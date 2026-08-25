# الترجمة للعقد (Translate → spec_core)

## قاعدة فصل المزودين (صارمة)

**الترجمة = Gemini (Google) فقط.**  
الشات = Groq فقط. لا يُستخدم Groq في مسار `translate_request` عندما `TBE_STRICT_LLM_ROLES=1`.

المفاتيح: `GEMINI_API_KEY` / `GEMINI_API_KEYS` (خانة واحدة مفصولة بفاصلة أو أسطر).


## الهدف

تحويل كلام المستخدم الطبيعي إلى عقد يفهمه المحرك الحتمي:

- `spec_request` — نص مواصفات مضغوط
- `features_requested` — مفاتيح من سجل `spec_core` فقط
- `flows`, `purpose`, `confidence`, `clarification_needed`

## المسار الموصى به (Two-stage)

من تعليقات `message_router`:

```
Gemini يفهم المستخدم → بنية نية (understanding)
        ↓
Translator (عقد features حرفي من CAPABILITIES)
        ↓
spec_core يولّد المشروع
```

- **فهم / شات:** غالباً Gemini أو Groq حسب `CHAT_PROVIDER`
- **ترجمة العقد:** افتراضي `TRANSLATE_PROVIDER=gemini` مع fallback لـ Groq

## الملفات

| ملف | الدور |
|-----|------|
| `services/translator_client.py` | أجسام المزودين + `translate_request` / `chat_request` |
| `services/llm/facade.py` | اختيار المزود الرسمي |
| `services/engine_groq_bridge.py` | جسر تحليل بعد الترجمة (preferred_keys, mode) |
| `services/gemini_client.py` | برومبتات الفهم + التحقق `validate_spec_translation` |
| `spec_core/registry.py` | قاموس القدرات المسموحة — **مصدر الحقيقة للمفاتيح** |

## قواعد صارمة في البرومبت

1. `features_requested` = مفاتيح حرفية من `SPEC_CORE_CAPABILITIES` فقط
2. لا اختراع أسماء قدرات
3. لو المواصفات ناقصة → `clarification_needed=true`
4. `spec_request` عقد داخلي للمحرك — مش رد للمستخدم

## مسار force_generate (تخطي الشات)

عند طلب توليد **صريح** (أفعال: عايز بوت / اعمل بوت…):

- يُضبط `force_generate_once`
- يتخطى طبقة الشات البطيئة
- يستدعي `translate_request` ثم التوليد

وصف بدون فعل صريح (`بوت متجر إلكتروني…`) **يجب** أن يمر بمسار الفهم/الترجمة الكامل، لا بـ `repo_understand`.

## الاستخدام من الكود

```python
from lumen.engine.services.translator_client import translate_request

tr = translate_request(user_text, {
    "conversation_history": [...],
    "server_facts": {...},
    "gemini_understanding": {...},  # إن وُجد من مرحلة الفهم
})
# tr["spec_request"], tr["features_requested"]
```
