"""OpenAI-compatible chat client + strict JSON parser for local LLMs."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

from shared.schemas import Action, ClarificationReason
from shared.settings import Settings, get_settings

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.IGNORECASE | re.DOTALL)
_ALLOWED_ACTIONS = {"ON", "OFF", "STATUS"}

SYSTEM_PROMPT = """You are the RV lighting intent extractor.
Return ONE JSON object with keys:
  target (string), action ("ON"|"OFF"|"STATUS"),
  needs_clarification (boolean), clarification_reason (string|null).
Rules:
- Only lighting control. action MUST be ON, OFF, or STATUS.
- Map synonyms to known zones (galley/cooking area -> Kitchen; lounge/living room/cabin -> Main Cabin; washroom -> Bathroom; outside -> Exterior).
- If no specific zone or area is mentioned, or the user asks for a mood/dimming (e.g. "cozy", "brighter", "dim"), set needs_clarification=true.
- Set needs_clarification=false when one zone/synonym AND one of ON/OFF/STATUS is clear.
- Never use 'all'. No dimming. JSON only.
Known zones: {zones}.
"""


class LLMError(RuntimeError):
    """Raised when the LLM cannot be reached or returns empty content."""


@dataclass(frozen=True)
class ParsedLLMIntent:
    target: str
    action: Optional[Action]
    needs_clarification: bool = False
    clarification_reason: Optional[str] = None
    parse_error: Optional[ClarificationReason] = None


def parse_llm_json(raw: str) -> ParsedLLMIntent:
    """Extract and validate JSON returned by the LLM."""
    text = (raw or "").strip()
    fence = _FENCE_RE.search(text)
    if fence:
        text = fence.group(1).strip()

    obj: Optional[Dict[str, Any]] = None
    start, end = text.find("{"), text.rfind("}")
    for candidate in (text, text[start : end + 1] if 0 <= start < end else ""):
        if not candidate:
            continue
        try:
            loaded = json.loads(candidate)
            if isinstance(loaded, dict):
                obj = loaded
                break
        except json.JSONDecodeError:
            continue

    if obj is None:
        return ParsedLLMIntent("", None, parse_error=ClarificationReason.NOT_UNDERSTOOD)

    target = obj.get("target").strip() if isinstance(obj.get("target"), str) else ""
    action_raw = obj.get("action")
    action: Optional[Action] = None
    if isinstance(action_raw, str) and action_raw.strip().upper() in _ALLOWED_ACTIONS:
        action = action_raw.strip().upper()  # type: ignore[assignment]

    if obj.get("needs_clarification") is True:
        reason = obj.get("clarification_reason")
        return ParsedLLMIntent(
            target=target,
            action=action,
            needs_clarification=True,
            clarification_reason=str(reason) if reason else "not_understood",
        )

    if not target:
        return ParsedLLMIntent("", None, parse_error=ClarificationReason.NOT_UNDERSTOOD)
    if action is None:
        err = ClarificationReason.UNSUPPORTED_ACTION if isinstance(action_raw, str) else ClarificationReason.NOT_UNDERSTOOD
        return ParsedLLMIntent(target, None, parse_error=err)
    return ParsedLLMIntent(target=target, action=action)


class LLMClient:
    def __init__(self, settings: Optional[Settings] = None, client: Optional[httpx.Client] = None):
        self.settings = settings or get_settings()
        self._client = client
        self._owns_client = client is None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            headers = {"Content-Type": "application/json"}
            if self.settings.llm_api_key:
                headers["Authorization"] = f"Bearer {self.settings.llm_api_key}"
            self._client = httpx.Client(
                base_url=self.settings.llm_base_url.rstrip("/"),
                timeout=self.settings.llm_timeout_seconds,
                headers=headers,
            )
        return self._client

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def health_check(self) -> bool:
        try:
            return self._get_client().get("/models").status_code < 500
        except httpx.HTTPError:
            return False

    def generate_completion(
        self,
        user_prompt: str,
        *,
        zones: Optional[List[str]] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        system = system_prompt or SYSTEM_PROMPT.format(zones=", ".join(zones or []) or "(none)")
        if self.settings.llm_debug:
            print("--- LLM INPUT (system) ---", flush=True)
            print(system, flush=True)
            print("--- LLM INPUT (user) ---", flush=True)
            print(user_prompt, flush=True)

        base: Dict[str, Any] = {
            "model": self.settings.llm_model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
        }
        effort = (self.settings.llm_reasoning_effort or "").strip()
        if effort:
            base["reasoning_effort"] = effort

        bodies = ({**base, "response_format": {"type": "json_object"}}, base)
        last_error: Optional[Exception] = None
        for attempt, body in enumerate(bodies):
            try:
                response = self._get_client().post("/chat/completions", json=body)
                if response.status_code >= 400 and attempt == 0:
                    continue
                response.raise_for_status()
                payload = response.json()
                content = self._extract_content(payload)
                if self.settings.llm_debug:
                    print("--- LLM RAW RESPONSE ---", flush=True)
                    print(json.dumps(payload, indent=2), flush=True)
                    print("--- LLM EXTRACTED CONTENT ---", flush=True)
                    print(content or "(empty)", flush=True)
                if not content:
                    raise LLMError("Empty LLM completion content")
                return content
            except (httpx.HTTPError, LLMError, ValueError, KeyError, IndexError) as exc:
                last_error = exc
                logger.warning("LLM attempt %s failed: %s", attempt + 1, exc)
        raise LLMError(f"LLM unavailable: {last_error}")

    @staticmethod
    def _extract_content(data: Dict[str, Any]) -> str:
        message = data.get("choices", [{}])[0].get("message", {}) or {}
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content
        for key in ("reasoning", "reasoning_content"):
            alt = message.get(key)
            if isinstance(alt, str) and "{" in alt and "}" in alt:
                start, end = alt.find("{"), alt.rfind("}")
                if end > start:
                    return alt[start : end + 1]
        return ""
