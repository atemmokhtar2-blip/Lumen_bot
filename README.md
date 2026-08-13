# AI Agent 7h

منصة توليد واستضافة بوتات تيليجرام — أربعة أسطح منتج في نظام واحد.

## أسطح المنتج

| السطح | الوصف | التفعيل |
|--------|--------|---------|
| **Consumer Bot** | بوت تيليجرام عام للمستخدمين | `python main.py` |
| **B2B API** | REST API مدفوعة للمطورين + حصص + مفاتيح | `ENABLE_API=1` أو `python api_main.py` |
| **White-label** | علامة تجارية / ألوان / نطاق لكل مستأجر (Business+) | `PATCH /v1/me/white-label` |
| **Managed Hosting** | توليد + تشغيل + إيقاف + تشخيص البوتات | `POST /v1/hosts/*` |

التوليد **حتمي (zero-AI)** عبر `spec_core` + بوابة **anti-hallucination**.

## التشغيل

```bash
pip install -r requirements.txt
cp .env.example .env   # TELEGRAM_BOT_TOKEN=...
python main.py         # Consumer bot + B2B API على PORT
# أو API فقط:
python api_main.py
```

## B2B API (ملخص)

المصادقة: `Authorization: Bearer sk_live_...` أو `X-Api-Key`.

| Method | Path | الوصف |
|--------|------|--------|
| GET | `/health` | صحة الخدمة |
| GET | `/v1/plans` | خطط الأسعار |
| POST | `/v1/tenants` | إنشاء مستأجر (يتطلب `X-Admin-Token` إن وُجد `PLATFORM_ADMIN_TOKEN`) |
| GET | `/v1/me` | هوية المستأجر + الخطة |
| PATCH | `/v1/me/white-label` | تحديث العلامة البيضاء |
| POST | `/v1/me/rotate_key` | تدوير مفتاح API |
| POST | `/v1/generate` | يقبل المهمة فوراً → `{ job_id, poll_url }` (202) |
| GET | `/v1/jobs/{job_id}` | حالة المهمة الثقيلة (polling) |
| GET | `/v1/jobs` | قائمة مهام المستأجر |
| POST | `/v1/hosts/start` | `{ "project_path", "bot_token" }` |
| POST | `/v1/hosts/stop` | إيقاف مثيل |
| GET | `/v1/hosts` | حالة الاستضافة |
| POST | `/v1/hosts/diagnose` | تشخيص أعطال |
| GET | `/v1/usage` | الاستهلاك الشهري |
| GET/POST | `/v1/invoices` | فواتير |
| GET | `/v1/dashboard` | لوحة مجمّعة |
| POST | `/v1/billing/checkout` | بدء Stripe Checkout للترقية |
| GET | `/v1/billing/checkout/success` | عودة بعد الدفع + تفعيل الخطة |
| GET | `/v1/billing/checkout/cancel` | إلغاء الدفع |
| POST | `/v1/billing/portal` | بوابة إدارة الاشتراك (Stripe Portal) |
| POST | `/v1/billing/webhook/stripe` | Webhook رسمي (تحقق توقيع) |
| POST | `/v1/billing/dev/activate` | تفعيل خطة بدون Stripe (تطوير فقط) |

### Stripe

1. أنشئ Products/Prices في Stripe لـ `pro` و `business`
2. ضع المتغيرات:
   - `STRIPE_SECRET_KEY`
   - `STRIPE_WEBHOOK_SECRET`
   - `STRIPE_PRICE_PRO` / `STRIPE_PRICE_BUSINESS`
   - `PUBLIC_BASE_URL` (رابط عام يصل لـ webhook)
3. Webhook endpoint: `POST /v1/billing/webhook/stripe`  
   أحداث: `checkout.session.completed`, `invoice.paid`, `customer.subscription.*`
4. العميل يستدعي `POST /v1/billing/checkout` بـ `{ "plan_id": "pro" }` ويُحوَّل إلى `url`


### الخطط

| Plan | $/mo | Generations | Hosted bots | RPM | White-label |
|------|------|-------------|-------------|-----|-------------|
| free | 0 | 20 | 1 | 30 | لا |
| pro | 49 | 500 | 10 | 120 | لا |
| business | 199 | 5000 | 100 | 600 | نعم |
| enterprise | custom | ∞ | ∞ | 3000 | نعم |

## مثال سريع

```bash
# إنشاء مستأجر
curl -s -X POST localhost:8080/v1/tenants \
  -H 'Content-Type: application/json' \
  -d '{"name":"Acme","plan_id":"business","brand_name":"Acme Bots"}'

# توليد
curl -s -X POST localhost:8080/v1/generate \
  -H "Authorization: Bearer $API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"description":"بوت فيه /start ويرد على الرسائل"}'

# لوحة
curl -s localhost:8080/v1/dashboard -H "Authorization: Bearer $API_KEY"
```

## العزل والأمان

- Sandbox لكل مستخدم/مستأجر تحت `OUTPUT_DIR`
- Docker مفضّل لتشغيل البوتات المولَّدة (حدود CPU/RAM/pids)
- مفاتيح API تُخزَّن **hashed** (SHA-256) — المفتاح الخام يُعرض مرة واحدة
- Rate limit + حصص شهرية حسب الخطة
- لا مسار LLM لتوليد الكود

## الهيكل

```text
main.py / api_main.py
bot_interface/          # Consumer Telegram
api/                    # B2B HTTP (aiohttp)
b2b_platform/           # tenants, plans, billing, metering
telegram_bot_engine/    # generation + isolation + hosting
  spec_core/
  services/anti_hallucination/
  services/hosting/
  services/user_sandbox/
```


## طابور المهام الثقيلة

`POST /v1/generate` لا يحجز خيط asyncio الافتراضي. يعيد `202` + `job_id`.

```bash
curl -X POST /v1/generate -H "Authorization: Bearer $KEY" -d '{"description":"..."}'
# → {"job_id":"job_...","poll_url":"/v1/jobs/job_..."}

curl /v1/jobs/job_... -H "Authorization: Bearer $KEY"
# → {"status":"running|succeeded|failed","result":{...}}
```

- عمال مخصصون: `JOB_MAX_WORKERS` (افتراضي 2)
- تخزين: SQLite تحت `OUTPUT_DIR/platform/jobs.sqlite3`
- مزامنة للتطوير فقط: `"wait": true` (غير مستحسن إنتاجاً)
