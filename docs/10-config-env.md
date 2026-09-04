# متغيرات البيئة

## تشغيل البوت

| متغير | وظيفة |
|-------|--------|
| `TELEGRAM_BOT_TOKEN` | توكن البوت (إلزامي) |
| `ALLOW_ALL_USERS` | `1` يفتح للجميع؛ وإلا allowlist أضيق |
| `REDIS_URL` / `JOB_REDIS_URL` | جلسات، طوابير، حدود |
| `MONGODB_URI` | مستخدمون + `pro_subscription` الدائم |
| `SESSION_ALLOW_MEMORY` | `1` يسمح بذاكرة فقط بدون Redis (تطوير) |
| `ENVIRONMENT` / `TBE_ENV` | dev/test vs production لاستضافة |

## توجيه النماذج

| متغير | وظيفة |
|-------|--------|
| `CLINE_ROUTER` | `auto` \| `foundry` \| `local` \| `r2` \| `catalog` |
| `CLINE_LLM_PROVIDER` / `ENGINE_LLM_PROVIDER` | إجبار مزوّد |
| `CLINE_MODEL_PLAN` / `CLINE_MODEL_BUILD` / `CLINE_MODEL_CRITIQUE` | catalog id أو model_id |
| `CLINE_LLM_TIMEOUT` | مهلة ثواني لنداءات HTTP |

## مفاتيح المزوّدين

| متغير | الاستخدام |
|-------|-----------|
| `DEEPSEEK_API_KEY` | V4 Flash + V3 |
| `DEEPSEEK_V3_MODEL` | تجاوز id لـ V3 (افتراضي `deepseek-chat`) |
| `DEEPSEEK_FLASH_MODEL` / `DEEPSEEK_PRO_MODEL` / `DEEPSEEK_BASE_URL` | تجاوزات اختيارية |
| `GOOGLE_API_KEY` / `GEMINI_API_KEY` | Gemini (+ key_pool) |
| `GEMINI_FLASH_LITE_MODEL` / `GEMINI_PRO_MODEL` | تجاوز أسماء |
| `OPENAI_API_KEY` | GPT-4o-mini |
| `ANTHROPIC_API_KEY` | Claude Haiku |
| `OPENROUTER_API_KEY` | بوابة + fallback للمزوّدين الآخرين |
| `GROQ_API_KEY` / `GROQ_MODEL` | groq-fast |
| `AZURE_FOUNDRY_ENDPOINT` + `AZURE_FOUNDRY_KEY` | Model Router |
| `AZURE_FOUNDRY_MODEL` / `AZURE_FOUNDRY_DEPLOYMENT*` | أسماء deployment |
| `AZURE_FOUNDRY_ROUTING_MODE` | balanced\|cost\|quality |
| `AZURE_FOUNDRY_API_VERSION` | نسخة API |

أسماء `AZURE_OPENAI_*` مقبولة كبديل في عدة مواضع Foundry.

## Multi-agent / استضافة

| متغير | وظيفة |
|-------|--------|
| `MULTI_AGENT_ORCHESTRATOR` | افتراضي on |
| `MULTI_AGENT_MAX_ATTEMPTS` | 1–8 |
| `TBE_MULTI_TENANT` | يفعّل مسار الإنتاج للاستضافة |
| `TBE_HOST_ALLOW_WEAK_BACKEND` | يسمح docker/gvisor في dev فقط |

## ما لا يُستخدم لتوليد الوكيل

متغيرات مترجم Qwen/HTTP translator القديمة — دوال `translate_request` غير موجودة.
