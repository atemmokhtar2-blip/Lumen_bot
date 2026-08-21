# الإعداد والمتغيرات

انسخ `.env.example` → `.env` عند التشغيل.

## أساسيات البوت

| متغير | معنى |
|--------|------|
| `TELEGRAM_BOT_TOKEN` | توكن البوت من BotFather |
| `ALLOWED_USER_IDS` | قائمة مسموحة (إن وُجد قفل) |
| `ALLOW_ALL_USERS` | فتح عام |
| `OUTPUT_DIR` | مخرجات التوليد والنسخ |
| `PORT` | منفذ health/API |

## LLM

| متغير | افتراضي تقريبي | معنى |
|--------|-----------------|------|
| `CHAT_PROVIDER` | `groq` | مزود الشات/التوجيه |
| `TRANSLATE_PROVIDER` | `gemini` | مزود ترجمة العقد |
| `GROQ_API_KEY` (+ `_1..`) | — | مفاتيح Groq |
| `GROQ_CHAT_ENABLED` | — | تفعيل/تعطيل شات Groq |
| `GROQ_*_MODELS` | — | قائمة نماذج |
| مفاتيح Gemini | حسب `gemini_client` | فهم/ترجمة |

## المنصة

| متغير | معنى |
|--------|------|
| `PLATFORM_UNDER_DEVELOPMENT` | `1`/`0` — إعلان التطوير في الشات |
| `PLATFORM_UPDATE_NOTE` | ملاحظة تحديث |
| `PLATFORM_DEVELOPER_NAME` | الاسم الظاهر (افتراضي حاتم) |
| `ENABLE_API` | تشغيل B2B مع main.py |
| `PLATFORM_ADMIN_TOKEN` | إنشاء مستأجرين من الـ API |
| `SENTRY_DSN` | مراقبة أخطاء (اختياري) |

## Stripe (B2B)

`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_PRO`, `STRIPE_PRICE_BUSINESS`, `PUBLIC_BASE_URL`

## Repo explain

| متغير | معنى |
|--------|------|
| `REPO_EXPLAIN_PROMPT_CHARS` | حجم نافذة برومبت فهم المستودع |
| `REPO_EXPLAIN_MAX_TOKENS` | حد إخراج النموذج |
| `REPO_TOOLKIT_PROMPT_CHARS` | حجم TOOL_RESULTS في البرومبت |
