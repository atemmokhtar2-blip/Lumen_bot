# الاستضافة

## نقطة التنسيق

`lumen/hosting/orchestration.py` — بدء/إيقاف البوتات المستضافة.

### اختيار الـ backend (fail-closed)

- **إنتاج / multi-tenant:** Firecracker فقط
- docker | gvisor | dind مسموحة فقط إذا البيئة dev/test **و** `TBE_HOST_ALLOW_WEAK_BACKEND=1`
- `.lumen_host.json` داخل المشروع يُحترم فقط تحت نفس البوابة

## حزم أخرى تحت `lumen/hosting/`

| ملف | دور |
|-----|-----|
| `gateway.py` | بوابة تشغيل |
| `project_space.py` / `project_manifest.py` | مساحة ووصف المشروع |
| `secrets_env.py` | حقن أسرار للمستضاف |
| `usage_billing.py` | استخدام/فوترة |
| `backup_manager.py` | نسخ احتياطي |
| `rate_limiter.py` | حدود معدل على مستوى الاستضافة |
| `webhook_manager.py` | webhooks |
| `ops_scheduler.py` / `alerter.py` / `log_aggregator.py` | تشغيل ومراقبة |

## المحرك

`engine/services/live_deployment`, `sandbox_runtime`, `user_sandbox` — عزل وتنفيذ حسب التهيئة.

## مع Lumen Pro

بعد استحقاق Pro النشط تُفتح الاستضافة الدائمة ضمن:

- حتى 10 بوتات
- 3 GB تخزين
- 2 GB RAM مشتركة
- 0.25 CPU لكل بوت

(التفاصيل في `09-pro-subscription.md` و`ui_state/pro_plan.py`)
