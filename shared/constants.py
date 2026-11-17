"""Shared constants for Smart RV V1."""

DEFAULT_CLARIFY_MESSAGE = (
    "I need a clearer request. Please name one zone and say on, off, or status."
)

# Default local service endpoints (web / hardware stubs)
DEFAULT_BACKEND_URL: str = "http://127.0.0.1:8000"
DEFAULT_TELEMETRY_WS: str = "ws://127.0.0.1:8000/api/state"
DEFAULT_WAKE_WS: str = "ws://127.0.0.1:8000/api/audio"
