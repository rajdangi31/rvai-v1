"""
Synchronous Python wrapper around CommandCoordinator for scripts / CLI / legacy callers.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from backend.coordinator import CommandCoordinator
from shared.schemas import CommandOutcome


class SmartRVPipeline:
    """Convenience synchronous façade over Raj's Week 06 CommandCoordinator."""

    def __init__(self, coordinator: Optional[CommandCoordinator] = None, **_unused: Any):
        self.coordinator = coordinator or CommandCoordinator()
        self.intent_router = self.coordinator.intent_router
        self.safety_gate = self.coordinator.safety_gate

    def process_text_command(self, user_text: str) -> Dict[str, Any]:
        return self._to_dict(asyncio.run(self.coordinator.handle_text(user_text)))

    def process_voice_command(self, audio_bytes: bytes) -> Dict[str, Any]:
        return self._to_dict(asyncio.run(self.coordinator.handle_audio(audio_bytes)))

    def process_tap_command(self, target: str, cmd: str) -> Dict[str, Any]:
        return self._to_dict(asyncio.run(self.coordinator.handle_tap(target, cmd)))

    @staticmethod
    def _to_dict(outcome: CommandOutcome) -> Dict[str, Any]:
        return outcome.model_dump()
