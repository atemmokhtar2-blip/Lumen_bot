# Phase 2 — Usage batches (telemetry only)

## Scope

Ingest **metrics batches** from hosted bots / supervisors.
**Does not** call `CreditService.deduct_*` (that is phase 3).

## Batch contract

```json
{
  "bot_id": "bot_xxx",
  "window_start": 1710000000.0,
  "window_end": 1710000300.0,
  "messages_processed": 12,
  "llm_tokens_used": 400,
  "uptime_seconds": 300,
  "ram_mb": 256,
  "cpu_millicores": 100,
  "idempotency_key": "batch-bot_xxx-1710000300"
}
```

`tenant_id` comes from authenticated API key (never trusted from body).

## Storage

- `usage_batches` append-oriented rows
- Unique `idempotency_key` → duplicate posts return replay, no double store
- Status: `accepted` | `rated` (rated set in phase 3)

## Emitters

- Hosting worker / supervisor tick may call `emit_host_heartbeat(...)` locally
- Bots may POST `/v1/usage/batch` with tenant API key
