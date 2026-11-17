"""Rule parser + target registry resolution coverage."""

from __future__ import annotations

import pytest

from ai_pipeline.intent_router import IntentRouter
from ai_pipeline.llm_client import LLMClient, LLMError
from ai_pipeline.rule_parser import RuleParser
from shared.schemas import Clarification, ClarificationReason, CommandRequest


@pytest.mark.parametrize(
    "text,target,action",
    [
        ("turn on the kitchen", "kitchen", "ON"),
        ("Turn OFF the galley lights", "kitchen", "OFF"),
        ("is the lounge on", "main_cabin", "STATUS"),
        ("switch on bathroom", "bathroom", "ON"),
        ("power off exterior lights", "exterior", "OFF"),
        ("check bedroom status", "bedroom", "STATUS"),
    ],
)
def test_rule_parser_happy_paths(registry, text, target, action):
    result = RuleParser(registry).parse(text)
    assert isinstance(result, CommandRequest)
    assert result.target == target
    assert result.action == action


def test_rule_parser_multiple_targets(registry, settings):
    router = IntentRouter(registry=registry, settings=settings)
    result = router.interpret_text("turn on the kitchen and bathroom")
    assert isinstance(result, Clarification)
    assert result.reason == ClarificationReason.MULTIPLE_TARGETS


def test_registry_aliases(registry):
    assert registry.resolve("galley")[0] == "kitchen"
    assert registry.resolve("living room")[0] == "main_cabin"
    target_id, reason, _ = registry.resolve("all lights")
    assert target_id is None
    assert reason == ClarificationReason.MULTIPLE_TARGETS


class _BoomLLM(LLMClient):
    def generate_completion(self, user_prompt: str, **kwargs) -> str:
        raise LLMError("down")


def test_router_uses_rules_without_llm(registry, settings):
    router = IntentRouter(registry=registry, settings=settings, llm_client=_BoomLLM(settings))
    result = router.interpret_text("turn on the kitchen")
    assert isinstance(result, CommandRequest)
    assert result.target == "kitchen"
    assert result.action == "ON"


def test_router_clarifies_when_llm_down_and_no_rule(registry, settings):
    router = IntentRouter(registry=registry, settings=settings, llm_client=_BoomLLM(settings))
    result = router.interpret_text("make it cozy in here")
    assert isinstance(result, Clarification)
    assert result.reason == ClarificationReason.AI_UNAVAILABLE


def test_clarification_messages(registry, settings):
    router = IntentRouter(registry=registry, settings=settings)
    msg = router.clarify(
        ClarificationReason.AMBIGUOUS_TARGET,
        candidates=["kitchen", "bedroom"],
    )
    assert "Kitchen" in msg.message
    assert "Bedroom" in msg.message
