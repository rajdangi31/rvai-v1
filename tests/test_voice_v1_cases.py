"""V1 voice transcript regression (no hardware / no real STT required)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ai_pipeline.intent_router import IntentRouter
from ai_pipeline.llm_client import LLMClient, LLMError
from shared.schemas import Clarification, CommandRequest

CASES_PATH = Path(__file__).resolve().parent / "data" / "voice_v1_cases.yaml"


class _OfflineLLM(LLMClient):
    def generate_completion(self, user_prompt: str, **kwargs) -> str:
        raise LLMError("offline test")


@pytest.fixture()
def router(registry, settings) -> IntentRouter:
    return IntentRouter(registry=registry, settings=settings, llm_client=_OfflineLLM(settings))


def _cases() -> list[dict]:
    raw = yaml.safe_load(CASES_PATH.read_text(encoding="utf-8")) or {}
    return list(raw.get("cases") or [])


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["id"])
def test_voice_v1_transcript_expectations(router: IntentRouter, case: dict):
    result = router.interpret_text(case["transcript"], source="voice")
    expect = case["expect"]
    kind = expect["kind"]

    if kind == "command":
        assert isinstance(result, CommandRequest), f"{case['id']}: expected command, got {result!r}"
        assert result.target == expect["target"]
        assert result.action == expect["cmd"]
        return

    assert kind == "clarification"
    assert isinstance(result, Clarification), f"{case['id']}: expected clarification, got {result!r}"
    if "reason" in expect:
        assert result.reason.value == expect["reason"]
