# Phase 4 — Zero-balance graceful degradation

## Flow

1. After successful rating debit → `on_balance_changed`
2. 80/90/95% of baseline → alert
3. available<=0 or insufficient rating → grace (`TBE_BALANCE_GRACE_SEC`)
4. Grace expired → suspend managed bots
5. Top-up → clear suspension + baseline

## Host start

Reject if suspended (402). Pre-auth reserve_for_hosting.
