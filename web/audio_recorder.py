"""
Frontend Audio Recorder and Wake-Stream Client Stubs
Browser mic capture and PCM streaming to the backend wake-word endpoint.
Not imported by backend.main_pipeline.
"""

from typing import Callable, Any

from shared.constants import DEFAULT_WAKE_WS


class AudioRecorder:
    """Client stub for browser microphone permissions and WAV/PCM capture."""

    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self.is_recording = False

    def request_mic_permission(self) -> bool:
        """Prompts the user for microphone access permission."""
        pass

    def start_recording(self) -> None:
        """Begins recording audio for a single voice command."""
        pass

    def stop_recording(self) -> bytes:
        """Stops recording and returns the raw WAV audio bytes."""
        pass


class WakeStreamClient:
    """Client stub that streams PCM chunks to the backend wake-word detector."""

    def __init__(self, websocket_url: str = DEFAULT_WAKE_WS):
        self.websocket_url = websocket_url

    def connect(self) -> None:
        """Establishes a persistent streaming connection to the server."""
        pass

    def send_pcm_chunk(self, pcm_data: bytes) -> None:
        """Transmits a live audio chunk for wake detection."""
        pass

    def on_wake_word_detected(self, callback: Callable[[], Any]) -> None:
        """Registers a callback triggered when the wake word is heard."""
        pass
