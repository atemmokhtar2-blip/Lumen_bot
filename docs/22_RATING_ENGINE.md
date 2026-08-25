# Phase 3 — Rating engine (hardened)

## Guarantees

| Rule | How |
|------|-----|
| Single charge per batch | `UNIQUE(batch_id)` claim → debit → finalize |
| No double debit under race | claim first; losers skip; debit idempotent `rate-{batch_id}` |
| Prefer holds | `capture_reservation` when `reserved >= cost` |
| Cap | `TBE_RATING_MAX_CREDITS_PER_BATCH` (default 100000) |
| Insufficient funds | `usage_rating_failures` + abort claim (retryable) |
| Batches immutable | ratings table separate |

## Flow

1. `try_begin_rating` (pending row / memory claim)
2. `compute_batch_cost`
3. capture or deduct via **CreditService only**
4. `finalize_rating` or `abort_claim` + `record_failure`

## API

- `GET /v1/usage/ratings` — tenant rating history
