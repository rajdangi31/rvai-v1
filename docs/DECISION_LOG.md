# Decision log (Raj)

| Date | Topic | Decision | Owner |
| --- | --- | --- | --- |
| 2026-11-10 | Package layout | Keep `ai_pipeline/`, `software_guardrails/`, `backend/`, `matter_bridge/`, `shared/` names; map to runtime blocks in README | Raj |
| 2026-11-10 | Matter controller | chip-tool one-plug trial first, then Matter Server WS client already in tree; defer Matter.js | Raj |
| 2026-11-10 | No product simulator | Removed `RVAI_MATTER_BACKEND=simulator`; default `chip_tool`. Test-only `FakeMatterPort` lives under `tests/fakes/` | Raj |
| 2026-11-10 | Safety V1 | Remove fault-blocks-ON and toggle rate limit until Jason/Arjun/Jay approve electrical rules | Raj |
| 2026-11-10 | Wire contract | Adopt FRONTEND_CONTRACT.md v0.1 (`result`, `fault_available`, WS `states`/`state`, 409/422/503) | Raj |
| TBD | Fault transport | How firmware exposes faults over Matter; clearing rules | Arjun + Raj |
| TBD | Feedback semantics | OnOff attribute vs latching-relay feedback pin | Arjun |
| TBD | Arbitration timing | Rocker > Jetson > CAN window / override duration | Arjun |
| TBD | Confirm timeout | Replace 5s default with measured hardware p95 | Raj after Phase E |
