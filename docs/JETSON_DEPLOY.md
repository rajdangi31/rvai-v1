# Phase G — Jetson deploy notes (stub)

Cold-boot checklist for Raj's services on the Orin Nano Super.

## Process layout

| Service | Bind | Notes |
| --- | --- | --- |
| OTBR + RCP | host | Thread border router |
| Matter controller (chip-tool trial → Matter Server) | `127.0.0.1` only | Never expose publicly |
| Ollama (`qwen3.5:4b`) | `127.0.0.1:11434` | Local LLM |
| FastAPI backend | LAN for tablet | `/api/command`, `/api/text`, `/api/audio`, `/api/state` |

## Suggested units (outline)

1. `otbr.service` — border router
2. `matter-server.service` — loopback `:5580`
3. `ollama.service` — model preload
4. `rvai-backend.service` — `uvicorn backend.app:app --host 0.0.0.0 --port 8000`

Fabric credentials and commissioning state live **outside** the git tree. Do not log secrets.

## Health

- `GET /api/health` — liveness + backend modes
- `GET /api/ready` — 200 only after Matter start + startup reads attempted

After cold boot, UI should show unknown/stale until startup reads succeed, then fresh observations.
