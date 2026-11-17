"""Production targets.yaml: all aliases known; only kitchen commissioned by default."""

from __future__ import annotations

from pathlib import Path

from shared.schemas import CommandRequest
from shared.targets import TargetRegistry
from software_guardrails.safety_gate import SafetyGate

PROD_TARGETS = Path(__file__).resolve().parents[1] / "config" / "targets.yaml"


def test_production_registry_one_plug_default(settings):
    registry = TargetRegistry.load(PROD_TARGETS)
    assert registry.ids() == ["bathroom", "bedroom", "exterior", "kitchen", "main_cabin"]
    assert registry.commissioned_ids() == ["kitchen"]
    assert registry.find_mentions("turn on the galley") == ["kitchen"]
    assert registry.find_mentions("bedroom lights") == ["bedroom"]

    gate = SafetyGate(registry=registry, settings=settings)
    assert gate.evaluate(CommandRequest(target="kitchen", action="ON", source="tap")).allowed is True
    blocked = gate.evaluate(CommandRequest(target="bedroom", action="ON", source="tap"))
    assert blocked.allowed is False
    assert blocked.reason_code.value == "target_not_commissioned"
