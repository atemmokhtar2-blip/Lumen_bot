# محركات الأمان الحقيقية (Not scripts)

| الهدف | المحرك الحقيقي | أين يعمل |
|--------|----------------|----------|
| Secrets | **Gitleaks** (`gitleaks/gitleaks-action`) | `security.yml` |
| Dependency CVE | **pip-audit** (PyPA) | `security.yml` + `requirements-security.txt` |
| Python SAST | **Bandit** (PyCQA) | `security.yml` |
| SAST rules / OWASP | **Semgrep** (`p/owasp-top-ten`, `p/security-audit`) | `security.yml` |
| Deep SAST | **GitHub CodeQL** `security-extended` | `security.yml` |
| FS / container / IaC | **Trivy** (Aqua) | `security.yml` |
| Supply chain posture | **OpenSSF Scorecard** | `security.yml` |
| Live DAST | **OWASP ZAP** image `ghcr.io/zaproxy/zaproxy:stable` | `dast-zap.yml` |
| API DAST from contract | **ZAP `zap-api-scan.py`** + OpenAPI | `dast-zap.yml` |

## ما ليس محركاً عاماً (مقصود)

| سكربت | الدور |
|--------|--------|
| `tests/test_security_idor_dast.py` | منطق أعمال المنصة (عزل tenants) — لا بديل ZAP له |
| `live_idor_http.py` | IDOR بمفتاحين على HTTP حي |
| `security_baseline_check.py` | بوابة ثابتة أن الأدوات/القواعد موجودة |

DAST العام = **ZAP فقط**. اختبارات IDOR = منطق المنتج.
