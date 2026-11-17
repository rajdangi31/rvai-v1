"""Shared fixtures for AI + Safety + Backend tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from shared.settings import Settings, clear_settings_cache
from shared.targets import TargetRegistry, clear_target_registry_cache


TARGETS_PATH = Path(__file__).resolve().parent / "data" / "targets_all_commissioned.yaml"


@pytest.fixture()
def settings(tmp_path, monkeypatch) -> Settings:
    clear_settings_cache()
    clear_target_registry_cache()
    monkeypatch.setenv("RVAI_TARGETS_PATH", str(TARGETS_PATH))
    monkeypatch.setenv("RVAI_STT_BACKEND", "stub")
    monkeypatch.setenv("RVAI_TTS_BACKEND", "stub")
    monkeypatch.setenv("RVAI_MATTER_BACKEND", "chip_tool")
    settings = Settings()
    yield settings
    clear_settings_cache()
    clear_target_registry_cache()


@pytest.fixture()
def registry(settings) -> TargetRegistry:
    return TargetRegistry.load(settings.resolved_targets_path())
