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

## LLM — فصل صارم بين المزودين

**قاعدة المنتج:**

| الدور | المزود | متغير المفاتيح (خانة واحدة للكل) |
|--------|--------|------------------------------|
| شات / توجيه فقط | **Groq فقط** | `GROQ_API_KEYS` (أو `GROQ_API_KEY` + `_0..`) |
| ترجمة عقد spec فقط | **Gemini فقط** | `GEMINI_API_KEYS` (أو `GEMINI_API_KEY` + `_0..`) |

| متغير | افتراضي | معنى |
|--------|---------|------|
| `TBE_STRICT_LLM_ROLES` | `1` | فرض الفصل: شات=Groq، ترجمة=Gemini — بلا خلط |
| `CHAT_PROVIDER` | `groq` | يُتجاهل تحت الصرامة ويُثبت `groq` |
| `TRANSLATE_PROVIDER` | `gemini` | يُتجاهل تحت الصرامة ويُثبت `gemini` |
| `GROQ_API_KEYS` | — | كل مفاتيح الشات (فاصلة أو أسطر) |
| `GEMINI_API_KEYS` | — | كل مفاتيح الترجمة (فاصلة أو أسطر) |
| `GROQ_CHAT_ENABLED` | — | تفعيل/تعطيل شات Groq |
| `KEY_RATE_COOLDOWN_SEC` | `8` | تهدئة قصيرة بعد 429 ثم المفتاح التالي |
| `KEY_AUTH_COOLDOWN_SEC` | `300` | تهدئة بعد 401/403 |

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
