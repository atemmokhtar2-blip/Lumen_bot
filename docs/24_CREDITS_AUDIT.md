# Phase 5 — Credits audit

## Guarantees verified

| Check | Where |
|-------|--------|
| Idempotency keys unique | ledger_audit page scan + DB unique |
| Hash chain | ledger_audit chronological |
| Double-entry balance | CreditService.reconcile |
| Admin isolation | require_admin on /v1/admin/credits/* |
| Tenant self-service | /v1/me/credits/* |

## API

### Tenant
- `GET /v1/me/credits/ledger?limit=&type=`
- `GET /v1/me/credits/reconcile`
- `GET /v1/me/credits/overview`

### Admin (`X-Admin-Token`)
- `GET /v1/admin/credits/{tenant_id}/overview`
- `GET /v1/admin/credits/{tenant_id}/ledger`
- `GET /v1/admin/credits/{tenant_id}/reconcile` → 409 if drift
