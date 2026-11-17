"""Test-only controllable MatterPort. Not a product backend — never selected via RVAI_MATTER_BACKEND."""

from __future__ import annotations

import asyncio
from typing import Dict, Optional

from matter_bridge.adapter import MatterError, MatterPort, ObservationCallback
from shared.schemas import ActualState, DeviceObservation
from shared.targets import TargetRecord


class FakeMatterPort(MatterPort):
    """Injects observations/failures for acceptance tests without pretending to be firmware."""

    def __init__(self, auto_report: bool = True):
        self.auto_report = auto_report
        self._actuals: Dict[str, Optional[ActualState]] = {}
        self._faults: Dict[str, Optional[str]] = {}
        self._fault_available: Dict[str, bool] = {}
        self._drop_targets: set[str] = set()
        self._stale_first: set[str] = set()
        self._callback: Optional[ObservationCallback] = None

    async def start(self, on_observation: ObservationCallback) -> None:
        self._callback = on_observation

    def set_fault(self, target_id: str, fault: Optional[str], *, available: bool = True) -> None:
        self._faults[target_id] = fault
        self._fault_available[target_id] = available

    def set_drop(self, target_id: str, drop: bool = True) -> None:
        if drop:
            self._drop_targets.add(target_id)
        else:
            self._drop_targets.discard(target_id)

    def set_stale_first(self, target_id: str, enabled: bool = True) -> None:
        if enabled:
            self._stale_first.add(target_id)
        else:
            self._stale_first.discard(target_id)

    async def emit_manual_change(
        self, target_id: str, actual: ActualState, fault: Optional[str] = None
    ) -> None:
        """Stand-in for a rocker / external change observation in tests."""
        self._actuals[target_id] = actual
        self._faults[target_id] = fault
        self._fault_available[target_id] = True
        await self._emit(
            DeviceObservation(
                target=target_id,
                actual=actual,
                fault=fault,
                fault_available=True,
                fresh=True,
            )
        )

    async def invoke_on(self, target: TargetRecord) -> None:
        await self._set_on_off(target, True)

    async def invoke_off(self, target: TargetRecord) -> None:
        await self._set_on_off(target, False)

    async def _set_on_off(self, target: TargetRecord, turn_on: bool) -> None:
        if target.id in self._drop_targets:
            return
        desired: ActualState = "ON" if turn_on else "OFF"
        if target.id in self._stale_first:
            previous = self._actuals.get(target.id)
            if previous is not None and previous != desired:
                await self._emit(
                    DeviceObservation(
                        target=target.id,
                        actual=previous,
                        fault=self._faults.get(target.id),
                        fault_available=self._fault_available.get(target.id, False),
                        fresh=True,
                    )
                )
                await asyncio.sleep(0)
        self._actuals[target.id] = desired
        if self.auto_report:
            await self._emit(
                DeviceObservation(
                    target=target.id,
                    actual=desired,
                    fault=self._faults.get(target.id),
                    fault_available=self._fault_available.get(target.id, True),
                    fresh=True,
                )
            )

    async def read_onoff(self, target: TargetRecord) -> DeviceObservation:
        if target.id in self._drop_targets:
            raise MatterError(f"Timed out reading node {target.node_id}")
        obs = DeviceObservation(
            target=target.id,
            actual=self._actuals.get(target.id, "OFF"),
            fault=self._faults.get(target.id),
            fault_available=self._fault_available.get(target.id, True),
            fresh=True,
        )
        await self._emit(obs)
        return obs

    async def _emit(self, obs: DeviceObservation) -> None:
        if self._callback is not None:
            maybe = self._callback(obs)
            if asyncio.iscoroutine(maybe):
                await maybe
