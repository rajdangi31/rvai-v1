"""
CAN Bus Listener
Reads real-time vehicle electrical metrics (voltage, current, relay state) over the CAN bus.
"""

from typing import Dict, Any, Optional

from .state_cache import StateCache


class CANBusListener:
    """Reads CAN frames from the RV bus to monitor battery voltage, current, and relay statuses."""

    def __init__(
        self,
        channel: str = "can0",
        bitrate: int = 250000,
        state_cache: Optional[StateCache] = None,
    ):
        self.channel = channel
        self.bitrate = bitrate
        self.state_cache = state_cache or StateCache()
        self.is_running = False

    def start_listener(self) -> None:
        """Launches the background thread listening for CAN frames."""
        pass

    def decode_can_frame(self, frame_id: int, payload: bytes) -> Dict[str, Any]:
        """Extracts voltage, current, and temperature from raw frame bytes."""
        pass

    def stop_listener(self) -> None:
        """Terminates the CAN listening thread."""
        pass
