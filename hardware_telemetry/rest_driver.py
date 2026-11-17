"""
REST Hardware Driver
Controls devices through a remote HTTP/REST actuation API.
"""

from .hardware_adapter import HardwareAdapter
from shared.constants import DEFAULT_BACKEND_URL


class RestDriver(HardwareAdapter):
    """Sends power and level commands to a REST hardware bridge."""

    def __init__(self, base_url: str = DEFAULT_BACKEND_URL):
        self.base_url = base_url

    def set_power(self, device_id: int, state: bool) -> bool:
        """POSTs an on/off command to the REST bridge."""
        pass

    def set_level(self, device_id: int, level: int) -> bool:
        """POSTs a brightness command to the REST bridge."""
        pass
