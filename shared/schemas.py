"""
V1 shared contracts across AI Pipeline, Safety Layer, Backend, and Matter Translator.

Authority: RVAI/Architecture Design.drawio + Spec Sheet (RAJ) + FRONTEND_CONTRACT.md v0.1.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import List, Literal, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

Action = Literal["ON", "OFF", "STATUS"]
ActualState = Literal["ON", "OFF"]
Source = Literal["voice", "text", "tap"]
OutcomeStatus = Literal["confirmed", "blocked", "failed", "unconfirmed", "clarification"]


class ClarificationReason(str, Enum):
    UNKNOWN_TARGET = "unknown_target"
    AMBIGUOUS_TARGET = "ambiguous_target"
    MULTIPLE_TARGETS = "multiple_targets"
    UNSUPPORTED_ACTION = "unsupported_action"
    NOT_UNDERSTOOD = "not_understood"
    NO_SPEECH = "no_speech"
    AI_UNAVAILABLE = "ai_unavailable"


class SafetyReasonCode(str, Enum):
    INVALID_SCHEMA = "invalid_schema"
    UNKNOWN_TARGET = "unknown_target"
    TARGET_DISABLED = "target_disabled"
    TARGET_NOT_COMMISSIONED = "target_not_commissioned"
    UNSUPPORTED_ACTION = "unsupported_action"
    ALL_DENIED = "all_denied"
    TARGET_BUSY = "target_busy"


class CommandRequest(BaseModel):
    """Proposed (AI) or direct (tablet tap) command evaluated by SafetyGate."""

    target: str = Field(..., min_length=1)
    action: Action
    source: Source = "text"
    raw_text: Optional[str] = None
    request_id: str = Field(default_factory=lambda: str(uuid4()))

    @property
    def cmd(self) -> Action:
        return self.action

    @field_validator("target")
    @classmethod
    def normalize_target(cls, value: str) -> str:
        cleaned = value.strip().lower().replace(" ", "_").replace("-", "_")
        if not cleaned:
            raise ValueError("target must not be empty")
        return cleaned

    @field_validator("action", mode="before")
    @classmethod
    def normalize_action(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("raw_text", mode="before")
    @classmethod
    def normalize_raw_text(cls, value: object) -> Optional[str]:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None


class Clarification(BaseModel):
    """Returned when AI cannot safely produce a single CommandRequest."""

    reason: ClarificationReason
    message: str
    candidates: List[str] = Field(default_factory=list)
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    raw_text: Optional[str] = None


class SafetyDecision(BaseModel):
    """Allow/block result from the Safety Layer."""

    allowed: bool
    request: CommandRequest
    reason_code: Optional[SafetyReasonCode] = None
    message: str = ""


class DeviceObservation(BaseModel):
    """Normalized report from Matter read or subscription event (Firmware Actual)."""

    target: str
    actual: Optional[ActualState] = None
    fault: Optional[str] = None
    fault_available: bool = False
    fresh: bool = True
    sequence: int = 0
    observed_at: float = Field(default_factory=time.time)


class TargetStateView(BaseModel):
    """Display projection record published on GET/WS /api/state."""

    target: str
    display_name: str
    actual: Optional[ActualState] = None
    pending: Optional[Action] = None
    fault: Optional[str] = None
    fault_available: bool = False
    fresh: bool = False
    updated_at: Optional[float] = None


class CommandOutcome(BaseModel):
    """HTTP response returned by /api/command, /api/text, and /api/audio."""

    model_config = ConfigDict(extra="ignore")

    result: OutcomeStatus
    message: str
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    target: Optional[str] = None
    cmd: Optional[Action] = None
    actual: Optional[ActualState] = None
    fault: Optional[str] = None
    fault_available: bool = False
    fresh: bool = False
    reason_code: Optional[str] = None
    candidates: List[str] = Field(default_factory=list)
    audio_path: Optional[str] = None


InterpretationResult = Union[CommandRequest, Clarification]
