"""
Hardware Adapter
Abstract base class defining the standard interface for all RV hardware drivers.
"""

from abc import ABC, abstractmethod


class HardwareAdapter(ABC):
    """Abstract interface that each communication protocol driver implements."""

    @abstractmethod
    def set_power(self, device_id: int, state: bool) -> bool:
        """Turns the specified hardware node ON or OFF."""
        pass

    @abstractmethod
    def set_level(self, device_id: int, level: int) -> bool:
        """Sets the brightness level (0-100) on the hardware node."""
        pass
