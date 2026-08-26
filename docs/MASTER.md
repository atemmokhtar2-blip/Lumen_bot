# دليل المستودع الكامل — Lumen / Lumen_bot

هذا الملف هو **الخريطة الرئيسية**. باقي الملفات تشرح كل جزء بالتفصيل بعد قراءة الكود الفعلي.

---

## 1) جملة واحدة عن النظام

منصة تولّد بوتات تيليجرام بشكل **حتمي** (`spec_core`)، وتسمح بسحب مستودعات وقياسها، وتشغيل استضافة، وتقدّم B2B API — مع طبقة شات **توجّه فقط** ولا تنفّذ.

---

## 2) خريطة سريعة: مين بيعمل إيه؟

| الطبقة | المسؤولية | أمثلة ملفات |
|--------|-----------|-------------|
| تشغيل | entry processes | `main.py`, `api_main.py` |
| واجهة تيليجرام | استقبال رسائل، جلسات، أوامر | `lumen.bot/` |
| توجيه الرسالة | ترتيب المسارات الحرج | `message_router.py` |
| شات (**Groq فقط**) | فهم نية + اختيار action — لا Gemini | `llm/groq_chat.py`, `llm/facade.py` |
| ترجمة (**Gemini فقط**) | عقد features لـ spec_core — لا Groq | `translator_client`, Gemini translate |
| أدوات | تنفيذ clone/host/repo/… | `tool_runtime/executor.py` |
| توليد حتمي | كود بوت من مواصفات | `spec_core/` |
| Pipeline/Engines | مراحل ومحركات داخلية | `pipeline/`, `engines/` |
| مستودع | قياس وشرح من TOOL_RESULTS | `repo_understanding/` |
| استضافة | عمليات طويلة الأمد | `services/hosting/` |
| B2B | مستأجرين وحصص وفوترة | `lumen/api/`, `lumen.platform/` |
| أمان | سياسة + sandbox | `security/`, `boundaries/` |

---

## 3) التدفق الذهني لأي رسالة تيليجرام

```
رسالة
 ├─ توكن بوت؟ → تشغيل حي
 ├─ توليد صريح (عايز بوت…)؟ → ترجمة → spec_core
 ├─ مواصفات بوت (بوت متجر…)? → Gemini فهم → ترجمة → spec_core
 ├─ Git URL / اسحب؟ → clone → active_repo
 ├─ سؤال عن المستودع النشط؟ → repo tools → إجابة من القياس
 ├─ استضافة؟ → hosting tools
 └─ غير ذلك → شات (توجيه) أو مساعدة
```

**Grok للشات/التوجيه فقط.** التنفيذ دائماً للمحرك.

---

## 4) فهرس ملفات التوثيق

| ملف | المحتوى |
|-----|---------|
| [00_ARCHITECTURE.md](00_ARCHITECTURE.md) | البنية والمجلدات والمبادئ |
| [01_ENTRY_POINTS.md](01_ENTRY_POINTS.md) | كيف تشغّل النظام |
| [03_MESSAGE_FLOW.md](03_MESSAGE_FLOW.md) | ترتيب message_router بالتفصيل |
| [04_CHAT_AND_GROK.md](04_CHAT_AND_GROK.md) | دور الشات وحدوده |
| [05_TRANSLATION.md](05_TRANSLATION.md) | من كلام المستخدم لعقد spec |
| [06_SPEC_CORE.md](06_SPEC_CORE.md) | التوليد الحتمي Zero-AI |
| [07_TOOL_RUNTIME.md](07_TOOL_RUNTIME.md) | execute_tool والأدوات |
| [08_REPO_AND_GIT.md](08_REPO_AND_GIT.md) | clone والفهم والقياس |
| [09_ENGINES_AND_PIPELINE.md](09_ENGINES_AND_PIPELINE.md) | pipeline والمحركات والسياق |
| [10_HOSTING.md](10_HOSTING.md) | الاستضافة |
| [11_B2B_API.md](11_B2B_API.md) | REST API |
| [12_SECURITY_AND_SANDBOX.md](12_SECURITY_AND_SANDBOX.md) | أمان وعزل |
| [13_CONFIG_ENV.md](13_CONFIG_ENV.md) | متغيرات البيئة |
| [14_ENGINE_ROUTER_AND_IR.md](14_ENGINE_ROUTER_AND_IR.md) | IR + EngineRouter |
| [15_ROADMAP_AND_AI_HANDOFF.md](15_ROADMAP_AND_AI_HANDOFF.md) | خارطة طريق وتسليم |
| [18_LIVE_TOKEN_AND_UX.md](18_LIVE_TOKEN_AND_UX.md) | توكن التشغيل الحي + واجهة مختصرة |
| [33_AGENTS_12_PHASES.md](33_AGENTS_12_PHASES.md) | نظام Agents — 12 مرحلة + قواعد |
| [34_PHASE_A_SERVER_RUN.md](34_PHASE_A_SERVER_RUN.md) | تشغيل السيرفر Phase A (Cline) |
| [35_PHASE_B_DURABILITY.md](35_PHASE_B_DURABILITY.md) | Phase B — Temporal / journal / scale |
| [36_PHASE_C_CODE_INTELLIGENCE.md](36_PHASE_C_CODE_INTELLIGENCE.md) | Phase C — Tree-sitter / graph / retrieval |

---

## 5) قواعد مطوّر (مستخرجة من التصميم)

1. لا تنفّذ side effects من برومبت الشات مباشرة.  
2. `features_requested` من سجل القدرات فقط.  
3. Repo intelligence مشتق — القرص مصدر الحقيقة.  
4. وصف بوت جديد ≠ سؤال عن `active_repo`.  
5. Planning منفصل عن Generation.  
6. Git ≠ Workspace ≠ Hosting.  
7. بعد أي تغيير سلوكي: راقب `message_router` أولاً — ترتيب الـ if هو المنتج.

---

## 6) تشغيل سريع

```bash
pip install -r requirements.txt
cp .env.example .env
# TELEGRAM_BOT_TOKEN=...
python main.py
```

API:

```bash
python api_main.py
```

---

*التوثيق يعكس بنية المستودع كما هي في الكود. أي تعارض مع الكود → الكود هو المرجع.*

- [Engine Router & IR](14_ENGINE_ROUTER_AND_IR.md)

- [Roadmap & AI Handoff](15_ROADMAP_AND_AI_HANDOFF.md) — **read first if continuing work**

## 6) تشغيل حي بعد التوليد (توكن)

1. بعد نجاح التوليد + بوابة anti-hallucination تُحفظ `pending_run` / `pending_live_run` / `pending_deploy` في الجلسة (ومخزن الجلسات).
2. المستخدم يرسل توكن `@BotFather` — يُعالج **قبل** رسالة «مايسترو يفكر» و**قبل** مسار الشات.
3. إن ضاعت الجلسة: يُستعاد آخر مشروع من `OUTPUT_DIR/users/<shard>/<id>/projects/`.
4. التشغيل عبر `live_runner` (تثبيت تبعيات → إقلاع). التقدم في رسالة حالة واحدة تُحدَّث.

## 7) رسائل واجهة مختصرة

- `QUIET_DELIVERY=1` (افتراضي): نتيجة التوليد = «✅ تم» بدل تقرير الطبقات الطويل.
- رسالة التفكير: `مايسترو يفكر...🤔` (تُحذف بعد الرد؛ لا تظهر مع مسار التوكن).

## 8) هوية المستخدم

- MongoDB فقط (`MONGODB_URI` → مجموعة `users`).
- كل رسالة و`/start` → `ensure_mongo_user` (إنشاء أو `last_seen` + `visit_count`).
