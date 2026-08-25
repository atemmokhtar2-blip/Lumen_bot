# Phase 3 — Rating & deduction

## Flow

```
usage_batches (accepted, immutable)
        │
        ▼
RatingEngine.rate_pending()
        │  compute_batch_cost(pricing_rules)
        ▼
CreditService.deduct_credits(...)   ← sole debit gate
        │
        ▼
usage_ratings (append-only, unique batch_id)
```

## Cost mapping

| Metric | Rule |
|--------|------|
| messages_processed | `telegram_message` |
| llm_tokens_used | `llm_output_token` |
| uptime_seconds | `hourly_hosting` (pro-rated, min 1 if uptime>0) |
| ram_mb × hours | `docker_ram_mb_per_hour` |

## Pre-auth

`reserve_for_hosting(tenant, hours, ram_mb)` before host start.
Actual usage later `deduct` or `capture_reservation`.

## Idempotency

`idempotency_key = rate-{batch_id}` on both debit and rating row.
