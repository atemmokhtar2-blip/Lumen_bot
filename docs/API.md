# B2B API (from code)

App factory: `lumen/api/app.py` (aiohttp).

Defaults pushed in factory when unset:

- `TBE_MULTI_TENANT=1`
- `TBE_REQUIRE_DOCKER=1`
- `TBE_LOCAL_FALLBACK_WHEN_NO_DOCKER=1`
- `TBE_PIP_WHEELS_ONLY=1`

CORS: allowlist via `API_CORS_ORIGIN` (no `*` in production unless explicit unsafe flags in dev).

## Routes (selected)

| Method | Path | Module |
|--------|------|--------|
| POST | `/v1/generate` | `routes/generate` — enqueue job, return task id |
| GET | `/v1/jobs`, `/v1/jobs/{id}` | jobs |
| POST | `/v1/jobs/{id}/cancel\|pause\|resume\|steer` | jobs |
| GET | `/v1/jobs/{id}/events` | job event stream |
| GET | `/v1/jobs/{id}/files`, `/file` | runs_ux |
| POST | `/v1/hosts/start\|stop\|diagnose` | hosts |
| GET | `/v1/hosts` | hosts |
| GET | `/v1/usage`, billing/balance, invoices, checkout | billing |
| GET | `/v1/dashboard` | dashboard |
| GET/POST | `/v1/me/*`, credits audit admin | tenants / audit |
| GET | health | health |

Auth: tenant key via `require_tenant`; ownership checks against IDOR (`ownership.py`).

Generate enforces body size, description length, per-tenant RPM, billing gate, then job queue.
