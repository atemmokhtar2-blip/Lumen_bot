# خطة تطوير شاملة لإعادة هيكلة محرك توليد بوتات التيليجرام
## Comprehensive Development Plan: Overhaul of the AI Translator & Code Generation Engine

---

## جدول المحتويات | Table of Contents

1. [الملخص التنفيذي | Executive Summary](#1-الملخص-التنفيذي--executive-summary)
2. [تحليل المعمارية الحالية | Current Architecture Analysis](#2-تحليل-المعمارية-الحالية--current-architecture-analysis)
3. [جرد القواعد الثابتة والقوالب | Hardcoded Rules & Templates Inventory](#3-جرد-القواعد-الثابتة-والقوالب--hardcoded-rules--templates-inventory)
4. [المشاكل الجوهرية | Core Problems](#4-المشاكل-الجوهرية--core-problems)
5. [المعمارية المقترحة | Proposed Architecture](#5-المعمارية-المقترحة--proposed-architecture)
6. [تطوير المترجم الذكي (SpecTranslator) | Upgrading the AI Translator](#6-تطوير-المترجم-الذكي-spectranslator--upgrading-the-ai-translator)
7. [تطوير محرك التوليد (Formal Engine) | Upgrading the Code Generation Engine](#7-تطوير-محرك-التوليد-formal-engine--upgrading-the-code-generation-engine)
8. [بوابة التثبيت المعمارية | Architectural Grounding Gate](#8-بوابة-التثبيت-المعمارية--architectural-grounding-gate)
9. [خطة التنفيذ بالمراحل | Phased Implementation Plan](#9-خطة-التنفيذ-بالمراحل--phased-implementation-plan)
10. [المعاير والاختبار | Benchmarks & Testing](#10-المعاير-والاختبار--benchmarks--testing)
11. [مخاطر وضمانات | Risks & Safeguards](#11-مخاطر-وضمانات--risks--safeguards)

---

## 1. الملخص التنفيذي | Executive Summary

### الهدف

المستخدم طلب تطوير المحرك الحالي بحيث:
- يفهم بشكل أعمق وما ينفذ أي شيء وهمي نهائيًا
- لا يعتمد على قوالب أو قواعد ثابتة نهائيًا — كل شيء يُفهم من محرك الترجمة (الذكاء الاصطناعي) فقط
- الذكاء الاصطناعي يترجم فقط بقوة، وضخ فهم غني في محرك التوليد
- تطوير الاثنين معًا "جامد جامد جدًا"

### الحل المقترح في سطور

نقوم بثورة معمارية من ثلاث طبقات: نستبدل المخطط المسطح (`_SYN`/`_SKIP_CMDS`/`_PROMPT`/...) **بمخطط فهم ديناميكي** يُبنى بالكامل من مخرجات المترجم الذكي، ونلغي رحلة النص الذهنية والإياب (text round-trip) التي تُفقد البيانات، ونعزز المترجم الذكي بمخطط JSON عميق متعدد المستويات مع تمرير تدقيق الأمانة (fidelity audit)، ونحوّل المحرك الرسمي من محرك قائم على القواعد إلى محرك **يستنتج هيكله من المخطط فقط** مع بوابة تثبيت معمارية تمنع أي وهم.

---

## 2. تحليل المعمارية الحالية | Current Architecture Analysis

### مسار التوليد الحالي (Current Pipeline)

```
نص المستخدم (عربي/إنجليزي)
  │
  ▼
[SpecTranslator] ── g4f LLM ──> JSON مسطح {commands, buttons, entities, rules, flows}
  │                               │
  │                               ▼ ground_spec() — يُسقط غير المثبّت
  │                               │
  ▼                               ▼
spec_to_text() ──> نص مقسّم (الأوامر:/الكيانات:/الأزرار:/القواعد:/التدفقات:)
  │                               ⚠️ رحلة نص ذهنية وإياب (lossy text round-trip)
  ▼
[extract_dsl] ── regex + synonyms ──> DSLProgram AST
  │                               ⚠️ إعادة تحليل نص أُنشئ بالفعل من JSON
  ▼
[grounding_gate] ─ـ _SYN synonyms ──> DSLProgram مُصفّى
  │                               ⚠️ مرادفات ثابتة لإعادة التثبيت
  ▼
[infer] ── _SKIP_CMDS/_INPUT_VERBS/_PROMPT ──> InferenceResult
  │                               ⚠️ تصنيف قائم على قوائم ثابتة
  ▼
[transpile/micro] ── cmd_kind() hardcoded ──> handlers.py, logic.py, models.py
  │                               ⚠️ قوالب معالجات حسب نوع ثابت
  ▼
[verify] ── AST parse + structural checks ──> VerificationReport
```

### الملفات الأساسية ومسؤولياتها

| الملف | السطور | الدور | يعتمد على قواعد ثابتة؟ |
|-------|--------|------|----------------------|
| `chat_ai/spec_translator.py` | 1041 | المترجم الذكي: نص → JSON → نص مقسّم | نعم (`_SYN` 45 مجموعة) |
| `formal_engine/pipeline_formal.py` | 81 | المنسق: extract → gate → infer → transpile → verify | لا |
| `formal_engine/dsl/extractor.py` | 1120 | مستخرج DSL من النص | نعم (`_GHOST`, `_ADMIN_CMDS`, `_SYN_GROUPS`, `noun_map`, `_SECTION_STOP`) |
| `formal_engine/dsl/ast.py` | 105 | تعريفات AST | لا |
| `formal_engine/inference/engine.py` | 471 | محرك الاستنتاج | نعم (`_INPUT_VERBS`, `_SKIP_CMDS`, `_PROMPT` 60 حقل, `_CMD_ENTITY_HINTS`) |
| `formal_engine/transpiler/micro.py` | 1096 | مولّد كود بايثون | نعم (`cmd_kind` قوائم ثابتة) |
| `formal_engine/verification/grounding_gate.py` | 281 | بوابة التثبيت | نعم (`_STRUCTURAL_CMDS`, `_SYN`) |
| `formal_engine/verification/verifier.py` | 149 | التحقق الرسمي | لا (فحص AST) |
| `formal_engine/schemas/program_contract.py` | 242 | عقد Pydantic بين الفهم والتوليد | لا (مخطط نظيف) |
| `formal_engine/schemas/formal_spec.py` | 209 | مخطط فهم غني (Pydantic) | لا |
| `formal_engine/services/clarification/service.py` | 450 | فحص الاكتمال + `_slug_cmd` | نعم (51 فرع if/elif) |
| `chat_ai/understanding_ai.py` | 306 | طبقة فهم g4f بديلة (معطّلة) | نعم (مخطط JSON مسطح) |
| `__init__.py` | 300 | نقطة الدخول `generate_bot()` | لا |

---

## 3. جرد القواعد الثابتة والقوالب | Hardcoded Rules & Templates Inventory

هذا هو الجرد الكامل لكل قاعدة ثابتة وقالب في النظام، مصنّفًا حسب الملف والمسؤولية. كل عنصر في هذا الجرد هو هدف للحذف أو الاستبدال بخاصية مستنتجة من المترجم الذكي.

### 3.1 المترجم الذكي (`spec_translator.py`)

| العنصر | العدد | الوصف | خطر الوهم |
|--------|------|------|----------|
| `_MODEL_CANDIDATES` | 6 نماذج | قائمة نماذج g4f بالترتيب | منخفض (بنية تحتية) |
| `_SYN` | 45 مجموعة مرادفات | مرادفات عربي/إنجليزي للتثبيت (register/order/track/...) | **عالٍ** — يحدد ما يُعتبر "مثبّتًا" |
| `_SYSTEM` prompt | مخطط JSON مسطح | commands[{name,description,admin_only,evidence}] / buttons / entities / rules / flows | متوسط — يقيّد عمق الفهم |
| `_REPAIR_SYSTEM` | تدقيق أمانة | يضيف/يحذف عناصر | منخفض |
| `spec_to_text()` | تحويل JSON→نص | يُعيد تحليله لاحقًا بـ extract_dsl | **عالٍ** — رحلة نص ضائعة |

**المشكلة الجوهرية:** المترجم ينتج JSON غنيًا ثم يحوّله إلى نص مقسّم، ثم يستخرج النص مرة أخرى إلى AST. هذا يعني أن المعلومات المنظمة (مثل أنواع الحقول، تسلسل التدفقات، علاقات الكيانات) تُفقد في الرحلة. JSON يحتوي على `evidence` و`steps` و`fields` لكنها تُسطح في النص.

### 3.2 مستخرج DSL (`extractor.py`)

| العنصر | العدد | الوصف |
|--------|------|------|
| `_GHOST` | 20+ كلمة | كلمات عامة تُستبعد (start/help/bot/telegram/...) |
| `_ADMIN_CMDS` | 6 كلمات | أوامر إدارية (admin/ban/mute/broadcast/stats/panel) |
| `_SYN_GROUPS` | 12 مجموعة | مجموعات إشارات (paid_success/success/create_record/...) |
| `_SECTION_STOP` | 30+ عنوان | عناوين أقسام بالعربي/الإنجليزي (الأوامر/الأزرار/القواعد/...) |
| `noun_map` | 6 كيانات | كيانات المجال (Customer/Driver/Order/Task/Product/Appointment) |
| `_field_word` | 10 حقول | أنماط حقول (name/phone/address/status/title/price/...) |
| `_infer_type` | 30+ حقل | تخمين نوع الحقل (int/bool/str) من الاسم |
| `_dynamic_intent` | 16 نمط | استنتاج النية من الأفعال (create/accept/reject/...) |
| `_resolve_create_target` | 40+ اسم | قائمة كيانات معروفة للمطابقة |

**المشكلة الجوهرية:** المستخرج يعيد تحليل نص أُنشئ بالفعل من JSON. هذا مضاعفة للجهد + فقدان للمعلومات. عندما يفشل المستخرج في مطابقة نمط، يُسقط العنصر حتى لو كان في JSON الأصلي.

### 3.3 محرك الاستنتاج (`inference/engine.py`)

| العنصر | العدد | الوصف |
|--------|------|------|
| `_INPUT_VERBS` | 26 فعل | أفعال تجميع البيانات (create/add/register/book/...) |
| `_LOOKUP_CMDS` | 8 أوامر | أوامر البحث (track/search/status/info/...) |
| `_MINE_CMDS` | 6 أوامر | أوامر البيانات الشخصية (progress/score/history/balance/...) |
| `_LIST_CMDS` | 10 أوامر | أوامر القوائم (list/menu/catalog/courses/products/...) |
| `_SKIP_CMDS` | 18 أمر | أوامر تُتجاوز في التدفقات (cancel/admin/broadcast/...) |
| `_SKIP_STEMS` | 11 جذر | جذور تُتجاوز (cancel/delete/remove/drop/...) |
| `_DESC_INPUT_HINTS` | 22 تلميح | تلميحات عربي/إنجليزي لجمع البيانات |
| `_CMD_ENTITY_HINTS` | 11 مجموعة | ربط الأوامر بالكيانات (register→student/order→order/...) |
| `_DESC_FIELD_MAP` | 30+ مجموعة | ربط وصف الأمر بالحقول (البريد→email/الاسم→name/...) |
| `_PROMPT` | 60 حقل | رسائل عربية لكل حقل معروف |
| `_col_type` | 30+ حقل | تخمين نوع العمود (int/bool/str) |
| `_pick_wizard_fields` | قائمة تفضيل | ترتيب حقول مفضلة (name/phone/address/email/...) |

**المشكلة الجوهرية:** تصنيف الأوامر (collect/lookup/mine/list/skip) قائم بالكامل على قوائم ثابتة. لو جاء أمر جديد مثل `/split_pdf` أو `/compress_file` لا يعرفه أي قائمة، يُصنّف كـ "action" ويُتجاوز. هذا هو السبب الجذري لعدم عمل الأوامر في النسخة القديمة.

### 3.4 المولّد (`transpiler/micro.py`)

| العنصر | الوصف |
|--------|------|
| `cmd_kind()` | دالة مستقلة تُصنّف الأوامر: stats/mine/list/mutate/broadcast/generic بقوائم ثابتة |
| `action_for_cmd()` | مطابقة الأوامر بأسماء الإجراءات |
| المعالج العام (generic handler) | يعرض عدد السجلات فقط — لا ينفذ منطق الأمر |
| `callback_handler` | معالج الأزرار — يحاول تخمين الأمر المرتبط |

**المشكلة الجوهرية:** المولّد له دالة `cmd_kind` منفصلة عن دالة الاستنتاج، بقوائم مختلفة. هذا يعني أن التصنيف قد يختلف بين المرحلتين، مما يسبب عدم اتساق.

### 3.5 بوابة التثبيت (`grounding_gate.py`)

| العنصر | الوصف |
|--------|------|------|
| `_STRUCTURAL_CMDS` | `{"start", "help"}` — أوامر هيكلية مسموحة دائمًا |
| `_SYN` (محلي) | مرادفات للتثبيت |
| `_text_has_cmd()` | يفحص تثبيت الأمر عبر الرموز/المرادفات |

### 3.6 خدمة التوضيح (`clarification/service.py`)

| العنصر | الوصف |
|--------|------|
| `_slug_cmd` | 51 فرع if/elif يحول التسميات العربية إلى معرفات أوامر |
| `_AR_TRANS` | جدول تحويل صوتي عربي→لاتيني |
| `_transliterate_ar()` | دالة تحويل صوتي |

---

## 4. المشاكل الجوهرية | Core Problems

### المشكلة 1: رحلة النص الضائعة (Lossy Text Round-Trip)

```
JSON غني ──spec_to_text()──> نص مقسّم ──extract_dsl()──> AST
         ⚠️ فقدان: أنواع الحقول، تسلسل التدفقات، علاقات الكيانات، evidence
```

المترجم الذكي ينتج JSON منظمًا يحتوي على معلومات غنية (أنواع الحقول، تسلسل خطوات التدفقات، علاقات الكيانات، أدلة التثبيت). ثم يُحوَّل هذا JSON إلى نص مقسّم، ثم يُعاد تحليل النص بواسطة `extract_dsl` باستخدام regex ومرادفات. في هذه الرحلة:

- أنواع الحقول تُفقد (JSON له `fields: ["name", "email"]` لكن النص يصبح `Student (name, email)` بدون أنواع)
- تسلسل التدفقات يُسطح (`flows: [{command: "register", steps: ["name", "email", "phone"]}]` يصبح `-/register يجمع name و email و phone`)
- علاقات الكيانات تُفقد
- أدلة التثبيت (`evidence`) تُحذف

### المشكلة 2: ازدواجية الفهم (Double Interpretation)

المترجم الذكي يفهم النص وينتج JSON. ثم المستخرج يعيد فهم النص المقسّم. هذا يعني أن الفهم يحدث مرتين، بطريقتين مختلفتين، بقواعد مختلفة. لو فهم المترجم أمرًا جديدًا لكن المستخرج لا يعرفه، يُسقط. لو فهم المستخرج شيئًا لم يقصده المترجم، يُضاف (وهم).

### المشكلة 3: التصنيف القائم على القوائم الثابتة (Hardcoded Classification)

تصنيف الأوامر (collect/lookup/mine/list/skip) هو ما يحدد ما إذا كان الأمر سيُولّد كتدفق متعدد الخطوات (wizard) أم معالجًا بسيطًا. هذا التصنيف قائم على قوائم ثابتة (`_INPUT_VERBS`, `_SKIP_CMDS`, ...). أي أمر جديد لا يعرفه أي قائمة يُصنّف كـ "action" ويُتجاوز، مما يعني عدم توليد أي منطق له.

### المشكلة 4: المخطط المسطح (Flat Schema)

مخطط المترجم الذكي مسطح: `commands[{name, description, admin_only, evidence}]`. لا يوجد:
- نوع الأمر (collect/lookup/list/mine/action) — يُستنتج لاحقًا بقوائم ثابتة
- الحقول التي يجمعها الأمر — يُستنتج من الوصف بقوائم ثابتة
- الكيان المرتبط بالأمر — يُستنتج بقوائم ثابتة
- سلوك الأمر (ماذا يفعل بعد الجمع) — لا يوجد أصلًا
- أنواع الحقول — لا توجد
- التحقق من الحقول (هل البريد صالح؟ هل الرقم؟) — لا توجد

### المشكلة 5: ازدواجية `cmd_kind`

محرك الاستنتاج له `_cmd_kind()` والمولّد له `cmd_kind()` منفصلة. القوائم مختلفة. التصنيف قد يختلف بين المرحلتين، مما يسبب عدم اتساق في الكود المولّد.

---

## 5. المعمارية المقترحة | Proposed Architecture

### المبدأ الأساسي

> **المترجم الذكي هو المصدر الوحيد للفهم. المحرك الرسمي هو المولّد الوحيد للكود. لا قوالب. لا قواعد ثابتة. كل شيء يُستنتج من المخطط.**

### المعمارية الجديدة

```
نص المستخدم (عربي/إنجليزي)
  │
  ▼
[SpecTranslator V2] ── g4f LLM (متعدد التمريرات) ──> RichSpec (JSON عميق)
  │                                                     │
  │  Pass 1: الاستخراج الأساسي                            │
  │  Pass 2: تدقيق الأمانة (إضافة/حذف)                     │
  │  Pass 3: الاستنتاج العميق (أنواع/تدفقات/سلوك)          │
  │  Pass 4: التثبيت ضد النص الأصلي                       │
  │                                                     │
  ▼                                                     ▼
[RichSpecValidator] ── Pydantic تحقق صارم ──> RichSpec مُتحقّق
  │                                                     │
  ▼                                                     ▼
[ArchitecturalGroundingGate] ─ـ تثبيت معماري ──> RichSpec مُثبّت
  │  (يُسقط أي عنصر ليس له evidence في النص الأصلي)        │
  ▼
[ContractBuilder] ── تحويل RichSpec → ProgramContract ──> ProgramContract
  │  (تحويل مباشر، لا رحلة نص، لا regex)                  │
  ▼
[SpecDrivenInference] ─ـ استنتاج من Contract فقط ──> InferenceResult
  │  (تدفقات، مخططات، إجراءات — كلها من Contract)          │
  ▼
[SpecDrivenTranspiler] ─ـ توليد كود من InferenceResult ──> ملفات المشروع
  │  (لا قوالب مجال، لا قوائم ثابتة)                       │
  ▼
[MultiLevelVerifier] ── تحقق متعدد المستويات ──> VerificationReport
  │  (AST + استيراد + اتساق منطقي + تشغيل فعلي)            │
```

### الفروق الجوهرية عن المعمارية الحالية

| الجانب | الحالي | المقترح |
|--------|--------|---------|
| نقل الفهم | JSON → نص → AST (ضائع) | JSON → ProgramContract (مباشر) |
| تصنيف الأوامر | قوائم ثابتة (`_SKIP_CMDS`, ...) | المترجم يُحدد النوع في المخطط |
| حقول التدفق | قوائم ثابتة (`_PROMPT`, `_DESC_FIELD_MAP`) | المترجم يُحدد الحقول والرسائل |
| ربط الكيانات | قوائم ثابتة (`_CMD_ENTITY_HINTS`) | المترجم يُحدد العلاقة |
| التثبيت | مرادفات ثابتة (`_SYN`) | تثبيت معماري بـ evidence من المخطط |
| المخطط | مسطح (5 حقول) | عميق (20+ حقول، متعدد المستويات) |
| `cmd_kind` | دالتان منفصلتان بقوائم مختلفة | حقل واحد في المخطط، يُقرأ مرة واحدة |

---

## 6. تطوير المترجم الذكي (SpecTranslator) | Upgrading the AI Translator

### 6.1 مخطط RichSpec الجديد

المخطط الجديد هو قلب التطوير. كل ما كان يُستنتج بقوائم ثابتة، الآن يُحدد في المخطط مباشرة من فهم الذكاء الاصطناعي.

```json
{
  "schema_version": "2.0",
  "bot_name": "string",
  "bot_type": "ecommerce | utility | admin | booking | education | delivery | custom",
  "language": "ar | en | mixed",

  "commands": [
    {
      "name": "register",
      "description": "تسجيل عميل جديد",
      "admin_only": false,
      "evidence": "المستخدم قال: تسجيل عميل جديد",

      "kind": "collect | lookup | list | mine | action | admin_action",
      "kind_evidence": "الأمر يجمع بيانات: الاسم والهاتف والعنوان",

      "entity": "Customer",
      "entity_evidence": "الكيان المرتبط هو العميل",

      "collects_fields": [
        {
          "key": "name",
          "label": "أرسل الاسم",
          "type": "str",
          "required": true,
          "validation": "non_empty",
          "evidence": "المستخدم طلب الاسم"
        },
        {
          "key": "phone",
          "label": "أرسل رقم الهاتف",
          "type": "str",
          "required": true,
          "validation": "phone",
          "evidence": "المستخدم طلب رقم الهاتف"
        }
      ],

      "post_action": {
        "type": "save_to_entity | show_list | show_stats | show_record | broadcast | confirm",
        "target": "Customer",
        "reply_template": "تم تسجيل {name} بنجاح. رقمك: {id}",
        "evidence": "المستخدم توقع رسالة تأكيد"
      },

      "flow_steps": ["name", "phone", "address"],
      "flow_evidence": "التسلسل من وصف المستخدم"
    }
  ],

  "entities": [
    {
      "name": "Customer",
      "fields": [
        {"name": "id", "type": "str", "primary_key": true},
        {"name": "name", "type": "str", "required": true},
        {"name": "phone", "type": "str", "required": true},
        {"name": "user_id", "type": "int", "auto": true}
      ],
      "evidence": "الكيان من: تسجيل عميل بالاسم والهاتف"
    }
  ],

  "buttons": [
    {
      "label": "تسجيل عميل",
      "callback_id": "cmd_register",
      "triggers_command": "register",
      "evidence": "الزر من قائمة المستخدم"
    }
  ],

  "rules": [
    {
      "text": "لو العميل دفع بنجاح يتم تأكيد الطلب",
      "kind": "conditional",
      "conditions": [
        {"left": "paid", "op": "truthy", "right": "true"}
      ],
      "effects": [
        {"kind": "set", "target": "status", "value": "confirmed"},
        {"kind": "reply", "target": "message", "value": "تم تأكيد الطلب"}
      ],
      "evidence": "القاعدة من نص المستخدم"
    }
  ],

  "flows": [
    {
      "command": "register",
      "steps": [
        {"key": "name", "prompt": "أرسل الاسم"},
        {"key": "phone", "prompt": "أرسل رقم الهاتف"}
      ],
      "evidence": "التدفق من تسلسل الحقول"
    }
  ],

  "roles": [
    {"name": "user", "allows": ["start", "help", "register", "track"]},
    {"name": "admin", "allows": ["admin", "broadcast", "stats"]}
  ],

  "tech_flags": {
    "database": true,
    "file_handling": false,
    "payments": false
  },

  "needs_clarification": false,
  "clarification_questions": [],
  "fidelity_notes": []
}
```

### 6.2 سلسلة التمريرات المتعددة (Multi-Pass Pipeline)

بدلًا من تمريرة واحدة، نستخدم أربع تمريرات متخصصة. كل تمريرة لها مهمة محددة وprompt مخصص. هذا يضمن عمق الفهم ويقلل الوهم لأن كل تمريرة تُدقق من قِبل التالية.

#### التمريرة 1: الاستخراج الأساسي (Extraction Pass)

**المهمة:** استخراج الأوامر والكيانات والأزرار والقواعد من النص. فقط ما ورد صراحة.

**الـ Prompt:**
```
أنت محلل مواصفات بوتات تيليجرام. استخرج من النص التالي:
1. كل أمر ذكره المستخدم (صراحة أو ضمنيًا كوظيفة)
2. كل كيان ذكره المستخدم (عميل/طلب/منتج/...)
3. كل زر ذكره المستخدم
4. كل قاعدة ذكرها المستخدم (لو...إذا...عند...)

قواعد صارمة:
- استخرج فقط ما ورد في النص. لا تخترع أوامرًا أو كيانات.
- لكل عنصر، اكتب evidence: الاقتباس المباشر من النص.
- لو لم تذكر الأوامر صراحة، استنتجها من الوظائف المذكورة.
- لا تكتب كودًا. أرجع JSON فقط.

المخطط المطلوب: [مخطط RichSpec الأساسي]
```

#### التمريرة 2: تدقيق الأمانة (Fidelity Audit Pass)

**المهمة:** مراجعة مخرجات التمريرة 1 مقابل النص الأصلي. إضافة ما فات. حذف ما ليس له أصل.

**الـ Prompt:**
```
أنت مدقق أمانة. لديك:
- النص الأصلي للمستخدم
- مواصفة مستخرجة (JSON)

مهمتك:
1. لكل أمر/كيان/زر/قاعدة في المواصفة: هل له أصل في النص؟ لو لا، اقترح حذفه.
2. هل فات شيء في النص لم يُستخرج؟ لو نعم، أضفه مع evidence.
3. هل الوصف صحيح لكل أمر؟ صحّح لو لزم.

أرجع JSON بـ:
- "add": [عناصر جديدة مع evidence]
- "remove": [أسماء عناصر تُحذف مع السبب]
- "fix": [{name, old_description, new_description}]
- "fidelity_notes": [ملاحظات]
```

#### التمريرة 3: الاستنتاج العميق (Deep Inference Pass)

**المهمة:** تعميق المواصفة بإضافة: نوع كل أمر، الحقول التي يجمعها، الكيان المرتبط، سلوك ما بعد التنفيذ، أنواع الحقول، التحقق. **هذه هي التمريرة التي تحل محل كل القوائم الثابتة.**

**الـ Prompt:**
```
أنت مهندس بوتات تيليجرام. لديك مواصفة مستخرجة. لكل أمر، حدد:

1. kind: نوع الأمر
   - "collect": يجمع بيانات من المستخدم (تسجيل/حجز/طلب)
   - "lookup": يبحث عن سجل موجود (تتبع/بحث/حالة)
   - "list": يعرض قائمة من السجلات (قائمة/منيو/كتالوج)
   - "mine": يعرض بيانات المستخدم الشخصية (ملفي/تقدمي/رصيدي)
   - "action": ينفذ إجراءً فوريًا (تأكيد/إلغاء/إشعار)
   - "admin_action": إجراء إداري (حظر/بث/إحصائيات)

2. collects_fields: لو kind=collect، ما الحقول التي يجمعها؟
   لكل حقل: key, label (رسالة عربية للمستخدم), type (str/int/bool/float),
   required, validation (non_empty/phone/email/number/choice)

3. entity: الكيان المرتبط بالأمر (لو وُجد)

4. post_action: ماذا يحدث بعد تنفيذ الأمر؟
   - type: save_to_entity / show_list / show_stats / show_record / broadcast / confirm / delete
   - target: الكيان المعني
   - reply_template: قالب الرد (استخدم {field} للمتغيرات)

5. flow_steps: لو kind=collect، ترتيب الحقول

استنتج من الأدلة (evidence) فقط. لو لم تكن متأكدًا، ضع null ولا تخمن.
أرجع JSON بالمواصفة المعمّقة.
```

#### التمريرة 4: التثبيت النهائي (Grounding Pass)

**المهمة:** فحص نهائي — كل عنصر يجب أن يكون له `evidence` مقتبس من النص الأصلي. حذف أي عنصر بلا evidence.

هذه التمريرة برمجية (لا LLM) — تطبيق قاعدة: لو `evidence` فارغ أو غير موجود في النص، يُحذف العنصر.

### 6.3 إدارة النماذج والتوافر

```python
# استراتيجية متعددة النماذج مع fallback
_PRIMARY_MODELS = [
    ("gemini-2.0-flash", "google"),     # الأسرع للأكواد المنظمة
    ("gpt-4o-mini", "openai"),          # fallback موثوق
    ("claude-3.5-sonnet", "anthropic"), # fallback للتعقيد
    ("llama-3.1-70b", "meta"),          # fallback أخير
]

# كل تمريرة لها نموذج مفضل:
_PASS_MODEL_PREFERENCE = {
    "extraction": ["gemini-2.0-flash", "gpt-4o-mini"],
    "fidelity":   ["gpt-4o-mini", "claude-3.5-sonnet"],
    "inference":  ["claude-3.5-sonnet", "gpt-4o-mini"],
    "grounding":  None,  # برمجي، لا LLM
}
```

### 6.4 إلغاء `_SYN` والمرادفات الثابتة

في المعمارية الجديدة، التثبيت لا يعتمد على مرادفات ثابتة. بدلًا من ذلك:

1. **التثبيت بـ evidence:** كل عنصر في المخطط له حقل `evidence` يحتوي على اقتباس مباشر من النص. التثبيت يفحص: هل `evidence` موجود فعلًا في النص الأصلي؟ (بحث نصي مباشر، لا مرادفات)

2. **التثبيت الدلالي (اختياري):** لو الـ evidence غير مطابق نصيًا لكن قريب، يمكن استخدام تشابه نصي (SequenceMatcher) ك fallback — لكن هذا في الـ gate المعماري، لا في المترجم.

هذا يُلغي الحاجة لـ 45 مجموعة `_SYN` في `spec_translator.py` و `_SYN` في `grounding_gate.py`.

---

## 7. تطوير محرك التوليد (Formal Engine) | Upgrading the Code Generation Engine

### 7.1 إلغاء رحلة النص — ContractBuilder مباشر

**الحالي:** `spec_to_text()` → `extract_dsl()` → `grounding_gate()` → `infer()`

**المقترح:** `RichSpec` → `ContractBuilder.build()` → `ProgramContract` → `SpecDrivenInference.infer()` → `SpecDrivenTranspiler.transpile()`

```python
# contract_builder.py — تحويل مباشر RichSpec → ProgramContract
class ContractBuilder:
    """
    يحول RichSpec (JSON من المترجم) إلى ProgramContract (Pydantic).
    لا regex. لا قوائم ثابتة. تحويل 1:1 مباشر.
    """

    def build(self, spec: RichSpec) -> ProgramContract:
        contract = ProgramContract(
            bot_name=spec.bot_name,
            bot_kind=self._map_bot_type(spec.bot_type),
            commands=[
                CommandUnit(
                    name=cmd.name,
                    description=cmd.description,
                    admin_only=cmd.admin_only,
                )
                for cmd in spec.commands
            ],
            entities=[
                EntityUnit(
                    name=ent.name,
                    fields=[
                        FieldUnit(name=f.name, field_type=self._map_type(f.type))
                        for f in ent.fields
                    ],
                )
                for ent in spec.entities
            ],
            buttons=[
                ButtonUnit(
                    label=btn.label,
                    callback_id=btn.callback_id,
                )
                for btn in spec.buttons
            ],
            flows=[
                FlowUnit(
                    name=fl.command,
                    steps=[
                        FlowStep(
                            id=f"step_{i}",
                            action=step.key,
                            label=step.prompt,
                        )
                        for i, step in enumerate(fl.steps)
                    ],
                )
                for fl in spec.flows
            ],
            # ... roles, tech_flags, etc.
        )
        return contract.ensure_minimums()
```

### 7.2 SpecDrivenInference — استنتاج من المخطط فقط

محرك الاستنتاج الجديد لا يستخدم أي قائمة ثابتة. كل شيء من المخطط:

```python
# inference/spec_driven.py
class SpecDrivenInference:
    """
    يستنتج التدفقات والمخططات والإجراءات من ProgramContract فقط.
    لا _SKIP_CMDS. لا _INPUT_VERBS. لا _PROMPT. لا _CMD_ENTITY_HINTS.
    """

    def infer(self, contract: ProgramContract) -> InferenceResult:
        result = InferenceResult()

        # 1. المخططات: مباشرة من الكيانات في Contract
        for ent in contract.entities:
            result.schemas.append(SchemaPlan(
                table=ent.name.lower(),
                columns=[
                    (f.name, self._type_from_field(f))
                    for f in ent.fields
                ],
            ))

        # 2. التدفقات: مباشرة من flows في Contract
        for fl in contract.flows:
            result.wizards.append({
                "id": fl.name,
                "command": fl.name,
                "entity": self._entity_for_flow(fl, contract),
                "kind": "collect",  # دائمًا collect لأن flows تُنشأ للأوامر التي تجمع
                "steps": [
                    {"key": step.action, "prompt": step.label}
                    for step in fl.steps
                ],
            })

        # 3. الأوامر بدون flows: من نوع الأمر في المخطط
        flow_cmds = {fl.name for fl in contract.flows}
        for cmd in contract.commands:
            if cmd.name in flow_cmds or cmd.name in ("start", "help"):
                continue
            # نوع الأمر من المخطط (ليس من قائمة ثابتة!)
            cmd_meta = self._cmd_meta(cmd.name, contract)
            result.command_handlers.append(cmd_meta)

        return result

    def _cmd_meta(self, name: str, contract: ProgramContract) -> dict:
        """
        يبني metadata للأمر من المخطط.
        نوع الأمر، الكيان، سلوك ما بعد التنفيذ — كلها من Contract.
        """
        # ابحث عن الأمر في RichSpec الأصلي (مُخزّن في Contract)
        spec_cmd = contract.command_specs.get(name)
        if not spec_cmd:
            return {"name": name, "kind": "generic", "handler": "echo"}

        return {
            "name": name,
            "kind": spec_cmd.kind,           # من المخطط!
            "entity": spec_cmd.entity,        # من المخطط!
            "post_action": spec_cmd.post_action,  # من المخطط!
            "collects_fields": spec_cmd.collects_fields,  # من المخطط!
            "handler": self._handler_template(spec_cmd),   # من المخطط!
        }
```

### 7.3 SpecDrivenTranspiler — توليد بلا قوالب مجال

المولّد الجديد يقرأ نوع الأمر وسلوكه من المخطط ويُولّد الكود المناسب. لا قوائم ثابتة، لا `cmd_kind()` منفصلة.

```python
# transpiler/spec_driven.py
class SpecDrivenTranspiler:
    """
    يولّد كود بايثون من InferenceResult.
    لا قوالب مجال. لا قوائم ثابتة. كل شيء من المخطط.
    """

    def transpile(self, inf: InferenceResult, out_dir: Path) -> list[str]:
        files = []
        files.append(self._emit_models(inf))
        files.append(self._emit_store(inf))
        files.append(self._emit_logic(inf))
        files.append(self._emit_handlers(inf))
        files.append(self._emit_main(inf))
        files.append(self._emit_config(inf))
        files.append(self._emit_requirements(inf))
        return files

    def _emit_handlers(self, inf: InferenceResult) -> str:
        """يولّد handlers.py من المخطط فقط."""
        lines = [...]

        # FLOWS dict — من inf.wizards (التي جاءت من Contract.flows)
        for w in inf.wizards:
            lines.append(f"    {w['command']}: [")
            for step in w['steps']:
                lines.append(f"        {{'key': '{step['key']}', 'prompt': '{step['prompt']}'}},")

        # معالج لكل أمر — من inf.command_handlers (التي جاءت من المخطط)
        for cmd_meta in inf.command_handlers:
            handler_code = self._handler_for_kind(cmd_meta)
            lines.extend(handler_code)

        return "\n".join(lines)

    def _handler_for_kind(self, cmd_meta: dict) -> list[str]:
        """
        يولّد معالج الأمر حسب نوعه وسلوكه من المخطط.
        لا قوائم ثابتة — كل شيء من cmd_meta.
        """
        kind = cmd_meta.get("kind", "generic")
        post = cmd_meta.get("post_action", {})
        entity = cmd_meta.get("entity")
        fields = cmd_meta.get("collects_fields", [])

        if kind == "collect" and fields:
            return self._collect_handler(cmd_meta)
        elif kind == "lookup":
            return self._lookup_handler(cmd_meta)
        elif kind == "list":
            return self._list_handler(cmd_meta)
        elif kind == "mine":
            return self._mine_handler(cmd_meta)
        elif kind == "action":
            return self._action_handler(cmd_meta)
        elif kind == "admin_action":
            return self._admin_action_handler(cmd_meta)
        else:
            return self._generic_handler(cmd_meta)

    def _collect_handler(self, cmd_meta: dict) -> list[str]:
        """
        معالج أمر تجميع البيانات.
        الحقول والرسائل من المخطط (لا _PROMPT!).
        سلوك ما بعد التنفيذ من المخطط (لا قوالب ثابتة!).
        """
        name = cmd_meta["name"]
        entity = cmd_meta.get("entity", "record")
        post = cmd_meta.get("post_action", {})
        reply_template = post.get("reply_template", f"تم تنفيذ {name}")

        return [
            f"async def {name}_handler(update, context):",
            f"    await _start_flow(update.message or update.callback_query.message, "
            f"context, '{name}')",
            "",
            # دالة معالجة إكمال التدفق — تُولّد من المخطط
            f"async def _complete_{name}(user_id, data):",
            f"    container = get_container()",
            f"    store = container.{entity.lower()}_store",
            f"    record = store.create(user_id=user_id, **data)",
            # رد من قالب المخطط
            f"    reply = f\"{reply_template}\".format(",
            *[f"        {f['key']}=data.get('{f['key']}')," for f in cmd_meta.get("collects_fields", [])],
            f"        id=record.get('id', ''),",
            f"    )",
            f"    return reply",
        ]
```

### 7.4 إلغاء جميع القوائم الثابتة

هذا جدول الإلغاء/الاستبدال لكل قائمة ثابتة:

| الملف | العنصر الثابت | الإلغاء/الاستبدال |
|------|--------------|------------------|
| `inference/engine.py` | `_INPUT_VERBS` (26) | **حذف** — المترجم يُحدد `kind: "collect"` في المخطط |
| `inference/engine.py` | `_LOOKUP_CMDS` (8) | **حذف** — المترجم يُحدد `kind: "lookup"` |
| `inference/engine.py` | `_MINE_CMDS` (6) | **حذف** — المترجم يُحدد `kind: "mine"` |
| `inference/engine.py` | `_LIST_CMDS` (10) | **حذف** — المترجم يُحدد `kind: "list"` |
| `inference/engine.py` | `_SKIP_CMDS` (18) | **حذف** — لا حاجة للتخطي، كل أمر له نوع |
| `inference/engine.py` | `_SKIP_STEMS` (11) | **حذف** — نفس السبب |
| `inference/engine.py` | `_DESC_INPUT_HINTS` (22) | **حذف** — المترجم يُحدد `collects_fields` |
| `inference/engine.py` | `_CMD_ENTITY_HINTS` (11) | **حذف** — المترجم يُحدد `entity` |
| `inference/engine.py` | `_DESC_FIELD_MAP` (30+) | **حذف** — المترجم يُحدد الحقول وأنواعها |
| `inference/engine.py` | `_PROMPT` (60) | **حذف** — المترجم يُحدد `label` لكل حقل |
| `inference/engine.py` | `_col_type` (30+) | **حذف** — المترجم يُحدد `type` لكل حقل |
| `inference/engine.py` | `_pick_wizard_fields` | **حذف** — الحقول من المخطط مباشرة |
| `transpiler/micro.py` | `cmd_kind()` | **حذف** — النوع من المخطط، لا دالة منفصلة |
| `transpiler/micro.py` | `action_for_cmd()` | **حذف** — الإجراء من `post_action` في المخطط |
| `extractor.py` | `_GHOST` (20+) | **تبسيط** — قائمة هيكلية صغيرة (start/help/bot) فقط |
| `extractor.py` | `_ADMIN_CMDS` (6) | **حذف** — المترجم يُحدد `admin_only` |
| `extractor.py` | `_SYN_GROUPS` (12) | **حذف** — القواعد من المخطط مباشرة |
| `extractor.py` | `noun_map` (6) | **حذف** — الكيانات من المخطط مباشرة |
| `extractor.py` | `_field_word` (10) | **حذف** — الحقول من المخطط مباشرة |
| `extractor.py` | `_dynamic_intent` (16) | **حذف** — النية من المخطط |
| `extractor.py` | `_resolve_create_target` (40+) | **حذف** — الكيان من المخطط |
| `grounding_gate.py` | `_STRUCTURAL_CMDS` | **إبقاء** — start/help هيكلية فقط |
| `grounding_gate.py` | `_SYN` (محلي) | **حذف** — التثبيت بـ evidence |
| `spec_translator.py` | `_SYN` (45) | **حذف** — التثبيت بـ evidence |
| `clarification/service.py` | `_slug_cmd` (51) | **حذف** — المترجم يُحدد `name` بالإنجليزية مباشرة |
| `clarification/service.py` | `_AR_TRANS` | **حذف** — المترجم يتعامل مع العربية |

**ملاحظة عن `extractor.py`:** في المعمارية الجديدة، المستخرج يُستخدم فقط كـ **fallback** عندما يفشل المترجم الذكي تمامًا (مثلًا جميع نماذج g4f معطّلة). في الوضع الطبيعي، المترجم يُنتج `RichSpec` مباشرة ويُمرّر إلى `ContractBuilder` دون المرور بالمستخرج. المستخرج المبسّط يُبقى كـ fallback نهائي فقط.

### 7.5 دور `extractor.py` الجديد — Fallback مبسّط

لو فشل المترجم الذكي تمامًا، نحتاج fallback. لكن هذا الـ fallback يجب أن يكون بسيطًا ولا يدّعي فهمًا عميقًا:

```python
# extractor.py الجديد — fallback فقط
def extract_dsl_minimal(text: str) -> DSLProgram:
    """
    Fallback نهائي فقط. يستخرج:
    - أوامر /صريحة فقط
    - لا استنتاج كيانات من الكلمات
    - لا تصنيف أوامر
    - لا مرادفات

    لو فشل المترجم الذكي، يُفضّل أن نطلب من المستخدم التوضيح
    بدلًا من تخمين خاطئ.
    """
    # فقط أوامر /صريحة
    commands = []
    for m in re.finditer(r'/([a-zA-Z][a-zA-Z0-9_]{1,32})', text):
        commands.append(CommandNode(name=m.group(1), description=m.group(1)))

    # start/help دائمًا
    ensure_start_help(commands)

    # لا كيانات، لا أزرار، لا قواعد، لا استنتاج
    # المترجم الذكي هو المسؤول عن الفهم العميق
    return DSLProgram(
        commands=commands,
        entities=[],
        buttons=[],
        rules=[],
        # ...
    )
```

---

## 8. بوابة التثبيت المعمارية | Architectural Grounding Gate

### 8.1 مبدأ التثبيت الجديد

التثبيت في المعمارية الجديدة لا يعتمد على مرادفات ثابتة. بدلًا من ذلك، كل عنصر في المخطط له `evidence` — اقتباس مباشر من النص الأصلي. بوابة التثبيت تفحص:

1. **هل `evidence` موجود في النص الأصلي؟** (بحث نصي مباشر)
2. **لو غير مطابق نصيًا، هل قريب دلاليًا؟** (تشابه نصي ≥ 0.7)
3. **لو لا هذا ولا ذاك، يُحذف العنصر** (منع الوهم)

### 8.2 تنفيذ البوابة

```python
# verification/architectural_grounding.py
class ArchitecturalGroundingGate:
    """
    تثبيت معماري: كل عنصر يجب أن يكون له evidence في النص الأصلي.
    لا مرادفات ثابتة. لا قوائم كلمات.
    """

    def gate(self, spec: RichSpec, original_text: str) -> RichSpec:
        text_lower = original_text.lower()
        text_normalized = self._normalize(original_text)

        # تصفية الأوامر
        grounded_commands = []
        for cmd in spec.commands:
            if cmd.name in ("start", "help"):  # هيكلية فقط
                grounded_commands.append(cmd)
                continue
            if self._evidence_grounded(cmd.evidence, text_lower, text_normalized):
                grounded_commands.append(cmd)
            else:
                self._log_drop("command", cmd.name, cmd.evidence)

        # تصفية الكيانات، الأزرار، القواعد بنفس الطريقة
        ...

        return spec.copy_with(
            commands=grounded_commands,
            entities=grounded_entities,
            # ...
        )

    def _evidence_grounded(self, evidence: str, text_lower: str, text_normalized: str) -> bool:
        if not evidence:
            return False
        ev = evidence.strip().lower()
        ev_norm = self._normalize(evidence)
        # 1. مطابقة نصية مباشرة
        if ev in text_lower or ev_norm in text_normalized:
            return True
        # 2. تشابه دلالي (fallback)
        # اقسم النص إلى جمل وابحث عن أعلى تشابه
        sentences = re.split(r'[.!\n؟]', text_normalized)
        best_sim = max(
            SequenceMatcher(None, ev_norm, sent.strip()).ratio()
            for sent in sentences if sent.strip()
        )
        return best_sim >= 0.7  # عتبة عالية لمنع الوهم
```

### 8.3 منع الحلقة الذاتية للوهم

في المعمارية الحالية، هناك خطر: المترجم يُنتج نصًا، ثم يُثبّت ضد النص الأصلي، لكن الـ `grounding_src` في `__init__.py` يُضبط على `original_request` — وهذا صحيح. يجب الحفاظ على هذا المبدأ:

> **التثبيت دائمًا ضد النص الأصلي للمستخدم، أبدًا ضد مخرجات المترجم.**

في المعمارية الجديدة، نفس المبدأ لكن أقوى: `evidence` في المخطط يجب أن يكون اقتباسًا من النص الأصلي، والبوابة تفحص ذلك.

---

## 9. خطة التنفيذ بالمراحل | Phased Implementation Plan

### المرحلة 0: التحضير (يوم 1)

- [ ] إنشاء branch جديد `feat/spec-driven-engine-v2`
- [ ] كتابة اختبارات للمعمارية الحالية (baseline tests) لتأكيد عدم الانكسار
- [ ] توثيق حالة الاختبار المرجعية (10 مواصفات متنوعة عربية/إنجليزية)

### المرحلة 1: مخطط RichSpec (يوم 2-3)

**الملفات:**
- `chat_ai/rich_spec.py` (جديد) — تعريفات Pydantic لـ RichSpec
- `chat_ai/spec_translator.py` (تعديل) — إضافة مخطط V2، إبقاء V1 كـ fallback

**المهام:**
- [ ] تعريف `RichSpec`, `CommandSpec`, `EntitySpec`, `ButtonSpec`, `RuleSpec`, `FlowSpec`, `FieldSpec`, `PostAction` كـ Pydantic models
- [ ] تعريف `RichSpecValidator` للتحقق الصارم
- [ ] تحديث `_SYSTEM` prompt للمخطط الجديد
- [ ] إضافة `_PASS_MODEL_PREFERENCE` للتمريرات المتعددة
- [ ] كتابة اختبارات للتحقق من صحة المخطط

**معايير القبول:**
- مخطط Pydantic يتحقق من RichSpec صالحًا ويرفض غير الصالح
- المترجم يُنتج RichSpec يتبع المخطط

### المرحلة 2: سلسلة التمريرات المتعددة (يوم 3-5)

**الملفات:**
- `chat_ai/spec_translator.py` (تعديل كبير)
- `chat_ai/passes/extraction_pass.py` (جديد)
- `chat_ai/passes/fidelity_pass.py` (جديد)
- `chat_ai/passes/inference_pass.py` (جديد)
- `chat_ai/passes/grounding_pass.py` (جديد)

**المهام:**
- [ ] فصل التمريرات الأربع إلى ملفات منفصلة
- [ ] كل تمريرة لها prompt مخصص ونموذج مفضل
- [ ] التمريرة 4 (التثبيت) برمجية — لا LLM
- [ ] إدارة Fallback: لو فشلت تمريرة، نتيجة سابقة تُمرّر للتالية
- [ ] إضافة timeout وretry لكل تمريرة
- [ ] كتابة اختبارات لكل تمريرة

**معايير القبول:**
- 4 تمريرات تُنفّذ بالتسلسل
- كل تمريرة تُحسّن المواصفة
- Fallback يعمل عند فشل نموذج

### المرحلة 3: ContractBuilder (يوم 5-6)

**الملفات:**
- `formal_engine/contract_builder.py` (جديد)
- `formal_engine/schemas/program_contract.py` (تعديل — إضافة command_specs)

**المهام:**
- [ ] كتابة `ContractBuilder.build(rich_spec) -> ProgramContract`
- [ ] تحويل مباشر 1:1 — لا regex، لا قوائم
- [ ] إضافة `command_specs: dict[str, CommandSpec]` إلى `ProgramContract` لحفظ metadata الأوامر
- [ ] كتابة اختبارات للتحويل

**معيار القبول:**
- `ContractBuilder` يحول RichSpec إلى ProgramContract بدون فقدان معلومات

### المرحلة 4: SpecDrivenInference (يوم 6-7)

**الملفات:**
- `formal_engine/inference/spec_driven.py` (جديد)
- `formal_engine/inference/engine.py` (إبقاء كـ fallback فقط)

**المهام:**
- [ ] كتابة `SpecDrivenInference.infer(contract) -> InferenceResult`
- [ ] التدفقات من `contract.flows` مباشرة
- [ ] المخططات من `contract.entities` مباشرة
- [ ] أنواع الأوامر من `contract.command_specs` مباشرة
- [ ] **حذف** `_INPUT_VERBS`, `_SKIP_CMDS`, `_PROMPT`, `_CMD_ENTITY_HINTS`, `_DESC_FIELD_MAP`
- [ ] كتابة اختبارات

**معيار القبول:**
- الاستنتاج من Contract فقط، لا قوائم ثابتة
- نفس النتيجة للمواصفات المتطابقة

### المرحلة 5: SpecDrivenTranspiler (يوم 7-9)

**الملفات:**
- `formal_engine/transpiler/spec_driven.py` (جديد)
- `formal_engine/transpiler/micro.py` (إبقاء كـ fallback فقط)

**المهام:**
- [ ] كتابة `SpecDrivenTranspiler.transpile(inf, out_dir) -> files`
- [ ] `_emit_handlers` من المخطط فقط
- [ ] `_handler_for_kind` يقرأ النوع من المخطط
- [ ] **حذف** `cmd_kind()` المنفصلة
- [ ] توليد `logic.py` من `post_action` في المخطط
- [ ] توليد `models.py` من `entities` في المخطط
- [ ] كتابة اختبارات

**معيار القبول:**
- الكود المولّد يتبع المخطط تمامًا
- لا قوائم ثابتة في المولّد

### المرحلة 6: بوابة التثبيت المعمارية (يوم 9-10)

**الملفات:**
- `formal_engine/verification/architectural_grounding.py` (جديد)
- `formal_engine/verification/grounding_gate.py` (إبقاء لـ fallback)

**المهام:**
- [ ] كتابة `ArchitecturalGroundingGate.gate(spec, original_text)`
- [ ] تثبيت بـ evidence — لا مرادفات ثابتة
- [ ] تشابه دلالي كـ fallback (عتبة 0.7)
- [ ] **حذف** `_SYN` من `grounding_gate.py` و `spec_translator.py`
- [ ] كتابة اختبارات

**معيار القبول:**
- العناصر بلا evidence تُحذف
- العناصر بـ evidence صادق تُبقى

### المرحلة 7: تجميع الـ Pipeline الجديد (يوم 10-11)

**الملفات:**
- `formal_engine/pipeline_formal.py` (تعديل)
- `__init__.py` (تعديل)

**المهام:**
- [ ] تحديث `build_from_text()` لاستخدام الـ pipeline الجديد
- [ ] تحديث `generate_bot()` في `__init__.py`
- [ ] Fallback: لو فشل المترجم، استخدم `extract_dsl_minimal` بدل المستخرج الكامل
- [ ] كتابة اختبارات تكاملية (end-to-end)

**معيار القبول:**
- Pipeline كامل يعمل من النص إلى المشروع
- Fallback يعمل عند فشل المترجم

### المرحلة 8: تبسيط خدمة التوضيح (يوم 11-12)

**الملفات:**
- `formal_engine/services/clarification/service.py` (تعديل كبير)

**المهام:**
- [ ] **حذف** `_slug_cmd` (51 فرع) و `_AR_TRANS`
- [ ] المترجم يُحدد `name` بالإنجليزية مباشرة في المخطط
- [ ] خدمة التوضيح تفحص الاكتمال من المخطط فقط
- [ ] كتابة اختبارات

**معيار القبول:**
- لا فرع if/elif ثابت في `_slug_cmd`
- أسماء الأوامر من المخطط

### المرحلة 9: التحقق متعدد المستويات (يوم 12-13)

**الملفات:**
- `formal_engine/verification/verifier.py` (تعديل)

**المهام:**
- [ ] المستوى 1: AST parse (موجود)
- [ ] المستوى 2: استيراد/أسماء (موجود)
- [ ] المستوى 3: اتساق منطقي (كل أمر له معالج، كل زر له callback)
- [ ] المستوى 4: تشغيل فعلي — استيراد المشروع وتشغيل معالج وهمي
- [ ] كتابة اختبارات

**معيار القبول:**
- 4 مستويات تحقق تعمل
- الأخطاء تُكشف قبل التسليم

### المرحلة 10: اختبار شامل ومعاير (يوم 13-14)

**المهام:**
- [ ] اختبار 10 مواصفات متنوعة (قسم 10)
- [ ] مقارنة قبل/بعد: عدد الأوامر المولّدة، الأوامر العاملة، الكود المولّد
- [ ] اختبار fallback عند فشل المترجم
- [ ] اختبار منع الوهم (مواصفات بأوامر غير موجودة)
- [ ] توثيق النتائج

**معيار القبول:**
- جميع المعاير تتحسن عن الحالي
- لا انكسار في الحالات الحالية

---

## 10. المعاير والاختبار | Benchmarks & Testing

### 10.1 مواصفات الاختبار المرجعية

10 مواصفات متنوعة لاختبار شامل:

1. **بوت متجر إلكتروني** (عربي): تسجيل عميل، عرض المنتجات، طلب، تتبع الطلب، دفع
2. **بوت حجوزات مواعيد** (عربي): حجز موعد، عرض المواعيد المتاحة، إلغاء موعد
3. **بوت إداري** (عربي): لوحة تحكم، إحصائيات، حظر مستخدم، بث رسالة
4. **بوت تعليمي** (عربي): تسجيل طالب، عرض الكورسات، التسجيل في كورس، عرض الدرجات
5. **بوت توصيل** (عربي): تسجيل سائق، استلام طلبات، تحديث حالة التوصيل
6. **بوت أدوات PDF** (عربي): تقسيم ملف، دمج ملف، ضغط ملف، تحويل صيغة
7. **بوت دعم فني** (إنجليزي): open ticket, track ticket, close ticket, rate support
8. **بوت إشعارات** (إنجليزي): subscribe, unsubscribe, notifications list, settings
9. **بوت محفظة** (عربي): رصيدي، إيداع، سحب، سجل المعاملات
10. **بوت مخصص معقد** (مختلط): ميزات غير قياسية لاختبار عدم الاعتماد على القوالب

### 10.2 مقاييس القياس

| المقياس | الحالي (مقدّر) | الهدف |
|--------|--------------|------|
| نسبة الأوامر المولّدة التي تعمل | ~30% | ≥ 95% |
| متوسط عدد الأوامر المستخرجة من نص غني | 1-3 | ≥ 80% من المذكورة |
| وقت التوليد (مع المترجم) | 10-30s | 15-40s (قبول زيادة للجودة) |
| وقت التوليد (fallback بدون مترجم) | 2-3s | 2-3s |
| عناصر وهمية في الكود المولّد | متكررة | صفر |
| قواعد ثابتة في الكود | ~250 | ≤ 10 (هيكلية فقط) |
| أحجام الملفات (extractor + inference + transpiler) | ~2700 سطر | ~1200 سطر |

### 10.3 اختبارات منع الوهم

```python
def test_no_hallucinated_commands():
    """مواصفة بسيطة بأمرين فقط — التأكد من عدم توليد أوامر إضافية."""
    spec = "اعمل بوت فيه /start و /help فقط"
    result = generate_bot(spec)
    commands = result.metadata["commands"]
    assert set(commands) == {"start", "help"}

def test_no_hallucinated_entities():
    """مواصفة بدون كيانات — التأكد من عدم تخمين كيانات."""
    spec = "بوت يرد على الرسائل بصوت"
    result = generate_bot(spec)
    # لا يجب أن يكون هناك كيانات
    assert len(result.metadata.get("entities", [])) == 0

def test_evidence_grounding():
    """كل أمر يجب أن يكون له evidence في النص الأصلي."""
    spec = "بوت متجر: تسجيل عميل، عرض المنتجات"
    result = generate_bot(spec)
    # كل أمر مولّد يجب أن يكون له أصل في النص
    for cmd in result.metadata["commands"]:
        assert cmd_has_evidence(cmd, spec)
```

---

## 11. مخاطر وضمانات | Risks & Safeguards

### المخاطر وطرق التخفيف

| الخطر | الاحتمال | التأثير | التخفيف |
|------|--------|--------|---------|
| فشل جميع نماذج g4f | متوسط | عالٍ | Fallback إلى `extract_dsl_minimal` + طلب توضيح من المستخدم |
| بطء التمريرات المتعددة (4 تمريرات LLM) | عالٍ | متوسط | تمريرات متوازية حيث ممكن، timeout لكل تمريرة، تخزين مؤقت |
| المترجم يُنتج مخطط غير صالح | متوسط | عالٍ | `RichSpecValidator` صارم + تمريرة إصلاح + fallback |
| زيادة الاعتماد على g4f | عالٍ | متوسط | Fallback قوي، طلب توضيح بدل التخمين |
| فقدان السرعة (من 3s إلى 20s+) | مؤكد | منخفض | جودة أعلى تستحق الوقت؛ خيار سريع للمواصفات البسيطة |
| الوهم من المترجم نفسه | متوسط | عالٍ | بوابة تثبيت معمارية + تمريرة تدقيق الأمانة + evidence إجباري |

### مبدأ التخفيف الأساسي

> **لو لم نكن متأكدين، نسأل بدل أن نخمن.** هذا هو المبدأ الذي يحل مشكلة الوهم نهائيًا. الـ fallback ليس تخمينًا — بل طلب توضيح من المستخدم. المترجم الذكي إما يفهم بثقة (مع evidence) أو يعترف بأنه بحاجة لتوضيح.

### ضمانات عدم الانكسار

1. **إبقاء الـ pipeline القديم كـ fallback:** `extractor.py` و `inference/engine.py` و `transpiler/micro.py` لا تُحذف بل تُبقى كـ fallback نهائي
2. **اختبارات المرجعية:** 10 مواصفات تُختبر قبل وبعد
3. **تبديل تدريجي:** flag بيئي `SPEC_ENGINE_V2=1` لتفعيل الـ pipeline الجديد، القديم افتراضي حتى التحقق الكامل
4. **مراجعة كل مرحلة:** كل مرحلة لها معايير قبول قبل الانتقال

---

## ملخص خطة التنفيذ | Implementation Summary

| المرحلة | المدة | المخرجات |
|--------|------|---------|
| 0. التحضير | يوم 1 | branch، اختبارات مرجعية |
| 1. مخطط RichSpec | يوم 2-3 | `rich_spec.py`, مخطط Pydantic |
| 2. تمريرات متعددة | يوم 3-5 | 4 ملفات passes، سلسلة LLM |
| 3. ContractBuilder | يوم 5-6 | `contract_builder.py` |
| 4. SpecDrivenInference | يوم 6-7 | `spec_driven.py`، حذف قوائم |
| 5. SpecDrivenTranspiler | يوم 7-9 | `spec_driven.py`، حذف cmd_kind |
| 6. بوابة تثبيت معمارية | يوم 9-10 | `architectural_grounding.py` |
| 7. تجميع Pipeline | يوم 10-11 | pipeline جديد، fallback |
| 8. تبسيط التوضيح | يوم 11-12 | حذف `_slug_cmd` |
| 9. تحقق متعدد المستويات | يوم 12-13 | 4 مستويات تحقق |
| 10. اختبار شامل | يوم 13-14 | معاير، توثيق |

**الإجمالي: ~14 يوم عمل**

---

## الملفات الجديدة والمُعدّلة | Files Summary

### ملفات جديدة

| الملف | الوصف |
|------|------|
| `chat_ai/rich_spec.py` | تعريفات Pydantic لـ RichSpec |
| `chat_ai/passes/extraction_pass.py` | التمريرة 1: استخراج أساسي |
| `chat_ai/passes/fidelity_pass.py` | التمريرة 2: تدقيق أمانة |
| `chat_ai/passes/inference_pass.py` | التمريرة 3: استنتاج عميق |
| `chat_ai/passes/grounding_pass.py` | التمريرة 4: تثبيت برمجي |
| `formal_engine/contract_builder.py` | تحويل RichSpec → ProgramContract |
| `formal_engine/inference/spec_driven.py` | استنتاج من Contract |
| `formal_engine/transpiler/spec_driven.py` | توليد من InferenceResult |
| `formal_engine/verification/architectural_grounding.py` | تثبيت معمارى بـ evidence |

### ملفات مُعدّلة

| الملف | التغيير |
|------|--------|
| `chat_ai/spec_translator.py` | مخطط V2، تمريرات متعددة، حذف `_SYN` |
| `formal_engine/pipeline_formal.py` | pipeline جديد |
| `formal_engine/schemas/program_contract.py` | إضافة `command_specs` |
| `formal_engine/inference/engine.py` | تُبقى كـ fallback فقط |
| `formal_engine/transpiler/micro.py` | تُبقى كـ fallback فقط |
| `formal_engine/verification/grounding_gate.py` | تُبقى كـ fallback |
| `formal_engine/verification/verifier.py` | 4 مستويات تحقق |
| `formal_engine/services/clarification/service.py` | حذف `_slug_cmd` |
| `formal_engine/dsl/extractor.py` | تبسيط لـ fallback نهائي |
| `__init__.py` | pipeline جديد + flag |

---

*هذه الوثيقة هي خطة تطوير شاملة قابلة للتنفيذ. كل مرحلة لها معايير قبول واضحة، وكل قاعدة ثابتة لها هدف حذف أو استبدال. المبدأ الأساسي: المترجم الذكي هو المصدر الوحيد للفهم، والمحرك الرسمي هو المولّد الوحيد للكود، ولا وهم نهائيًا.*
