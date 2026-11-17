"""
Telemetry WebSocket Client Stub
Receives real-time telemetry from the backend to refresh the dashboard.
Not imported by backend.main_pipeline.
"""

from typing import Dict, Any, Callable, Optional

from shared.constants import DEFAULT_TELEMETRY_WS


class TelemetryClient:
    """Client stub for the live telemetry WebSocket subscription."""

    def __init__(self, ws_endpoint: str = DEFAULT_TELEMETRY_WS):
        self.ws_endpoint = ws_endpoint
        self.latest_telemetry: Optional[Dict[str, Any]] = None

    def connect(self) -> None:
        """Opens the WebSocket connection to the server."""
        pass

    def handle_incoming_telemetry(self, raw_data: str) -> Dict[str, Any]:
        """Parses incoming JSON data and notifies UI subscribers."""
        pass

    def subscribe(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Registers a listener for live telemetry updates."""
        pass

    def disconnect(self) -> None:
        """Closes the telemetry connection cleanly."""
        pass
