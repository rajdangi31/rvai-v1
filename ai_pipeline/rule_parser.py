"""Deterministic keyword parser for common V1 lighting phrases."""

from __future__ import annotations

import re
from typing import Optional

from shared.schemas import Action, Clarification, CommandRequest, InterpretationResult, Source
from shared.targets import TargetRegistry

_ON = [re.compile(p, re.I) for p in (r"\bturn\s+on\b", r"\bswitch\s+on\b", r"\blights?\s+on\b", r"\bpower\s+on\b", r"\benable\b", r"\bactivate\b")]
_OFF = [re.compile(p, re.I) for p in (r"\bturn\s+off\b", r"\bswitch\s+off\b", r"\blights?\s+off\b", r"\bpower\s+off\b", r"\bdisable\b", r"\bdeactivate\b", r"\bshut\s+off\b", r"\bkill\b")]
_STATUS = [re.compile(p, re.I) for p in (r"\bstatus\b", r"\bstate\b", r"\bis\s+(?:the\s+)?.+\s+on\b", r"\bare\s+(?:the\s+)?.+\s+on\b", r"\bcheck\b", r"\bwhat(?:'s|\s+is)\s+(?:the\s+)?(?:status|state)\b")]


def detect_action(text: str) -> Optional[Action]:
    if any(p.search(text) for p in _OFF):
        return "OFF"
    if any(p.search(text) for p in _ON):
        return "ON"
    if any(p.search(text) for p in _STATUS):
        return "STATUS"
    return None


class RuleParser:
    """Fast offline parser; returns None when the LLM should take over."""

    def __init__(self, registry: TargetRegistry):
        self.registry = registry

    def parse(
        self,
        text: str,
        *,
        source: Source = "text",
        request_id: Optional[str] = None,
        clarify=None,
    ) -> Optional[InterpretationResult]:
        cleaned = text.strip()
        action = detect_action(cleaned) if cleaned else None
        if action is None:
            return None

        target_id, fail_reason, candidates = self.registry.resolve(cleaned, from_free_text=True)
        if target_id:
            kwargs = {"target": target_id, "action": action, "source": source, "raw_text": cleaned}
            if request_id:
                kwargs["request_id"] = request_id
            return CommandRequest(**kwargs)

        # Action matched + multiple zones named → clarify immediately (don't waste an LLM call).
        if fail_reason and candidates and clarify is not None:
            return clarify(fail_reason, candidates=candidates, raw_text=cleaned, request_id=request_id)
        return None
