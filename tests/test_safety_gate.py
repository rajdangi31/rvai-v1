"""Safety Layer allow/block matrix (V1 schema / target / commissioning checks only)."""

from __future__ import annotations

from shared.schemas import CommandRequest, SafetyReasonCode
from shared.targets import TargetRecord, TargetRegistry
from software_guardrails.safety_gate import SafetyGate


def _req(target: str, action: str, source: str = "tap") -> CommandRequest:
    return CommandRequest(target=target, action=action, source=source)  # type: ignore[arg-type]


def test_allows_valid_on_off_status(registry, settings):
    gate = SafetyGate(registry=registry, settings=settings)
    for action in ("ON", "OFF", "STATUS"):
        decision = gate.evaluate(_req("kitchen", action))
        assert decision.allowed is True
        assert decision.request.target == "kitchen"
        assert decision.request.action == action


def test_blocks_unknown_target(registry, settings):
    gate = SafetyGate(registry=registry, settings=settings)
    decision = gate.evaluate(_req("garage", "ON"))
    assert decision.allowed is False
    assert decision.reason_code == SafetyReasonCode.UNKNOWN_TARGET


def test_blocks_all(registry, settings):
    gate = SafetyGate(registry=registry, settings=settings)
    decision = gate.evaluate(_req("all", "OFF"))
    assert decision.allowed is False
    assert decision.reason_code == SafetyReasonCode.ALL_DENIED


def test_blocks_uncommissioned_target(settings):
    registry = TargetRegistry.from_records(
        [
            TargetRecord(
                id="kitchen",
                display_name="Kitchen",
                node_id=None,
                endpoint_id=1,
                aliases=("galley",),
                supported_actions=("ON", "OFF", "STATUS"),
                enabled=True,
            )
        ]
    )
    gate = SafetyGate(registry=registry, settings=settings)
    decision = gate.evaluate(_req("kitchen", "ON"))
    assert decision.allowed is False
    assert decision.reason_code == SafetyReasonCode.TARGET_NOT_COMMISSIONED


def test_blocks_disabled_target(settings):
    registry = TargetRegistry.from_records(
        [
            TargetRecord(
                id="kitchen",
                display_name="Kitchen",
                node_id=1,
                endpoint_id=1,
                aliases=(),
                supported_actions=("ON", "OFF", "STATUS"),
                enabled=False,
            )
        ]
    )
    gate = SafetyGate(registry=registry, settings=settings)
    decision = gate.evaluate(_req("kitchen", "ON"))
    assert decision.allowed is False
    assert decision.reason_code == SafetyReasonCode.TARGET_DISABLED


def test_normalizes_target_casing(registry, settings):
    gate = SafetyGate(registry=registry, settings=settings)
    decision = gate.evaluate(_req("Kitchen", "on"))
    assert decision.allowed is True
    assert decision.request.target == "kitchen"
    assert decision.request.action == "ON"
