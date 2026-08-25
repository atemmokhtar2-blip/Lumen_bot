# Credits Ledger — ADR (Phase 0 + 1)

## Decision

Usage billing uses an **append-only credit ledger** + wallet balances.
Stripe subscriptions remain for *plan purchase*; they do not mutate balance
except via an explicit `purchase` ledger entry (Phase 5).

## Units

- Smallest unit: integer **credit** (never float).
- `available = current_balance - reserved_balance` (enforced in application).

## Tables

| Table | Role |
|-------|------|
| `credit_wallets` | One row per tenant; `current_balance`, `reserved_balance` |
| `credit_ledger` | Append-only movements; unique `idempotency_key` |
| `credit_pricing_rules` | Resource → cost_per_unit |

## Single write gate

Only `CreditService` methods may change wallet balances:

- `credit_credits` — top-up / purchase / refund
- `deduct_credits` — consumption
- `reserve_credits` / `release_reservation` / `capture_reservation`

## Non-goals (later phases)

- Metering batches, rating worker, grace suspension, admin UI.

## Storage

- Production: PostgreSQL (`DATABASE_URL`)
- Tests / offline: in-memory store with identical semantics
