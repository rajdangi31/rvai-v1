"""
CLI harness for Raj's Week 06 stack (AI Pipeline + Safety Layer + Matter Coordinator).

Examples:
  python -m ai_pipeline.cli "turn on the galley"
  python -m ai_pipeline.cli --tap kitchen ON
  python -m ai_pipeline.cli --audio sample.wav
  python -m ai_pipeline.cli --ai-only "please illuminate the cooking area"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from ai_pipeline.intent_router import IntentRouter
from backend.coordinator import CommandCoordinator
from shared.schemas import Clarification, CommandRequest
from shared.settings import Settings, clear_settings_cache
from software_guardrails.safety_gate import SafetyGate


def _dump(obj: object) -> None:
    print(json.dumps(obj.model_dump() if hasattr(obj, "model_dump") else obj, indent=2))


def _settings_with_flags(args: argparse.Namespace) -> Settings:
    clear_settings_cache()
    settings = Settings()
    if args.show_llm:
        settings.llm_debug = True
    return settings


async def _run_full(args: argparse.Namespace) -> int:
    settings = _settings_with_flags(args)
    coord = CommandCoordinator(settings=settings)
    await coord.start()
    try:
        if args.tap:
            outcome = await coord.handle_tap(args.tap[0], args.tap[1])
        elif args.audio:
            outcome = await coord.handle_audio(args.audio.read_bytes())
        else:
            outcome = await coord.handle_text(args.text)
        _dump(outcome)
        return 0 if outcome.result == "confirmed" else 2
    finally:
        await coord.stop()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RVAI Week 06 CLI (Raj)")
    parser.add_argument("text", nargs="?", help="Natural language command")
    parser.add_argument("--audio", type=Path, help="WAV file for STT path")
    parser.add_argument("--tap", nargs=2, metavar=("TARGET", "CMD"), help="Direct tablet tap (ON/OFF/STATUS)")
    parser.add_argument("--ai-only", action="store_true", help="Stop after AI + SafetyGate without Matter dispatch")
    parser.add_argument(
        "--show-llm",
        action="store_true",
        help="Print exact LLM system/user prompts and raw model response (only when the LLM is used)",
    )
    args = parser.parse_args(argv)

    if not (args.tap or args.audio or args.text):
        parser.error("Provide text, --audio, or --tap")
        return 1

    if not args.ai_only:
        return asyncio.run(_run_full(args))

    settings = _settings_with_flags(args)
    router = IntentRouter(settings=settings)
    gate = SafetyGate(registry=router.registry, settings=settings)
    if args.tap:
        decision = gate.evaluate(CommandRequest(target=args.tap[0], action=args.tap[1], source="tap"))  # type: ignore[arg-type]
        _dump(decision)
        return 0 if decision.allowed else 2

    result = router.interpret_audio(args.audio.read_bytes()) if args.audio else router.interpret_text(args.text)
    _dump(result)
    if isinstance(result, CommandRequest):
        decision = gate.evaluate(result)
        _dump(decision)
        return 0 if decision.allowed else 2
    return 3


if __name__ == "__main__":
    sys.exit(main())
