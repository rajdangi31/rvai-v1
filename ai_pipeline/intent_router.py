"""
AI Intent Router (Raj): audio/text → CommandRequest | Clarification.

Flow: sanitize → rule parser → LLM (when needed) → target registry check.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Optional, Sequence
from uuid import uuid4

from ai_pipeline.llm_client import LLMClient, LLMError, parse_llm_json
from ai_pipeline.rule_parser import RuleParser
from ai_pipeline.stt_engine import STTEngine
from shared.constants import DEFAULT_CLARIFY_MESSAGE
from shared.schemas import (
    Clarification,
    ClarificationReason,
    CommandRequest,
    InterpretationResult,
    Source,
)
from shared.settings import Settings, get_settings
from shared.targets import TargetRegistry, get_target_registry

logger = logging.getLogger(__name__)

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SPACE_RE = re.compile(r"\s+")


def sanitize_text(text: str, max_chars: int) -> str:
    if text is None:
        return ""
    cleaned = _CONTROL_RE.sub("", unicodedata.normalize("NFKC", str(text)))
    return _SPACE_RE.sub(" ", cleaned).strip()[:max_chars].rstrip()


class IntentRouter:
    """Interprets user language into one V1 CommandRequest or a Clarification."""

    def __init__(
        self,
        registry: Optional[TargetRegistry] = None,
        settings: Optional[Settings] = None,
        llm_client: Optional[LLMClient] = None,
        stt_engine: Optional[STTEngine] = None,
    ):
        self.settings = settings or get_settings()
        self.registry = registry or get_target_registry(
            str(self.settings.resolved_targets_path())
        )
        self.rule_parser = RuleParser(self.registry)
        self.llm_client = llm_client or LLMClient(settings=self.settings)
        self.stt_engine = stt_engine or STTEngine(settings=self.settings)

    def interpret_text(
        self,
        text: str,
        *,
        source: Source = "text",
        request_id: Optional[str] = None,
    ) -> InterpretationResult:
        rid = request_id or str(uuid4())
        cleaned = sanitize_text(text, self.settings.max_text_chars)
        if not cleaned:
            return self.clarify(ClarificationReason.NOT_UNDERSTOOD, raw_text=text, request_id=rid)

        rule_hit = self.rule_parser.parse(
            cleaned, source=source, request_id=rid, clarify=self.clarify
        )
        if rule_hit is not None:
            return rule_hit

        return self._interpret_with_llm(cleaned, source=source, request_id=rid)

    def interpret_audio(
        self,
        audio_bytes: bytes,
        *,
        request_id: Optional[str] = None,
    ) -> InterpretationResult:
        rid = request_id or str(uuid4())
        text, err = self.stt_engine.transcribe(audio_bytes)
        if err is not None or text is None:
            return self.clarify(err or ClarificationReason.NO_SPEECH, request_id=rid)
        return self.interpret_text(text, source="voice", request_id=rid)

    def parse_intent(self, user_transcript: str) -> InterpretationResult:
        return self.interpret_text(user_transcript, source="text")

    def _interpret_with_llm(self, cleaned: str, *, source: Source, request_id: str) -> InterpretationResult:
        try:
            raw = self.llm_client.generate_completion(cleaned, zones=self.registry.display_names())
        except LLMError as exc:
            logger.warning("LLM unavailable for request %s: %s", request_id, exc)
            mentioned, _, _ = self.registry.resolve(cleaned, from_free_text=True)
            if mentioned:
                return self.clarify(
                    ClarificationReason.UNSUPPORTED_ACTION,
                    candidates=[mentioned],
                    raw_text=cleaned,
                    request_id=request_id,
                    detail="Please say on, off, or status for that zone.",
                )
            return self.clarify(ClarificationReason.AI_UNAVAILABLE, raw_text=cleaned, request_id=request_id)

        parsed = parse_llm_json(raw)
        if parsed.parse_error is not None:
            return self.clarify(parsed.parse_error, raw_text=cleaned, request_id=request_id)

        target_id, fail_reason, candidates = (
            self.registry.resolve(parsed.target) if parsed.target else (None, ClarificationReason.UNKNOWN_TARGET, [])
        )

        if target_id and parsed.action:
            record = self.registry.get(target_id)
            if record and record.enabled and record.supports(parsed.action):
                mentioned, _, _ = self.registry.resolve(cleaned, from_free_text=True)
                # Accept when confident, or when timid but the user actually named that zone.
                if not parsed.needs_clarification or mentioned == target_id:
                    return CommandRequest(
                        target=target_id,
                        action=parsed.action,
                        source=source,
                        raw_text=cleaned,
                        request_id=request_id,
                    )

        if parsed.needs_clarification:
            reason = next(
                (r for r in ClarificationReason if r.value == (parsed.clarification_reason or "").strip().lower()),
                ClarificationReason.NOT_UNDERSTOOD,
            )
            cands = candidates or ([target_id] if target_id else [])
            return self.clarify(reason, candidates=cands, raw_text=cleaned, request_id=request_id)

        return self.clarify(
            fail_reason or ClarificationReason.NOT_UNDERSTOOD,
            candidates=candidates,
            raw_text=cleaned,
            request_id=request_id,
        )

    def clarify(
        self,
        reason: ClarificationReason,
        *,
        candidates: Optional[Sequence[str]] = None,
        raw_text: Optional[str] = None,
        request_id: Optional[str] = None,
        detail: Optional[str] = None,
    ) -> Clarification:
        ids = list(candidates or [])
        names = [rec.display_name if (rec := self.registry.get(i)) else i for i in ids]
        joined = ", ".join(names)
        messages = {
            ClarificationReason.UNKNOWN_TARGET: "I didn't recognize that zone. Please name one of the known lights.",
            ClarificationReason.AMBIGUOUS_TARGET: f"Which zone did you mean: {joined}?" if joined else "Which zone did you mean?",
            ClarificationReason.MULTIPLE_TARGETS: f"Please choose one zone. I heard: {joined}." if joined else "Please choose one zone at a time.",
            ClarificationReason.UNSUPPORTED_ACTION: detail or "I can only turn lights on, off, or check status.",
            ClarificationReason.NO_SPEECH: "I didn't catch any speech. Please try again.",
            ClarificationReason.AI_UNAVAILABLE: "The language model is unavailable right now. Try a simple command like 'turn on the kitchen'.",
            ClarificationReason.NOT_UNDERSTOOD: detail or DEFAULT_CLARIFY_MESSAGE,
        }
        kwargs = {
            "reason": reason,
            "message": messages.get(reason, DEFAULT_CLARIFY_MESSAGE),
            "candidates": ids,
            "raw_text": raw_text,
        }
        if request_id:
            kwargs["request_id"] = request_id
        return Clarification(**kwargs)
