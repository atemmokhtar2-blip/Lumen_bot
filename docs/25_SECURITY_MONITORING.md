# مراقبة الثغرات — World-Class Security Monitoring

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

## قواعد Semgrep الخاصة (Maestro)

- منع `verify=False`
- منع أسرار مضمّنة
- منع `shell=True` / `eval()` في مسارات الإنتاج

## API hardening

- `security_headers_middleware`: nosniff, DENY frame, CSP, Permissions-Policy, HSTS on HTTPS
- CORS: deny-by-default (لا `*` في الإنتاج)
- Admin credits: `require_admin` فقط
