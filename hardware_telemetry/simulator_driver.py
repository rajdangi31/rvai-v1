"""
Simulator Hardware Driver
In-memory mock adapter for development without physical hardware.
"""

from typing import Dict

from .hardware_adapter import HardwareAdapter


class SimulatorDriver(HardwareAdapter):
    """Records power and level commands in memory for local testing."""

    def __init__(self):
        self.device_states: Dict[int, Dict[str, object]] = {}

    def set_power(self, device_id: int, state: bool) -> bool:
        """Updates simulated on/off state for the device."""
        pass

    def set_level(self, device_id: int, level: int) -> bool:
        """Updates simulated brightness for the device."""
        pass
