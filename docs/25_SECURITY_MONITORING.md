# مراقبة الثغرات — Security Monitoring

> **Maintenance index (modular):** [docs/security/README.md](security/README.md)  
> **Developer strict rules:** [docs/security/00_DEVELOPER_RULES.md](security/00_DEVELOPER_RULES.md)


## طبقات الدفاع (Defense in Depth)

| # | الطبقة | الأداة | التكرار |
|---|--------|--------|---------|
| 1 | Secrets | Gitleaks | كل PR / push |
| 2 | Dependency CVE | pip-audit + CycloneDX SBOM | كل PR / push |
| 3 | SAST Python | Bandit (fail on HIGH) | كل PR / push |
| 4 | SAST قواعد مخصصة | Semgrep (`semgrep/`) + OWASP ERROR | كل PR / push |
| 5 | Deep SAST | CodeQL `security-extended` | كل PR / push |
| 6 | FS / Image / IaC | Trivy | كل PR / push |
| 7 | Supply-chain posture | OpenSSF Scorecard | يومي / main |
| 8 | منطق المال | pytest credits + privilege | كل PR / push |
| 9 | Runtime ledger | `credits_health_monitor` | يومي 03:00 UTC |
| 10 | Static baseline | `security_baseline_check.py --strict` | كل PR / push |

## GitHub Security tab

SARIF يُرفع من: CodeQL، Trivy، Scorecard (عند تفعيل `security-events`).

## محلياً قبل الـ push

```bash
bash scripts/security/run_local_scans.sh
python scripts/security/security_baseline_check.py --strict
pytest tests/test_security_baseline.py tests/test_welcome_credits.py -q
```

## متغيرات / Secrets

| الاسم | الاستخدام |
|-------|-----------|
| `DATABASE_URL` | مسح promo/drift على Postgres |
| `PLATFORM_ADMIN_TOKEN` | بوابة admin fail-closed |
| `CREDITS_MONITOR_FAIL_ON_DRIFT` | افتراضي 1 |

## قواعد Semgrep الخاصة (Lumen)

- منع `verify=False`
- منع أسرار مضمّنة
- منع `shell=True` / `eval()` في مسارات الإنتاج

## API hardening

- `security_headers_middleware`: nosniff, DENY frame, CSP, Permissions-Policy, HSTS on HTTPS
- CORS: deny-by-default (لا `*` في الإنتاج)
- Admin credits: `require_admin` فقط

## Offensive layer (not scanners)

| Artifact | Role |
|----------|------|
| `tests/test_security_attack_surface.py` | Auth bypass, admin probe, path traversal, promo abuse, policy fail-closed, HTTP 401 gates |
| `lumen.platform/security_events.py` | Append-only JSONL runtime events (`auth.admin_rejected`, …) |
| `.github/workflows/security-attack.yml` | Must stay green on every PR |
| `.pre-commit-config.yaml` | gitleaks + bandit + baseline + attack tests before commit |
| `.github/CODEOWNERS` | Review gate on security-critical paths |

```bash
pytest tests/test_security_attack_surface.py -q
```


## IDOR + DAST (layer after attack-surface)

| Artifact | What it proves |
|----------|----------------|
| `tests/test_security_idor_dast.py` | Tenant A cannot admin-read B; `/v1/me` isolation; forged Stripe webhook; method fuzz; injection paths; oversized body → 413; dev activate locked |
| `scripts/security/dast_api_probe.py` | Standalone probe, exit ≠ 0 on any unexpected 2xx |

Also fixed production bug: `HTTPRequestEntityTooLarge` missing `max_size` (was 500 on big body).


## World-class IDOR matrix (layer 2 hardened)

Covers **every** tenant-authenticated route from `lumen/api/app.py`:

- Unauth matrix (GET/POST/PUT/DELETE) → never 2xx on sensitive paths
- Tenant key + spoofed X-Admin-Token → never admin
- `/v1/me` strict identity + no cross-tenant id leak in JSON
- Credits overview/ledger/reconcile/balance isolation
- **Job IDOR**: planted job of A returns 404 to B; list_jobs hides it
- usage / invoices / dashboard no cross leak
- Mass-assignment on white-label cannot set plan_id
- create_tenant + dev_activate privilege escalation locked
- Auth header confusion (empty bearer, admin as bearer, X-Api-Key)
- Stripe webhook forgery cannot mint credits
- Injection path matrix on admin + jobs
- Oversized generate → 413 (not 500)
- Parallel deduct race → no negative balance
- rotate_key isolates tenants

```bash
pytest tests/test_security_idor_dast.py -q
python scripts/security/dast_api_probe.py
```


## Layer complete: IDOR + live ZAP DAST

| Item | Artifact |
|------|----------|
| IDOR (two tenants, ownership, spoof) | `tests/test_security_idor_dast.py` + `lumen/api/ownership.py` |
| In-process DAST probe | `scripts/security/dast_api_probe.py` |
| **Live API + OWASP ZAP baseline** | `.github/workflows/dast-zap.yml` |
| ZAP rules | `.zap/rules.tsv` |
| Local live runner | `bash scripts/security/run_live_dast.sh` |

CI starts `scripts/security/start_api_dast.py` on `127.0.0.1:8765`, waits for `/health`,
runs unauth smoke, then **zaproxy/action-baseline** against the live process.


## World-class live DAST (complete)

| Stage | What |
|-------|------|
| 1 | Start live API `:8765` |
| 2 | Seed **two tenants** via `POST /v1/tenants` + admin token |
| 3 | **Live HTTP IDOR** (`live_idor_http.py`) with real keys |
| 4 | **OWASP ZAP baseline** spider/active light |
| 5 | **OWASP ZAP API scan** against `/openapi.yaml` |
| 6 | Parse reports — block on **MEDIUM + HIGH** |

Artifacts: `.github/workflows/dast-zap.yml`, `.zap/rules.tsv`, `seed_dast_tenants.py`, `live_idor_http.py`.
