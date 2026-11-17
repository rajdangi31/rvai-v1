"""
Raj: Observation Handling & Display State Publisher.

Rules:
  - Startup state is unknown (actual=None, fresh=False) until observed from Matter.
  - Pending command does NOT overwrite actual; only a valid DeviceObservation does.
  - Connection loss marks fresh=False while retaining last observed actual.
  - fault_available=false with fault=null means unknown (never treat as fault-free).
  - Observations get a monotonic sequence so old cached state cannot settle a new command.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Dict, List, Optional, Set

from shared.schemas import Action, DeviceObservation, TargetStateView
from shared.targets import TargetRegistry
from software_guardrails.faults import FaultProvider, FaultStatus

StateSubscriber = Callable[[Dict[str, object]], Awaitable[None]]


class ObservationStore(FaultProvider):
    """Stores last observed Matter state per target and feeds SafetyGate + WS /api/state."""

    def __init__(self, registry: TargetRegistry):
        self.registry = registry
        self._sequence = 0
        self._views: Dict[str, TargetStateView] = {
            rec.id: TargetStateView(
                target=rec.id,
                display_name=rec.display_name,
                actual=None,
                pending=None,
                fault=None,
                fault_available=False,
                fresh=False,
                updated_at=None,
            )
            for rec in registry.records.values()
        }
        self._queues: Dict[str, List[asyncio.Queue[DeviceObservation]]] = {}
        self._subscribers: Set[StateSubscriber] = set()

    def current_sequence(self) -> int:
        return self._sequence

    # --- FaultProvider interface (display / future electrical rules) ---
    def status_for(self, target_id: str) -> FaultStatus:
        view = self._views.get(target_id.lower())
        if view is None or not view.fault_available or not view.fresh:
            return FaultStatus.UNKNOWN
        return FaultStatus.ACTIVE if view.fault else FaultStatus.CLEAR

    # --- Snapshots & pending tracking ---
    def snapshot(self) -> List[TargetStateView]:
        return [self._views[tid].model_copy() for tid in self.registry.ids()]

    def get(self, target_id: str) -> Optional[TargetStateView]:
        view = self._views.get(target_id)
        return view.model_copy() if view else None

    def is_pending(self, target_id: str) -> bool:
        view = self._views.get(target_id)
        return bool(view and view.pending is not None)

    async def set_pending(self, target_id: str, action: Optional[Action]) -> None:
        view = self._views.get(target_id)
        if view is None:
            return
        self._views[target_id] = view.model_copy(update={"pending": action})
        await self._broadcast({"type": "state", "state": self._views[target_id].model_dump()})

    async def mark_all_stale(self) -> None:
        for tid, view in list(self._views.items()):
            self._views[tid] = view.model_copy(update={"fresh": False})
        await self._broadcast({"type": "snapshot", "states": [v.model_dump() for v in self.snapshot()]})

    # --- Incoming Matter observations ---
    async def apply_observation(self, obs: DeviceObservation) -> DeviceObservation:
        view = self._views.get(obs.target)
        if view is None:
            return obs

        self._sequence += 1
        stamped = obs.model_copy(update={"sequence": self._sequence})
        updated = view.model_copy(
            update={
                "actual": stamped.actual if stamped.actual is not None else view.actual,
                "fault": stamped.fault,
                "fault_available": stamped.fault_available,
                "fresh": stamped.fresh,
                "updated_at": stamped.observed_at,
            }
        )
        self._views[obs.target] = updated

        for queue in list(self._queues.get(obs.target, [])):
            await queue.put(stamped)

        await self._broadcast({"type": "state", "state": updated.model_dump()})
        return stamped

    def open_observation_queue(self, target_id: str) -> asyncio.Queue[DeviceObservation]:
        queue: asyncio.Queue[DeviceObservation] = asyncio.Queue()
        self._queues.setdefault(target_id, []).append(queue)
        return queue

    def close_observation_queue(self, target_id: str, queue: asyncio.Queue[DeviceObservation]) -> None:
        buckets = self._queues.get(target_id)
        if not buckets:
            return
        try:
            buckets.remove(queue)
        except ValueError:
            return
        if not buckets:
            self._queues.pop(target_id, None)

    # --- WebSocket subscriber management ---
    def subscribe(self, callback: StateSubscriber) -> None:
        self._subscribers.add(callback)

    def unsubscribe(self, callback: StateSubscriber) -> None:
        self._subscribers.discard(callback)

    async def _broadcast(self, payload: Dict[str, object]) -> None:
        for callback in list(self._subscribers):
            try:
                await callback(payload)
            except Exception:
                self._subscribers.discard(callback)
