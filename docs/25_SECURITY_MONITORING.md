# مراقبة الثغرات — Security Monitoring

## CI (كل push / PR)

| Job | أداة | يفشل عند |
|-----|------|----------|
| Secrets | gitleaks | أسرار في التاريخ/الـ diff |
| Dependencies | pip-audit | CVE معروفة في requirements.txt |
| SAST | bandit | شدة HIGH على المسارات الحرجة |
| Credits integrity | pytest | فشل اختبارات الدفتر / الترويجي |

## يومي (03:00 UTC)

`scripts/security/credits_health_monitor.py`

1. Smoke: منح promo منتهٍ ثم حرقه
2. مسح المحافظ (Postgres إن وُجد `DATABASE_URL`)
3. `expire_promotional` + `reconcile`
4. Exit ≠ 0 عند drift أو فشل الـ smoke

أسرار اختيارية في GitHub:
- `DATABASE_URL` — لمسح الإنتاج/الـ staging

## محلياً

```bash
bash scripts/security/run_local_scans.sh
```

## Dependabot

`.github/dependabot.yml` — تحديثات أسبوعية لـ pip / Actions / Docker.

## متغيرات المonitor

| Env | المعنى |
|-----|--------|
| `CREDITS_MONITOR_FAIL_ON_DRIFT` | افتراضي 1 |
| `CREDITS_MONITOR_TENANT_IDS` | قائمة tenants مفصولة بفاصلة |
| `CREDITS_MONITOR_MAX_TENANTS` | حد المسح (500) |
