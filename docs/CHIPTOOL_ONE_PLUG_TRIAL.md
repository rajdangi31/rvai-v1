# Phase E — chip-tool one-plug trial

Authority: Spec Sheet (RAJ) §11 and `ARCHITECTURE_BASELINE.md`.
Prove the Jetson → Matter-over-Thread path **before** attaching AI.

## Prerequisites

- Jetson Orin Nano Super with OTBR (`ot-br-posix`) + nRF52840 RCP
- `chip-tool` on PATH
- One Matter-over-Thread smart plug (or commissioned BL54L15 endpoint)
- Backend uses `RVAI_MATTER_BACKEND=chip_tool` (no product simulator)

## Procedure

1. Commission the plug and record `node_id` + discovered OnOff `endpoint_id`.
2. Set only that zone in `config/targets.yaml` (`node_id` / `endpoint_id`); leave others `null`.
3. Run:

```bash
chip-tool onoff read on-off <node> <endpoint>
chip-tool onoff on <node> <endpoint>
chip-tool onoff read on-off <node> <endpoint>
chip-tool onoff off <node> <endpoint>
chip-tool onoff read on-off <node> <endpoint>
```

4. Toggle the plug manually and re-read OnOff.
5. Disconnect RCP / OTBR, confirm reads fail; reconnect; read again.
6. Restart chip-tool / controller process; rediscover/read before trusting state.
7. Record latency (command → matching read) and set `RVAI_CONFIRM_TIMEOUT_SECONDS` from measured p95 + margin.

## Backend switch

```ini
RVAI_MATTER_BACKEND=chip_tool
RVAI_CHIP_TOOL_BINARY=chip-tool
```

Then:

```powershell
python -m ai_pipeline.cli --tap kitchen ON
python -m ai_pipeline.cli --tap kitchen STATUS
```

After chip-tool is proven, switch to the Matter Server WebSocket client:

```ini
RVAI_MATTER_BACKEND=matter_server
RVAI_MATTER_SERVER_WS_URL=ws://127.0.0.1:5580/ws
```

Keep the controller on loopback only. Do not claim fault integration until Arjun agrees transport.
