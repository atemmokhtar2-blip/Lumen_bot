# الشات و Grok — توجيه فقط (لا تنفيذ)

## الدور الصحيح لـ Grok / مزود الشات

في هذا المستودع:

> **الشات (افتراضي: Groq المسمى Grok في البرومبتات) = فهم نية المستخدم + اختيار أداة أو الإجابة.**  
> **التنفيذ = المحركات والأدوات فقط.**

مذكور صراحة في `tool_runtime`:

```text
Local tool runtime — Groq only *selects* tools; engines execute them.
```

## الإعداد الافتراضي (llm/facade.py)

| الوظيفة | المتغير | الافتراضي |
|---------|---------|-----------|
| **Chat** (حوار + توجيه) | `CHAT_PROVIDER` | `groq` |
| **Translate** (عقد spec_core) | `TRANSLATE_PROVIDER` | `gemini` |
| Fallback chat | — | groq → gemini |
| Fallback translate | — | gemini → groq |

نقاط الاستدعاء الموحدة (لا تستورد مزوداً من الراوترات مباشرة):

```python
from lumen.engine.services.llm.facade import chat_request, translate_request
# أو عبر
from lumen.engine.services.translator_client import chat_request, translate_request
```

## ملفات مزود الشات

| ملف | الدور |
|-----|------|
| `services/llm/groq_chat.py` | تنفيذ شات Groq + system prompt + JSON عقد الرد |
| `services/gemini_client.py` | شات/فهم Gemini + برومبتات |
| `services/llm/adapters.py` | محولات Chat/Translate |
| `services/llm/facade.py` | اختيار المزود + سلسلة fallback |
| `services/llm/key_pool.py` | مفاتيح Groq المتعددة + cooldown |
| `services/chat_router/service.py` | راوتر قدرات حتمي (phrases/regex) بدون LLM |
| `services/platform_status.py` | حالة «قيد التطوير» تُحقن في برومبت الشات |

## شكل رد الشات المتوقع

JSON تقريباً:

```json
{
  "answer": "نص للمستخدم بالعربي",
  "action": {
    "name": "generate_bot|clone_repo|host_start|…|\"\"",
    "requires_confirmation": false,
    "params": {}
  },
  "translation": { ... } | null
}
```

`action.name` المسموحة في groq_chat تشمل:  
`clone_repo`, `host_start`, `host_stop`, `host_status`, `repo_understand`, `generate_bot`, `refine_bot`, `repo_inspect`, …

الشات **يملأ** الاسم؛ `execute_tool` / مسارات التوليد **تنفّذ**.

## chat_router (بدون LLM)

`lumen.engine/services/chat_router/service.py` يسجّل قدرات (`Capability`) بعبارات عربية/إنجليزية:

- استضافة، سحب مستودع، توليد، تحليل، مساعدة…

يُستخدم لـ **hard routing** بثقة عالية قبل أو مع طبقة LLM.

## متى Grok «فاهم المستودع»؟

Grok **ما بيقرأش القرص لوحده**.

المسار الصحيح:

1. المستخدم سحب مستودع → `active_repo` + dossier من أدوات القياس
2. سؤال حر → `repo_understand` / `run_core_toolkit` (stats, tree, read_file, …)
3. نتائج الأدوات تُمرَّر لـ `llm_explain.explain_repo_with_llm` → إجابة من TOOL_RESULTS فقط

لو LLM غير متاح → رد عربي من الأرقام المقاسة (`_format_facts_ar`)، مش dump إنجليزي خام.

## حالة التطوير

`platform_status.py` يحقن في system prompt:

- المنصة قيد التطوير
- عند شكوى من أخطاء: اعتراف صريح بدون أعذار وهمية

متغيرات: `PLATFORM_UNDER_DEVELOPMENT`, `PLATFORM_UPDATE_NOTE`, `PLATFORM_DEVELOPER_NAME`

## ممنوع

- إن تنفيذ `git clone` أو كتابة مشروع من داخل رد الشات
- اعتبار وصف بوت جديد «سؤال عن المستودع القديم»
- عرض headers مثل `Grok LLM unavailable` للمستخدم النهائي
