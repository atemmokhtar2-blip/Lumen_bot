# Phase 4 — Balance lifecycle (hardened)

State machine: active → warning → grace → suspended → active

- Grace warnings every TBE_BALANCE_GRACE_WARN_SEC
- Snapshot bots before stop
- Optimistic concurrency version
- Host start fail-closed 503 if gate errors (non-dev)
- GET /v1/billing/balance
