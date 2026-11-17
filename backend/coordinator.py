"""
Raj: Backend Command Service & Outcome Responder.

Lifecycle:
  1. Receive tap / text / voice request (AI runs first for text/voice).
  2. SafetyGate validates target + cmd (V1 schema / commissioning checks).
  3. Enforce one pending operation per target; mark pending without altering actual.
  4. Dispatch ON / OFF / STATUS via MatterPort.
  5. Wait for a matching DeviceObservation (seq > baseline) up to confirm_timeout_seconds.
     Contradictory reports update display but do not settle; keep waiting until deadline.
  6. Return honest outcome: confirmed | blocked | failed | unconfirmed | clarification.
     No automatic ON/OFF retry. ACK alone is never confirmation.
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional

from ai_pipeline.intent_router import IntentRouter
from ai_pipeline.tts_engine import TTSEngine
from backend.observations import ObservationStore
from matter_bridge.adapter import MatterAdapter, MatterError
from shared.schemas import (
    Action,
    Clarification,
    CommandOutcome,
    CommandRequest,
    DeviceObservation,
    SafetyReasonCode,
)
from shared.settings import Settings, get_settings
from shared.targets import TargetRegistry, get_target_registry
from software_guardrails.safety_gate import SafetyGate


def _outcome_message(
    *,
    label: str,
    action: Action,
    result: str,
    actual: Optional[str],
    detail: Optional[str] = None,
) -> str:
    if result == "confirmed":
        if action == "STATUS":
            return f"The {label} light is currently {actual or 'unknown'}."
        if action == "ON":
            return f"The {label} light is on."
        return f"The {label} light is off."
    if result == "unconfirmed":
        return f"I couldn't confirm the {label} light's state."
    if detail:
        return detail
    return f"Could not complete {action} for {label}."


class CommandCoordinator:
    """Central coordinator connecting AI, Safety, MatterPort, Observations, and TTS."""

    def __init__(
        self,
        *,
        settings: Optional[Settings] = None,
        registry: Optional[TargetRegistry] = None,
        observations: Optional[ObservationStore] = None,
        intent_router: Optional[IntentRouter] = None,
        safety_gate: Optional[SafetyGate] = None,
        matter_adapter: Optional[MatterAdapter] = None,
        tts_engine: Optional[TTSEngine] = None,
    ):
        self.settings = settings or get_settings()
        self.registry = registry or get_target_registry(str(self.settings.resolved_targets_path()))
        self.observations = observations or ObservationStore(self.registry)
        self.intent_router = intent_router or IntentRouter(registry=self.registry, settings=self.settings)
        self.safety_gate = safety_gate or SafetyGate(registry=self.registry, settings=self.settings)
        self.matter = matter_adapter or MatterAdapter(registry=self.registry, settings=self.settings)
        self.tts = tts_engine or TTSEngine(settings=self.settings)
        self._started = False
        self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready

    async def start(self) -> None:
        if self._started:
            return
        await self.matter.start(self.observations.apply_observation)
        self._started = True
        # Read commissioned devices before presenting state as current. Never replay commands.
        for target_id in self.registry.commissioned_ids():
            try:
                await self.matter.read_onoff(target_id)
            except MatterError:
                view = self.observations.get(target_id)
                if view and view.fresh:
                    await self.observations.apply_observation(
                        DeviceObservation(
                            target=target_id,
                            actual=view.actual,
                            fault=view.fault,
                            fault_available=view.fault_available,
                            fresh=False,
                        )
                    )
        self._ready = True

    async def stop(self) -> None:
        if self._started:
            self._ready = False
            await self.matter.stop()
            self._started = False

    # --- Public entrypoints ---
    async def handle_tap(self, target: str, cmd: str) -> CommandOutcome:
        try:
            req = CommandRequest(target=target, action=cmd, source="tap")  # type: ignore[arg-type]
        except Exception as exc:
            return self._finish(
                CommandOutcome(
                    result="blocked",
                    target=target,
                    reason_code=SafetyReasonCode.INVALID_SCHEMA.value,
                    message=f"Invalid command: {exc}",
                ),
                speak=False,
            )
        return await self.execute_request(req)

    async def handle_text(self, text: str) -> CommandOutcome:
        result = await asyncio.to_thread(self.intent_router.interpret_text, text, source="text")
        if isinstance(result, Clarification):
            return self._from_clarification(result, speak=False)
        return await self.execute_request(result)

    async def handle_audio(self, audio_bytes: bytes) -> CommandOutcome:
        result = await asyncio.to_thread(self.intent_router.interpret_audio, audio_bytes)
        if isinstance(result, Clarification):
            return self._from_clarification(result, speak=True)
        return await self.execute_request(result)

    # --- Core request lifecycle ---
    async def execute_request(self, request: CommandRequest) -> CommandOutcome:
        await self.start()
        speak = request.source == "voice"

        decision = self.safety_gate.evaluate(request)
        cmd = decision.request
        if not decision.allowed:
            return self._finish(self._blocked_outcome(cmd, decision.message, decision.reason_code), speak=speak)

        if self.observations.is_pending(cmd.target):
            return self._finish(
                self._blocked_outcome(
                    cmd,
                    f"Another operation is already pending for '{cmd.target}'.",
                    SafetyReasonCode.TARGET_BUSY,
                ),
                speak=speak,
            )

        record = self.registry.get(cmd.target)
        label = record.display_name if record else cmd.target
        if speak and cmd.action in {"ON", "OFF"}:
            # Spec wording while waiting — never claims physical success.
            interim = f"Turning {'on' if cmd.action == 'ON' else 'off'} the {label} light."
            await asyncio.to_thread(self.tts.synthesize_speech, interim, play=True)

        baseline = self.observations.current_sequence()
        queue = self.observations.open_observation_queue(cmd.target)
        await self.observations.set_pending(cmd.target, cmd.action)

        try:
            await self.matter.dispatch(cmd.target, cmd.action)
            obs = await self._wait_for_match(queue, cmd.action, baseline)
        except MatterError as exc:
            view = self.observations.get(cmd.target)
            return self._finish(
                CommandOutcome(
                    result="failed",
                    request_id=cmd.request_id,
                    target=cmd.target,
                    cmd=cmd.action,
                    actual=view.actual if view else None,
                    fault=view.fault if view else None,
                    fault_available=view.fault_available if view else False,
                    fresh=view.fresh if view else False,
                    message=f"Could not reach {label}: {exc}",
                ),
                speak=speak,
            )
        except asyncio.TimeoutError:
            view = self.observations.get(cmd.target)
            return self._finish(
                CommandOutcome(
                    result="unconfirmed",
                    request_id=cmd.request_id,
                    target=cmd.target,
                    cmd=cmd.action,
                    actual=view.actual if view else None,
                    fault=view.fault if view else None,
                    fault_available=view.fault_available if view else False,
                    fresh=view.fresh if view else False,
                    message=_outcome_message(label=label, action=cmd.action, result="unconfirmed", actual=None),
                ),
                speak=speak,
            )
        finally:
            self.observations.close_observation_queue(cmd.target, queue)
            await self.observations.set_pending(cmd.target, None)

        return self._finish(
            CommandOutcome(
                result="confirmed",
                request_id=cmd.request_id,
                target=cmd.target,
                cmd=cmd.action,
                actual=obs.actual,
                fault=obs.fault,
                fault_available=obs.fault_available,
                fresh=obs.fresh,
                message=_outcome_message(
                    label=label,
                    action=cmd.action,
                    result="confirmed",
                    actual=obs.actual,
                ),
            ),
            speak=speak,
        )

    async def _wait_for_match(
        self,
        queue: asyncio.Queue[DeviceObservation],
        action: Action,
        baseline: int,
    ) -> DeviceObservation:
        deadline = time.monotonic() + self.settings.confirm_timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise asyncio.TimeoutError()
            obs = await asyncio.wait_for(queue.get(), timeout=remaining)
            if obs.sequence <= baseline:
                continue
            if action == "STATUS":
                if obs.actual is not None:
                    return obs
                continue
            if obs.actual == action:
                return obs
            # Contradictory report: display already updated; keep waiting until deadline.

    def _blocked_outcome(
        self,
        cmd: CommandRequest,
        message: str,
        reason: Optional[SafetyReasonCode],
    ) -> CommandOutcome:
        view = self.observations.get(cmd.target)
        return CommandOutcome(
            result="blocked",
            request_id=cmd.request_id,
            target=cmd.target,
            cmd=cmd.action,
            actual=view.actual if view else None,
            fault=view.fault if view else None,
            fault_available=view.fault_available if view else False,
            fresh=view.fresh if view else False,
            reason_code=reason.value if reason else None,
            message=message,
        )

    def _from_clarification(self, item: Clarification, *, speak: bool) -> CommandOutcome:
        return self._finish(
            CommandOutcome(
                result="clarification",
                request_id=item.request_id,
                reason_code=item.reason.value,
                candidates=item.candidates,
                message=item.message,
            ),
            speak=speak,
        )

    def _finish(self, outcome: CommandOutcome, *, speak: bool) -> CommandOutcome:
        if not speak:
            return outcome
        audio = self.tts.synthesize_speech(outcome.message, play=True)
        return outcome.model_copy(update={"audio_path": audio}) if audio else outcome
