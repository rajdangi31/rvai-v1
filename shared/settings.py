"""Runtime settings loaded from environment variables (RVAI_*)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Deployment configuration for Raj's V1 Jetson stack."""

    model_config = SettingsConfigDict(
        env_prefix="RVAI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Local LLM (Ollama / llama.cpp / LM Studio)
    llm_base_url: str = "http://127.0.0.1:11434/v1"
    llm_model: str = "qwen3.5:4b"
    llm_timeout_seconds: float = 60.0
    llm_api_key: Optional[str] = "ollama"
    llm_reasoning_effort: str = "none"
    llm_debug: bool = False

    # Whisper STT
    stt_backend: Literal["openai_compatible", "faster_whisper", "whisper_cpp", "stub"] = "stub"
    stt_base_url: str = "http://127.0.0.1:8080/v1"
    stt_model: str = "whisper-1"
    stt_language: str = "en"
    faster_whisper_model: str = "base.en"
    faster_whisper_device: str = "cpu"
    faster_whisper_compute_type: str = "int8"
    ffmpeg_binary: str = "ffmpeg"
    whisper_cli_binary: str = "whisper-cli"
    whisper_model_path: Optional[Path] = None

    # Piper TTS (outcome voice response)
    tts_backend: Literal["piper", "stub"] = "stub"
    piper_binary: str = "piper"
    piper_model_path: Optional[Path] = None
    tts_output_dir: Path = Field(default=PROJECT_ROOT / "static" / "voice_outputs")
    tts_play: bool = False

    # JSON <-> Matter Translator & Controller
    matter_backend: Literal["chip_tool", "matter_server"] = "chip_tool"
    matter_server_ws_url: str = "ws://127.0.0.1:5580/ws"
    chip_tool_binary: str = "chip-tool"
    confirm_timeout_seconds: float = Field(default=5.0, gt=0)
    matter_reconnect_seconds: float = Field(default=2.0, gt=0)

    # Input limits
    max_text_chars: int = Field(default=500, ge=32, le=4000)
    max_audio_seconds: float = Field(default=30.0, gt=0)
    max_audio_bytes: int = Field(default=5_000_000, gt=0)

    # Paths
    targets_path: Path = Field(default=PROJECT_ROOT / "config" / "targets.yaml")

    def resolved_targets_path(self) -> Path:
        return self.targets_path if self.targets_path.is_absolute() else PROJECT_ROOT / self.targets_path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
