# Frontend/backend contract v0.1

Authority: `RVAI/runtime/contracts/FRONTEND_CONTRACT.md`. Copied here so Software Skeleton stays self-contained.

One target per command. Raj owns backend execution; Purshottam owns rendering/cache consumer. Actual is device-observed state, never desired state.

## POST /api/command

Request: `{"target":"kitchen","cmd":"ON"}`. `cmd` is ON, OFF, or STATUS. Reject unknown fields/invalid types. Target must exist in configured registry.

Successful HTTP exchange returns an application outcome after observation or deadline:

```json
{"target":"kitchen","result":"confirmed","actual":"ON","fault":null,"fault_available":false,"fresh":true}
```

`result`: confirmed | blocked | failed | unconfirmed. `actual`: ON | OFF | null. Optional `message` explains non-success. `fresh` describes included actual, not fault availability. For STATUS, confirmed means a current device read was received. For ON/OFF it means a new observation established requested state.

Validation errors: HTTP 422; target busy: HTTP 409; backend not ready: HTTP 503. Once submitted, a lost HTTP connection leaves completion uncertain: do not retry actuation automatically.

## WebSocket /api/state

On connect send:

```json
{"type":"snapshot","states":[{"target":"kitchen","actual":null,"fault":null,"fault_available":false,"fresh":false}]}
```

On state change send:

```json
{"type":"state","state":{"target":"kitchen","actual":"ON","fault":null,"fault_available":false,"fresh":true}}
```

## POST /api/text

Request: `{"text":"Turn on the kitchen light"}`. AI resolves a proposal then uses the same command service/safety path. Clarification: `{"result":"clarification","message":"Which light?"}`.

## Not included

Brightness, All/batch controls, tablet audio streaming, fixed zone/node IDs, and voltage/current contracts. Never infer fault-free from `fault_available=false`.
