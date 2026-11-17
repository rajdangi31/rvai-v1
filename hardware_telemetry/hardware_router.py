"""
Hardware Communication Router
Routes validated commands to the active physical protocol (Simulator, Matter, BLE, or REST).

Zone IDs are derived from the V1 target registry so AI/Safety and hardware stay aligned.
"""

from typing import Any, Dict, Optional

from shared.targets import get_target_registry
from .hardware_adapter import HardwareAdapter
from .simulator_driver import SimulatorDriver
from .matter_driver import MatterDriver
from .ble_driver import BLEDriver
from .rest_driver import RestDriver

HARDWARE_MODES = ("simulator", "matter", "ble", "rest")


class HardwareRouter:
    """Selects the active hardware transport and executes actions."""

    def __init__(self, mode: str = "simulator", adapter: Optional[HardwareAdapter] = None):
        if mode not in HARDWARE_MODES:
            raise ValueError(f"Unsupported hardware mode: {mode}. Expected one of {HARDWARE_MODES}")

        self.mode = mode
        try:
            self.zone_id_map: Dict[str, int] = get_target_registry().zone_id_map()
        except Exception:
            # Registry may be unavailable in partial checkouts; keep empty map.
            self.zone_id_map = {}
        self.adapter = adapter or self._create_adapter(mode)

    def _create_adapter(self, mode: str) -> HardwareAdapter:
        if mode == "simulator":
            return SimulatorDriver()
        if mode == "matter":
            return MatterDriver()
        if mode == "ble":
            return BLEDriver()
        if mode == "rest":
            return RestDriver()
        raise ValueError(f"Unsupported hardware mode: {mode}")

    def resolve_device_id(self, zone_name: str) -> int:
        """Looks up the numerical device ID for a given zone."""
        key = zone_name.strip().lower().replace(" ", "_")
        if key not in self.zone_id_map:
            raise KeyError(f"Unknown zone: {zone_name}")
        return self.zone_id_map[key]

    def dispatch_command(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Routes the command to the active adapter (simulator, Matter, BLE, or REST)."""
        pass
