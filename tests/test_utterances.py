"""Offline utterance fixtures exercised through IntentRouter (rules path)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ai_pipeline.intent_router import IntentRouter
from ai_pipeline.llm_client import LLMClient, LLMError
from shared.schemas import Clarification, ClarificationReason, CommandRequest

FIXTURES = Path(__file__).parent / "data" / "utterances.yaml"


class _BoomLLM(LLMClient):
    def generate_completion(self, user_prompt: str, **kwargs) -> str:
        raise LLMError("offline fixture run")


def _cases():
    return yaml.safe_load(FIXTURES.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["text"][:40])
def test_utterance_fixture(registry, settings, case):
    router = IntentRouter(registry=registry, settings=settings, llm_client=_BoomLLM(settings))
    result = router.interpret_text(case["text"])
    if case["kind"] == "command":
        assert isinstance(result, CommandRequest)
        assert result.target == case["target"]
        assert result.action == case["action"]
    else:
        assert isinstance(result, Clarification)
        if "reason" in case:
            assert result.reason == ClarificationReason(case["reason"])
