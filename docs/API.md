# B2B API (from code)

App factory: `lumen/api/app.py` (aiohttp).

Isolation / package defaults are **not** written into `os.environ` by the API factory.

Readers apply fail-closed defaults when env is unset:

- `isolation_policy.is_multi_tenant()` → default multi-tenant on
- `isolation_policy.decide_isolation()` → multi-tenant/production never allow host LocalProcess
- `TBE_PIP_WHEELS_ONLY` defaulted at use sites in live_runner (wheels-only)
- `APISettings` (`lumen/api/settings.py`) documents B2B knobs without mutating the process env

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
