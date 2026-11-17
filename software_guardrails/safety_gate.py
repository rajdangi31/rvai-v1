"""
Safety Layer (Raj): V1 allow/block checks shared by voice, text, and tablet taps.

V1 checks (Spec Sheet / FRONTEND_CONTRACT):
  - command is ON, OFF, or STATUS
  - target is configured
  - target is enabled
  - target is commissioned (has Matter node_id)
  - target supports the requested operation
  - request has required fields and valid values

No silent rewriting. Electrical / fault rules are deferred until approved.
"""

from __future__ import annotations

from typing import Optional

from pydantic import ValidationError

from shared.schemas import CommandRequest, SafetyDecision, SafetyReasonCode
from shared.settings import Settings, get_settings
from shared.targets import TargetRegistry, get_target_registry


class SafetyGate:
    """Single Safety Layer entry point."""

    def __init__(
        self,
        registry: Optional[TargetRegistry] = None,
        settings: Optional[Settings] = None,
    ):
        self.settings = settings or get_settings()
        self.registry = registry or get_target_registry(
            str(self.settings.resolved_targets_path())
        )

    def evaluate(self, request: CommandRequest) -> SafetyDecision:
        try:
            cmd = CommandRequest.model_validate(request.model_dump())
        except (ValidationError, ValueError) as exc:
            return self._block(request, SafetyReasonCode.INVALID_SCHEMA, f"Invalid command: {exc}")

        if cmd.target == "all":
            return self._block(
                cmd,
                SafetyReasonCode.ALL_DENIED,
                "Controlling all lights at once is not allowed in V1.",
            )

        record = self.registry.get(cmd.target)
        if record is None:
            return self._block(cmd, SafetyReasonCode.UNKNOWN_TARGET, f"Unknown target '{cmd.target}'.")
        if not record.enabled:
            return self._block(
                cmd,
                SafetyReasonCode.TARGET_DISABLED,
                f"Target '{record.display_name}' is disabled.",
            )
        if not record.commissioned:
            return self._block(
                cmd,
                SafetyReasonCode.TARGET_NOT_COMMISSIONED,
                f"Target '{record.display_name}' is not commissioned yet.",
            )
        if not record.supports(cmd.action):
            return self._block(
                cmd,
                SafetyReasonCode.UNSUPPORTED_ACTION,
                f"Action '{cmd.action}' is not supported on '{record.display_name}'.",
            )

        return SafetyDecision(allowed=True, request=cmd, reason_code=None, message="allowed")

    @staticmethod
    def _block(request: CommandRequest, code: SafetyReasonCode, message: str) -> SafetyDecision:
        return SafetyDecision(allowed=False, request=request, reason_code=code, message=message)
