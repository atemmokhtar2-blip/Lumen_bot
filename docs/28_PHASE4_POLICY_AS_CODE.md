# المرحلة 4 — Policy-as-Code (مشدّدة)

## محركات رسمية (7)

| المحرك | الجهة | الصرامة |
|--------|--------|---------|
| **Hadolint** | hadolint | fail من **style** |
| **actionlint** | rhysd | مع **ShellCheck** مدمج |
| **ShellCheck** | koalaman | كل `scripts/` — severity warning |
| **Checkov** | Prisma | `soft_fail: false`، بدون skip واسع |
| **KICS** | Checkmarx | fail من **medium** |
| **Conftest** | Open Policy Agent | سياسات Rego على Dockerfile |
| **Trivy config** | Aqua | misconfig CRITICAL/HIGH/MEDIUM |

بوابة: **`Phase-4 policy gate`** — السبعة لازم ينجحوا.

## سياسات OPA (`policy/`)

- منع `USER root`
- إلزام `USER` غير root
- منع `ADD`
- إلزام `HEALTHCHECK`

## Dockerfile

يشمل `HEALTHCHECK` + مستخدم `appuser` 10001.

لا سكربت بديل لأي من المحركات أعلاه.
