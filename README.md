# Smart RV — V1 Jetson Software Stack (Raj)

Raj's V1 blocks for the **12V Smart Switch (RVAI)** on the Jetson Orin Nano Super.

**Authority:** `RVAI/Architecture Design.drawio` (diagram wins). Spec Sheet (RAJ) + `contracts/FRONTEND_CONTRACT.md` interpret it. Historical RVAI benchmarks are prototype evidence only.

## Ownership map (kept folder names ↔ runtime layout)

| Spec / runtime block | This repo |
| --- | --- |
| `api` | `backend/app.py` |
| `application` | `backend/coordinator.py`, `backend/observations.py` |
| `domain` | `shared/` + `contracts/` |
| `safety` | `software_guardrails/` |
| `ai` | `ai_pipeline/` |
| `matter` | `matter_bridge/` (`MatterPort`) |
| `state` (display cache) | Purshottam — untouched `web/` / `hardware_telemetry/` |

## V1 scope

- Commands: one target, `ON` / `OFF` / `STATUS` only
- Wire: `{"target","cmd"}` → outcome `result` + `actual` / `fault` / `fault_available` / `fresh`
- Safety: schema + configured/enabled/commissioned target + supported action (no fault lockout / rate limit until approved)
- Confirmation: observation sequence > dispatch baseline; contradictory reports wait until timeout; no auto-retry
- Targets: AI knows all zones; only commissioned `node_id` values may actuate (`config/targets.yaml`)

## Quick start

```powershell
cd "d:\Software Skeleton"
pip install -e ".[dev]"
pytest -v
```

```powershell
python -m ai_pipeline.cli "turn on the galley"
python -m ai_pipeline.cli --tap kitchen ON
uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload
```

Open `http://127.0.0.1:8000/docs`.

## Real path (no product simulator)

```
voice/text/tap
  → AI Pipeline (proposal) + Safety Gate (allow/block)
  → {"target","cmd"} on Jetson only
  → MatterPort (chip-tool | matter_server)  →  Matter On/Off
  → OTBR + RCP  →  Thread  →  firmware
  ← OnOff report / read
  → outcome JSON to CLI / tablet / Piper   (this is NOT sent to OTBR)
```

1. One-plug chip-tool trial: `docs/CHIPTOOL_ONE_PLUG_TRIAL.md`
2. Set `node_id` / `endpoint_id` for that zone; leave others `null`
3. Default: `RVAI_MATTER_BACKEND=chip_tool`. Later: `matter_server` on loopback only.
4. Voice: `RVAI_STT_BACKEND=whisper_cpp` + Piper paths; `RVAI_TTS_PLAY=true` on Jetson speakers

Without OTBR/`chip-tool`, CLI taps will fail honestly instead of faking confirmation.

## Decision log

See `docs/DECISION_LOG.md`.
