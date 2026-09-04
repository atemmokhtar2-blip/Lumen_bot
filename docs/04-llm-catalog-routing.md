# كتالوج النماذج والتوجيه

## مصدر الحقيقة

`lumen/engine/services/llm/model_catalog.py`

كل نموذج: `id`, `label`, `provider`, `model_id`, `api_style`, `base_url`, `api_key_env`, `roles`, `cost_tier`, `strength`.

- بدون مفتاح → يُستبعد من `available_models()` (لا crash).
- `resolve_dispatch()`: إن كان المفتاح OpenRouter فقط، يُحوَّل المسار إلى OpenRouter مع `model_id` مناسب.

## نماذج المنتج (الحالية في الكود)

| catalog id | provider | model_id الافتراضي | مفتاح |
|------------|----------|-------------------|--------|
| `deepseek-v4-flash` | deepseek | `deepseek-v4-flash` | `DEEPSEEK_API_KEY` |
| `gemini-2.5-flash-lite` | gemini | `gemini-2.5-flash-lite` | `GOOGLE_API_KEY` |
| `openai-gpt-4o-mini` | openai | `gpt-4o-mini` | `OPENAI_API_KEY` |
| `deepseek-v3` | deepseek | **`deepseek-chat`** | `DEEPSEEK_API_KEY` |
| `claude-3-haiku` | anthropic | `claude-3-haiku-20240307` | `ANTHROPIC_API_KEY` |
| `gemini-2.5-pro` | gemini | `gemini-2.5-pro` | `GOOGLE_API_KEY` |
| `openrouter-auto` | openrouter | `openrouter/auto` | `OPENROUTER_API_KEY` |
| `groq-fast` | groq | `llama-3.3-70b-versatile` | `GROQ_API_KEY` |
| `foundry-model-router` | foundry | `model-router` | Azure Foundry |

### ملاحظات مهمة

- **DeepSeek V3** = `deepseek-chat` فقط. لا يُستبدل افتراضيًا بـ `deepseek-v4-pro`.
- **`deepseek-v4-pro`:** موجود في الكتالوج لكن `roles=()` — اختياري عبر `CLINE_MODEL_PLAN=deepseek-v4-pro` وليس اختيارًا تلقائيًا.
- **Groq:** لا يستضيف DeepSeek V4 Flash رسميًا؛ مسار السرعة = Llama على GroqCloud.
- OpenRouter يمكنه عكس `deepseek/deepseek-v4-flash` عند غياب مفتاح DeepSeek.

## ترتيب التوجيه

`select_model` / `select_model_for_goal` في `cline_runtime/model_router.py`:

1. مزوّد إجباري `CLINE_LLM_PROVIDER` / `ENGINE_LLM_PROVIDER` (مع مطابقة role من الكتالوج)
2. **Microsoft Foundry Model Router** إذا `CLINE_ROUTER` ∈ {auto, foundry} والمفاتيح موجودة → deployment مثل `model-router`
3. وإلا **R2 allocator** المحلي (`r2_allocator.py`): تفكيك الخطوة plan|code|repair|critique ثم تقييم من الكتالوج
4. ترتيب تفضيلي للمنتج ثم cost/strength
5. `CLINE_MODEL_PLAN` / `CLINE_MODEL_BUILD` / `CLINE_MODEL_CRITIQUE` تقبل **catalog id** أو model_id

`ModelChoice` يحمل `catalog_id` للربط الرجعي مع صف الكتالوج.

## التنفيذ HTTP

`agent_brain._invoke_choice` →:

- foundry → `foundry_router.chat_completions`
- openai / openrouter / deepseek / anthropic → `_dispatch_catalog_provider`
- gemini / groq → دوال المزوّد مع `model_id` من الاختيار
- نفس تلميح JSON للأدوات المخصّصة للوكيل (منع tools المدمجة للمزوّد)

## ما أُزيل

- `translate_request` / `chat_request` وكل stubs الترجمة/الشات من مسار التوليد
- `llm/facade.py` و`llm_budget_gate.py`
