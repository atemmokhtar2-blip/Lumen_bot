# Credits Ledger — ADR (Phase 0 + 1 hardened)

## Decision

Usage billing uses an **append-only credit ledger** + wallet balances.
Stripe stays for plan purchase; credits move only via `CreditService`.

## Invariants

1. `available = current_balance - reserved_balance >= 0`
2. `reserved_balance <= current_balance`
3. Ledger is append-only (`amount` and/or `reservation_delta` non-zero)
4. `SUM(ledger.amount) == wallet.current_balance` (reconcile)
5. `SUM(ledger.reservation_delta) == wallet.reserved_balance` (reconcile)
6. Same `idempotency_key` → one effect only

## Operations

| Method | current | reserved | ledger |
|--------|---------|----------|--------|
| credit_credits | +N | — | amount=+N |
| deduct_credits | −N (from available) | — | amount=−N |
| reserve_credits | — | +N | reservation_delta=+N |
| release_reservation | — | −N | reservation_delta=−N |
| capture_reservation | −N | −N | amount=−N, reservation_delta=−N |

## Gate

Only `CreditService` mutates balances. Production: `PostgresCreditsStore` + `FOR UPDATE`.

## Phase 2 readiness

Phase 2 may emit usage batches **without** calling deduct until phase 3 rating worker uses this gate.
