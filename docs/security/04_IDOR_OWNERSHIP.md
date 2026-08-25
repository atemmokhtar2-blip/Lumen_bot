# IDOR & ownership — wiring checklist

## Module: `lumen/lumen/api/ownership.py`

| Function | Use when |
|----------|----------|
| `reject_identity_spoof(body, tenant_id=...)` | Any authenticated JSON body |
| `normalize_tenant_id(raw)` | Admin path `{tenant_id}` |
| `assert_job_owned(job, tenant_id)` | GET job by id |
| `assert_host_owned(instance, user_id)` | Host instance ops |

## Routes already wired (maintain this list)

| Route module | Guards |
|--------------|--------|
| `lumen/lumen/api/routes/generate.py` | require_tenant + reject_identity_spoof |
| `lumen/lumen/api/routes/hosts.py` | spoof + path sandbox + host ownership on stop |
| `lumen/lumen/api/routes/jobs.py` | assert_job_owned + strip input |
| `lumen/lumen/api/routes/billing.py` | spoof on mutating + credits amount cap |
| `lumen/lumen/api/routes/tenants.py` | spoof on white-label; create requires admin |
| `lumen/lumen/api/routes/audit.py` | require_admin + normalize_tenant_id |

## New route template

```python
async def my_handler(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    body = await safe_json_body(request, max_bytes=65536)
    reject_identity_spoof(body, tenant_id=tenant.tenant_id)
    # use tenant.tenant_id only
    ...
```
