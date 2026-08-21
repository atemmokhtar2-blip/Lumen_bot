# البنية العامة للمنصة (Architecture)

## ما هذه المنصة؟

**capability_maestro_bot / AI Agent 7h / Maestro** منصة واحدة فيها عدة أسطح:

| السطح | ماذا يفعل | نقطة الدخول |
|--------|-----------|-------------|
| بوت تيليجرام (Consumer) | محادثة، سحب مستودعات، توليد بوتات، استضافة | `python main.py` |
| B2B API | توليد/استضافة/فوترة عبر HTTP | `python api_main.py` أو `ENABLE_API=1` |
| محرك التوليد الحتمي | من مواصفات → مشروع بوت بدون هلوسة | `telegram_bot_engine/spec_core` |
| أدوات المستودع | clone / قياس / فهم / تعديل عبر المحرك | `tool_runtime` + `repo_understanding` |

## مبدأ التصميم الأساسي

```
المستخدم (تيليجرام أو API)
        │
        ▼
┌───────────────────┐
│  Interface Layer  │  bot_interface / api
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
| `api_main.py` / `api/` | خادم B2B فقط |
| `bot_interface/` | طبقة تيليجرام: أوامر، راوترات، جلسات |
| `telegram_bot_engine/` | المحرك: توليد، أدوات، LLM، استضافة، أمان |
| `telegram_bot_engine/spec_core/` | توليد حتمي Zero-AI من `BotSpec` |
| `telegram_bot_engine/pipeline/` | مراحل التوليد القديمة/الموحدة (Parse→Package) |
| `telegram_bot_engine/engines/` | محركات متخصصة (تخطيط، ملفات، git…) |
| `telegram_bot_engine/core/` | سياق، عقود، bootstrap، أدوار المحركات |
| `telegram_bot_engine/services/` | خدمات تشغيلية (LLM، repo، hosting، sandbox) |
| `b2b_platform/` | مستأجرين، خطط، قياس استهلاك |
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
