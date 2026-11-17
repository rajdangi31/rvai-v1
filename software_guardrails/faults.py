"""
Fault status helpers for display / future electrical rules.

Fault transport from firmware/Matter is still TBD. SafetyGate V1 does not
block on faults; ObservationStore still tracks fault_available for the UI.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict


class FaultStatus(str, Enum):
    CLEAR = "clear"
    ACTIVE = "active"
    UNKNOWN = "unknown"


class FaultProvider(ABC):
    @abstractmethod
    def status_for(self, target_id: str) -> FaultStatus:
        """Return fault status for a single target."""


class UnknownFaultProvider(FaultProvider):
    """Default provider: never claims fault-free when data is unavailable."""

    def status_for(self, target_id: str) -> FaultStatus:
        return FaultStatus.UNKNOWN


class InMemoryFaultProvider(FaultProvider):
    """Test / simulator provider with explicit per-target statuses."""

    def __init__(self, statuses: Dict[str, FaultStatus] | None = None):
        self._statuses: Dict[str, FaultStatus] = {
            key.lower(): value for key, value in (statuses or {}).items()
        }

    def set_status(self, target_id: str, status: FaultStatus) -> None:
        self._statuses[target_id.lower()] = status

    def clear(self, target_id: str) -> None:
        self._statuses.pop(target_id.lower(), None)

    def status_for(self, target_id: str) -> FaultStatus:
        return self._statuses.get(target_id.lower(), FaultStatus.UNKNOWN)
