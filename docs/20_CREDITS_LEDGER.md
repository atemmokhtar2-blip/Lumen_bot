# Credits Ledger — Double-Entry (Phase 1 production bar)

## Model

Every mutation is a **balanced transaction** (Σ debit = Σ credit) with append-only legs.

| Account | Role |
|---------|------|
| `wallet:{tenant}` | User credits |
| `hold:{tenant}` | Memorandum holds |
| `system:treasury` | Funding source |
| `system:revenue` | Recognized usage |
| `system:holds` | Platform hold control |

## Operations

- **purchase/credit**: DR treasury / CR wallet  
- **deduct**: DR wallet / CR revenue  
- **reserve**: DR hold:tenant / CR system:holds (+ reserved_balance)  
- **release**: reverse reserve legs  
- **capture**: release hold legs + DR wallet / CR revenue  

## Safety

- Immutable ledger (PG triggers block UPDATE/DELETE)
- `idempotency_key` unique, min length 8
- `FOR UPDATE` + conditional wallet UPDATE
- SHA-256 **hash chain** (`prev_hash` → `entry_hash`)
- `reconcile()`: wallet net from legs == `current_balance`; no unbalanced txs
- Amount cap `1e12` per operation

## Gate

`CreditService` only. Phase 2 metrics must not write balances.
