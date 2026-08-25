# المرحلة 3 — Supply chain & release admission

بعد المرحلة 1 (SAST/secrets/CI) والمرحلة 2 (IDOR + OWASP ZAP DAST):

## محركات رسمية فقط

| المحرك | الناشر | الوظيفة | Workflow |
|--------|--------|---------|----------|
| **Dependency Review** | GitHub | منع دمج PR يدخل CVE معروفة في التبعيات | `supply-chain.yml` |
| **Syft** | Anchore | توليد SBOM (SPDX + CycloneDX) | `supply-chain.yml` |
| **Grype** | Anchore | مطابقة ثغرات على المجلد/SBOM — fail على HIGH | `supply-chain.yml` |
| **Trivy image** | Aqua | بناء `Dockerfile` ثم مسح الصورة — fail على CRITICAL/HIGH | `supply-chain.yml` |

لا يوجد سكربت بديل لـ Grype/Syft/Trivy/Dependency Review.

## ترتيب المراحل

1. **Phase 1** — `security.yml`: Gitleaks, pip-audit, Bandit, Semgrep, CodeQL, Trivy fs, Scorecard  
2. **Phase 2** — `dast-zap.yml`: OWASP ZAP docker + IDOR حي  
3. **Phase 3** — `supply-chain.yml`: Dependency Review + Syft + Grype + Trivy image  

## إقرار الدمج (يدوي على GitHub)

Settings → Branches → `main` → Require status checks:

- `Security` / jobs الحرجة  
- `DAST ZAP`  
- `Supply Chain` / `Grype` + `Trivy image`  

هذا إعداد منصة GitHub وليس سكربت في المستودع.
