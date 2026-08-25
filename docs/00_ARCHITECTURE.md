# البنية العامة للمنصة (Architecture)

## ما هذه المنصة؟

**Lumen_bot / Lumen / Lumen** منصة واحدة فيها عدة أسطح:

| السطح | ماذا يفعل | نقطة الدخول |
|--------|-----------|-------------|
| بوت تيليجرام (Consumer) | محادثة، سحب مستودعات، توليد بوتات، استضافة | `python main.py` |
| B2B API | توليد/استضافة/فوترة عبر HTTP | `python api_main.py` أو `ENABLE_API=1` |
| محرك التوليد الحتمي | من مواصفات → مشروع بوت بدون هلوسة | `lumen.engine/spec_core` |
| أدوات المستودع | clone / قياس / فهم / تعديل عبر المحرك | `tool_runtime` + `repo_understanding` |

## مبدأ التصميم الأساسي

```
المستخدم (تيليجرام أو API)
        │
        ▼
┌───────────────────┐
│  Interface Layer  │  lumen.bot / api
│  توجيه فقط        │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│  LLM Layer        │  Chat = توجيه نية (افتراضي Groq/Grok)
│                   │  Translate = عقد spec (افتراضي Gemini)
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│  Tool / Engine    │  التنفيذ الحقيقي هنا فقط
│  Runtime          │  clone, generate, host, repo_*
└───────────────────┘
```

**قاعدة ذهبية:** النموذج اللغوي **ما بينفّذش** سحب Git ولا كتابة ملفات ولا استضافة.  
هو يفهم أو يترجم أو يختار أداة. **المحرك** هو اللي ينفّذ.

## المجلدات الرئيسية

| مسار | الدور |
|------|------|
| `main.py` | تشغيل بوت التيليجرام (+ API اختياري) |
| `api_main.py` / `lumen/api/` | خادم B2B فقط |
| `lumen.bot/` | طبقة تيليجرام: أوامر، راوترات، جلسات |
| `lumen.engine/` | المحرك: توليد، أدوات، LLM، استضافة، أمان |
| `lumen.engine/spec_core/` | توليد حتمي Zero-AI من `BotSpec` |
| `lumen.engine/pipeline/` | مراحل التوليد القديمة/الموحدة (Parse→Package) |
| `lumen.engine/engines/` | محركات متخصصة (تخطيط، ملفات، git…) |
| `lumen.engine/core/` | سياق، عقود، bootstrap، أدوار المحركات |
| `lumen.engine/services/` | خدمات تشغيلية (LLM، repo، hosting، sandbox) |
| `lumen.platform/` | مستأجرين، خطط، قياس استهلاك |
| `deploy/` | نشر تجاري |
| `tests/` | اختبارات |

## تدفق الطلب النموذجي (تيليجرام)

1. `main.py` يسجّل handlers → كل رسالة نصية → `handle_message`
2. `message_router` يفرّق: توكن بوت؟ أمر؟ سحب git؟ توليد؟ سؤال عن مستودع؟
3. إن كان **شات/توجيه**: مزود الشات (افتراضي Groq) يرد أو يملأ `action`
4. إن كان **توليد**: ترجمة لـ `spec_request` + `features_requested` ثم `spec_core`
5. إن كان **أداة صلبة** (`clone_repo`, `repo_understand`, …): `execute_tool` → محرك

## فصل المستويات (Planes)

بعد إعادة الهيكلة:

- **Control Plane** (`planes/control.py`): مشاريع، خطط، صلاحيات، نشر منطقي
- **Runtime Plane** (`planes/runtime.py`): عمال، أدوات، حاويات، تنفيذ

## الحدود الأمنية

```
Agent/Chat → Tool Contract → Policy → Sandbox/Executor
```

مجلدات مهمة: `security/policy.py`, `security/sandbox.py`, `boundaries/` (git / workspace / hosting).

## اقرأ بعد كده

- [01_ENTRY_POINTS.md](01_ENTRY_POINTS.md)
- [03_MESSAGE_FLOW.md](03_MESSAGE_FLOW.md)
- [04_CHAT_AND_GROK.md](04_CHAT_AND_GROK.md)
- [06_SPEC_CORE.md](06_SPEC_CORE.md)
