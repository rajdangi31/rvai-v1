"""Shared V1 contracts, settings, and target registry."""

from shared.schemas import (
    Clarification,
    ClarificationReason,
    CommandOutcome,
    CommandRequest,
    DeviceObservation,
    InterpretationResult,
    SafetyDecision,
    SafetyReasonCode,
    TargetStateView,
)
from shared.settings import Settings, get_settings
from shared.targets import TargetRecord, TargetRegistry, get_target_registry

__all__ = [
    "Clarification",
    "ClarificationReason",
    "CommandOutcome",
    "CommandRequest",
    "DeviceObservation",
    "InterpretationResult",
    "SafetyDecision",
    "SafetyReasonCode",
    "Settings",
    "TargetRecord",
    "TargetRegistry",
    "TargetStateView",
    "get_settings",
    "get_target_registry",
]
