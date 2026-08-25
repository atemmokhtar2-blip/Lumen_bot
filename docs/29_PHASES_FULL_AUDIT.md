# تدقيق كامل للمراحل 1–4 (محركات حقيقية)

تاريخ التدقيق: بعد إصلاح صرامة ZAP (fail على warnings) و Trivy config fail-closed.

## تصنيف المكوّنات

| نوع | أمثلة | مسموح؟ |
|-----|--------|--------|
| **محرك رسمي** | Gitleaks, Bandit, Semgrep, CodeQL, Trivy, ZAP, Syft, Grype, OSV, Checkov, KICS, Hadolint, OPA/Conftest, Cosign | نعم — المصدر |
| **منطق منتج** | pytest IDOR, `lumen/api/ownership.py`, live_idor_http | نعم — عزل tenants ليس بديل ZAP |
| **تجهيز هدف** | `start_api_dast.py`, `seed_dast_tenants.py` | نعم — يشغّل الهدف للمحرك |
| **قارئ تقرير محرك** | `zap_fail_on_severity.py` | نعم — يقرأ JSON من ZAP |

## المرحلة 1 — `security.yml` → gate: `Phase-1 security gate`

| Job | المحرك | الاستدعاء | Fail closed؟ |
|-----|--------|-----------|--------------|
| secrets | **Gitleaks** | `gitleaks/gitleaks-action@v2` | نعم |
| dependencies | **pip-audit** + CycloneDX | PyPA pip-audit على requirements.txt | نعم عند CVE |
| sast-bandit | **Bandit** | bandit -lll على مسارات حرجة | نعم على HIGH |
| sast-semgrep | **Semgrep** | p/owasp-top-ten + semgrep/ | نعم على ERROR |
| codeql | **CodeQL** | github/codeql-action security-extended | نعم |
| trivy | **Trivy** fs + config | aquasecurity/trivy-action | نعم (config بعد الإصلاح) |
| scorecard | **OpenSSF Scorecard** | ossf/scorecard-action | على push لـ main |
| credits-integrity | pytest منطق credits | ليس محرك CVE | نعم للاختبارات |
| api-baseline | بوابة وجود أدوات | تحقق ملفات | نعم |

## المرحلة 2 — `dast-zap.yml` → gate: `Phase-2 DAST gate`

| خطوة | المحرك / الدور | حقيقي؟ |
|------|-----------------|--------|
| unit-idor | pytest IDOR + ownership | منطق منتج |
| start API | aiohttp app حي على :8765 | هدف |
| seed tenants | POST /v1/tenants + admin | هدف |
| live_idor_http | HTTP بمفتاحين | منطق منتج على شبكة حقيقية |
| **ZAP baseline** | `ghcr.io/zaproxy/zaproxy:stable` `zap-baseline.py` | **محرك رسمي** |
| **ZAP API scan** | `zap-api-scan.py` + OpenAPI | **محرك رسمي** |
| **ZAP auth** | baseline + Replacer Bearer | **محرك رسمي** |
| fail MEDIUM+ | قراءة تقرير ZAP | بعد المحرك |
| صرامة exit | **exit ≠ 0 يفشل** (بعد الإصلاح) | نعم |

## المرحلة 3 — `supply-chain.yml` → gate: `Phase-3 admission gate`

| Job | المحرك |
|-----|--------|
| dependency-review | **GitHub Dependency Review** |
| osv-scanner | **Google OSV** `ghcr.io/google/osv-scanner` |
| syft-sbom | **Anchore Syft** |
| grype | **Anchore Grype** HIGH+ |
| trivy-secrets | **Trivy** scanners=secret |
| build-sign-scan | docker build + **Trivy image** + **Cosign** + attest |
| admission-gate | يجمع النتائج |

Dockerfile: non-root + HEALTHCHECK.

## المرحلة 4 — `policy-as-code.yml` → gate: `Phase-4 policy gate`

| Job | المحرك |
|-----|--------|
| hadolint | **Hadolint** |
| actionlint | **actionlint** + ShellCheck |
| shellcheck | **ShellCheck** على scripts/ |
| checkov | **Checkov** soft_fail=false |
| kics | **KICS** fail medium |
| conftest | **OPA Conftest** + policy/*.rego |
| trivy-config | **Trivy** config MEDIUM+ |
| phase4-gate | يجمع السبعة |

## مسار IDOR في الكود (منتج)

| ملف | المهمة |
|-----|--------|
| `lumen/api/ownership.py` | reject_identity_spoof, normalize_tenant_id, assert_job_owned |
| `lumen/api/routes/jobs|hosts|generate|billing|tenants|audit` | استدعاء الملكية/الـ spoof |
| `tests/test_security_idor_dast.py` | مصفوفة مسار كاملة |
| `scripts/security/live_idor_http.py` | نفس العزل على HTTP حي |

## ما تبقّى خارج الكود (منصة GitHub)

- تفعيل **Rulesets** من `.github/rulesets/main-protection.json`
- Require status checks: Phase-1/2/3/4 gates
- Secret scanning / push protection من إعدادات المستودع
