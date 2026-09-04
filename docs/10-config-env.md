# متغيرات البيئة

## أساسية

| متغير | الغرض |
|-------|--------|
| `TELEGRAM_BOT_TOKEN` | توكن البوت |
| `REDIS_URL` / `JOB_REDIS_URL` | جلسات، طوابير، حدود |
| `ALLOW_ALL_USERS` | فتح البوت للعامة (افتراضيًا مغلق أكثر أمانًا) |
| `DATABASE_URL` / Mongo | مستخدمون واشتراكات دائمة |

## نماذج (حسب الكتالوج)

| متغير | نماذج |
|-------|--------|
| `DEEPSEEK_API_KEY` | V4 Flash، V3 (`deepseek-chat`) |
| `DEEPSEEK_V3_MODEL` | تجاوز id لـ V3 فقط (الافتراضي `deepseek-chat`) |
| `DEEPSEEK_FLASH_MODEL` / `DEEPSEEK_PRO_MODEL` | تجاوزات اختيارية |
| `GOOGLE_API_KEY` / `GEMINI_API_KEY` | Gemini Flash Lite / Pro |
| `OPENAI_API_KEY` | GPT-4o-mini |
| `ANTHROPIC_API_KEY` | Claude 3 Haiku |
| `OPENROUTER_API_KEY` | بوابة + fallback |
| `GROQ_API_KEY` | `groq-fast` (Llama) |
| `AZURE_FOUNDRY_ENDPOINT` + `AZURE_FOUNDRY_KEY` | Model Router |
| `AZURE_FOUNDRY_MODEL` | افتراضي `model-router` |

## توجيه الوكيل

| متغير | المعنى |
|-------|--------|
| `CLINE_ROUTER` | `auto` \| `foundry` \| `local` \| `r2` \| `catalog` |
| `CLINE_LLM_PROVIDER` | إجبار مزوّد |
| `CLINE_MODEL_PLAN` / `BUILD` / `CRITIQUE` | تجاوز بـ catalog id أو model_id |
| `CLINE_LLM_TIMEOUT` | مهلة HTTP للنداءات |

## جلسات

| متغير | المعنى |
|-------|--------|
| `SESSION_ALLOW_MEMORY` | ذاكرة فقط للتطوير بدون Redis |

لا تعتمد على متغيرات مترجم Qwen/translator القديمة لمسار التوليد — المسار محذوف.
