# B2B API

## التشغيل

```bash
python api_main.py
# أو مع البوت:
ENABLE_API=1 python main.py
```

المصادقة: `Authorization: Bearer sk_live_...` أو `X-Api-Key`.

## المسارات الأساسية

| Method | Path | وصف |
|--------|------|-----|
| GET | `/health` | صحة |
| GET | `/v1/plans` | خطط |
| POST | `/v1/tenants` | مستأجر جديد (قد يحتاج Admin token) |
| GET | `/v1/me` | هوية + خطة |
| PATCH | `/v1/me/white-label` | علامة بيضاء |
| POST | `/v1/me/rotate_key` | تدوير مفتاح |
| POST | `/v1/generate` | قبول مهمة توليد → `job_id` (202) |
| GET | `/v1/jobs/{id}` | حالة المهمة |
| GET | `/v1/jobs` | قائمة مهام |
| POST | `/v1/hosts/*` | استضافة |
| GET | `/v1/usage` | استهلاك |
| GET/POST | `/v1/invoices` | فواتير |
| GET | `/v1/dashboard` | لوحة |
| POST | `/v1/billing/*` | Stripe checkout / portal / webhook |

## الحزمة

- `api/app.py` — إنشاء التطبيق
- `api/routes/` — المسارات
- `api/auth.py` / `security.py` — مصادقة
- `b2b_platform/` — tenants, plans, metering

## خطط تقريبية

| خطة | استخدام نموذجي |
|-----|----------------|
| free | حدود منخفضة |
| pro / business | حصص أعلى + white-label من business |
| enterprise | مخصص |

المفاتيح تُخزَّن hashed (SHA-256)؛ المفتاح الخام مرة واحدة عند الإنشاء.
