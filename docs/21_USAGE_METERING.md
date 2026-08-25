# Phase 2 — Usage batches (hardened)

## Guarantees

| Rule | Enforcement |
|------|-------------|
| No credit debit | Ingest never imports deduct |
| Tenant isolation | `tenant_id` from API auth only |
| Bot ownership | `usage_bot_registry`; 403 if unknown bot |
| Idempotency | unique `idempotency_key` |
| Integrity | SHA-256 `content_hash` of metrics |
| Window safety | reject future / stale / >24h span |
| Immutability | PG trigger blocks UPDATE/DELETE |
| Rate limit | `TBE_USAGE_INGEST_RPM` (default 60) |
| Host samples | `docker stats` + inspect uptime when container_id set |

## API

- `POST /v1/usage/register_bot` `{ "bot_id" }` — bind bot to tenant
- `POST /v1/usage/batch` — ingest metrics
- `GET /v1/usage/batches` — list

## Supervisor

`list_managed_containers` inspects labels (`tbe.tenant_id`, `tbe.bot_id`).
`emit_host_heartbeat` registers bot, samples stats, writes batch.

Dev only: `TBE_USAGE_RELAX_OWNERSHIP=1` skips ownership check.
