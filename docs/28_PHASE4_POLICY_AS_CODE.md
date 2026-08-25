# المرحلة 4 — Policy-as-Code

بعد:
1. SAST/secrets (`security.yml`)
2. IDOR + ZAP DAST (`dast-zap.yml`)
3. Supply chain (`supply-chain.yml`)

## محركات رسمية فقط

| المحرك | الجهة | ماذا يفحص |
|--------|--------|-----------|
| **Hadolint** | hadolint | أفضل ممارسات Dockerfile |
| **actionlint** | rhysd | صحة وأمان ملفات GitHub Actions |
| **Checkov** | Prisma / Bridgecrew | Dockerfile + Actions + secrets misconfig |
| **KICS** | Checkmarx | IaC / Docker / GitHub misconfig (HIGH fail) |

لا سكربت بديل لـ Checkov أو KICS أو Hadolint أو actionlint.

## بوابة القبول

Job: **`Phase-4 policy gate`** — يفشل إن فشل أي محرك.

## حماية الفرع (منصة GitHub — مش سكربت مسح)

القالب: `.github/rulesets/main-protection.json`

يُطبَّق من:
- Settings → Rules → Rulesets → Import، أو
- `gh api` بصلاحية admin (رسمي GitHub CLI)

يفرض مراجعة CODEOWNERS + status checks للمراحل 3 و 4 و ZAP.
