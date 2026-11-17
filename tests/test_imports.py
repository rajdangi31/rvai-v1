"""Smoke imports and V1 wiring checks."""

from ai_pipeline import IntentRouter, LLMClient, STTEngine
from backend.main_pipeline import SmartRVPipeline
from shared.schemas import Clarification, CommandRequest, SafetyDecision
from shared.targets import get_target_registry
from software_guardrails import SafetyGate


def test_core_exports(settings):
    registry = get_target_registry(str(settings.resolved_targets_path()))
    assert "kitchen" in registry.ids()
    assert "all" not in registry.ids()

    router = IntentRouter(registry=registry, settings=settings)
    gate = SafetyGate(registry=registry, settings=settings)
    assert router is not None
    assert gate is not None
    assert LLMClient(settings=settings) is not None
    assert STTEngine(settings=settings) is not None


def test_pipeline_constructs(settings, monkeypatch):
    monkeypatch.setenv("RVAI_TARGETS_PATH", str(settings.resolved_targets_path()))
    pipeline = SmartRVPipeline()
    assert hasattr(pipeline, "intent_router")
    assert hasattr(pipeline, "safety_gate")
    assert not hasattr(pipeline, "wake_engine")


def test_schema_roundtrip():
    request = CommandRequest(target="kitchen", action="ON", source="text")
    decision = SafetyDecision(allowed=True, request=request, message="allowed")
    assert decision.model_dump()["request"]["target"] == "kitchen"
    clarify = Clarification(reason="not_understood", message="retry")
    assert clarify.reason.value == "not_understood"
