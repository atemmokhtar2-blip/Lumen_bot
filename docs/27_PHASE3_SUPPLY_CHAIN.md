# المرحلة 3 — Supply chain (مشدّدة)

محركات **رسمية فقط** — لا سكربتات مسح بديلة.

## البوابات (كلها fail-closed على HIGH/CRITICAL حيث ينطبق)

| # | المحرك | الجهة | الوظيفة |
|---|--------|--------|---------|
| 1 | **Dependency Review** | GitHub | PR: منع moderate+ CVE في التبعيات الجديدة |
| 2 | **OSV-Scanner** | Google | قاعدة OSV لكل الحزم |
| 3 | **Syft** | Anchore | SBOM SPDX + CycloneDX (إلزامي غير فارغ) |
| 4 | **Grype** | Anchore | ثغرات HIGH+ على الشجرة |
| 5 | **Trivy secrets** | Aqua | أسرار في الشجرة |
| 6 | **docker build** | Docker | صورة من Dockerfile hardened |
| 7 | **Trivy image** | Aqua | CVE + secrets على الصورة |
| 8 | **Cosign** | Sigstore | توقيع keyless (OIDC) على main |
| 9 | **attest-build-provenance** | GitHub | إثبات بناء |
| 10 | **admission-gate** | CI | يفشل إن فشل أي محرك إلزامي |

## Dockerfile hardened

- `python:3.12-slim-bookworm`
- مستخدم غير root `appuser` uid 10001
- `.dockerignore` يستبعد `.git` / `.env` / tests
- لا build-args للأسرار

## Dependabot

- pip **يومي**
- actions + docker أسبوعي

## إقرار الدمج على GitHub

Require status check: **`Phase-3 admission gate`**.
