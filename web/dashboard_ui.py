"""
Dashboard UI Client Stub
Browser-side dashboard that talks to the Smart RV backend over HTTP.
Not imported by backend.main_pipeline — lives here as a client contract.
"""

from typing import Dict, Any

from shared.constants import DEFAULT_BACKEND_URL


class DashboardUI:
    """Client stub for the main UI view, chat, and system feedback."""

    def __init__(self, backend_url: str = DEFAULT_BACKEND_URL):
        self.backend_url = backend_url

    def render_dashboard(self) -> None:
        """Draws the sidebar, lighting zone controls, and chat interface."""
        pass

    def submit_text_command(self, text: str) -> Dict[str, Any]:
        """Sends a user text message to the backend voice/text endpoint."""
        pass

    def display_message(self, sender: str, message: str) -> None:
        """Appends a new message bubble into the chat history view."""
        pass

    def play_tts_response(self, text: str) -> None:
        """Plays the spoken assistant reply out loud in the browser."""
        pass


class ZoneControllerUI:
    """Client stub for zone toggles and brightness sliders."""

    def __init__(self):
        self.zone_states: Dict[str, bool] = {}

    def on_zone_toggle_click(self, zone_name: str, state: bool) -> None:
        """Sends a manual toggle request to the backend for a specific zone."""
        pass

    def on_brightness_slider_change(self, zone_name: str, level: int) -> None:
        """Sends a manual dimmer adjustment request to the backend."""
        pass

    def update_zone_display(self, zone_name: str, is_on: bool, level: int) -> None:
        """Syncs the button and slider visuals with real hardware state."""
        pass
