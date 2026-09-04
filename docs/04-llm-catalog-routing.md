# كتالوج النماذج والتوجيه

## مصدر الحقيقة

`lumen/engine/services/llm/model_catalog.py`

### `CatalogModel`

- `id` — معرّف منتج ثابت (مثل `deepseek-v3`)
- `provider`, `model_id`, `api_style` (`openai_compat` | `gemini` | `anthropic`)
- `base_url`, `api_key_env`, `roles`, `cost_tier`, `strength`
- `key_present()` — يدمج `key_pool` لـ Gemini/Groq وendpoint لـ Foundry
- `resolve_dispatch()` — إن المفتاح OpenRouter فقط: يحوّل provider/base_url/model_id للبوابة

بدون مفتاح صالح → النموذج خارج `available_models()`.

## صفوف المنتج

| id | provider | model_id الافتراضي | أدوار | ملاحظات |
|----|----------|-------------------|-------|---------|
| `deepseek-v4-flash` | deepseek | `deepseek-v4-flash` | build, fast, reason | API رسمي DeepSeek |
| `gemini-2.5-flash-lite` | gemini | `gemini-2.5-flash-lite` | build, fast | |
| `openai-gpt-4o-mini` | openai | `gpt-4o-mini` | build, fast, plan, critique | fallback عام |
| `deepseek-v3` | deepseek | **`deepseek-chat`** | plan, build, reason | **الافتراضي لـ DeepSeek في plan** |
| `claude-3-haiku` | anthropic | `claude-3-haiku-20240307` | critique, fast, build | |
| `gemini-2.5-pro` | gemini | `gemini-2.5-pro` | plan, critique, reason | |
| `openrouter-deepseek-v4-flash` | openrouter | `deepseek/deepseek-v4-flash` | build, fast, reason | مرآة |
| `openrouter-auto` | openrouter | `openrouter/auto` | الكل | بوابة |
| `groq-fast` | groq | `llama-3.3-70b-versatile` | build, fast | Groq لا يستضيف V4 Flash |
| `foundry-model-router` | foundry | `model-router` | الكل | يحتاج endpoint+key |
| `deepseek-v4-pro` | deepseek | `deepseek-v4-pro` | **roles=()** | اختياري فقط عبر `CLINE_MODEL_*` |

تجاوز V3: `DEEPSEEK_V3_MODEL` فقط — **`DEEPSEEK_MODEL` لا يلوّث صف V3**.

## `ModelChoice` (`model_router.py`)

`provider`, `model_id`, `api_key_env`, `base_url`, **`catalog_id`**

يُبنى عبر `_choice_from_catalog_model` → دائمًا `resolve_dispatch()`.

## ترتيب الاختيار

### `select_model(task=...)`

1. Foundry إن `CLINE_ROUTER` ∈ {auto, foundry} و`foundry_configured()`
2. مزوّد إجباري `CLINE_LLM_PROVIDER` مع تفضيل صفوف نفس الـ role
3. `available_models(role)` مرتّبة بـ **قائمة تفضيل R2** ثم strength/cost
4. `_apply_task_model_override` — `CLINE_MODEL_PLAN|BUILD|CRITIQUE` تقبل catalog id

### `select_model_for_goal(...)`

1. Foundry (مع meta عن الوضع)
2. `r2_allocator.allocate(...)` إن `CLINE_ROUTER` ∈ {auto, local, catalog, r2}
3. وإلا نفس مسار `select_model`

### Foundry (`foundry_router.py`)

- أوضاع: `quality` | `cost` | `balanced` من نوع المهمة أو `AZURE_FOUNDRY_ROUTING_MODE`
- deployment من env الخاص بالوضع أو `model-router`
- يُسجَّل `response.model` الفعلي في آخر نتيجة

### R2 (`r2_allocator.py`)

1. `decompose_step` → `plan` | `code` | `repair` | `critique`
2. تقييم كل نموذج في `available_models()` (مفتاح موجود)
3. تفضيل حسب `_KIND_PREFER` (V3 وليس v4-pro في plan)
4. `AllocateResult` مع `catalog_id` + حقول بعد `resolve_dispatch`

## التنفيذ (`agent_brain.py`)

`_invoke_choice`:

| provider | المسار |
|----------|--------|
| foundry | `foundry_router.chat_completions` + حقن anti-tool/JSON |
| openai, openrouter, deepseek, anthropic | `_dispatch_catalog_provider` |
| gemini | `_call_gemini` بـ model_id من الاختيار فقط |
| groq | `_call_groq`؛ الافتراضي من catalog `groq-fast` |
| qwen/xai/ollama/llamacpp | مسارات legacy عند الإجبار |

`_dispatch_catalog_provider` يطابق **catalog_id أولًا**، يحفظ catalog_id عند إعادة البناء، DeepSeek يضيف `/v1` على base، OpenRouter headers قياسية.

Failover: `_failover_choice` يختار التالي من الكتالوج باستثناء المزوّد الفاشل.
