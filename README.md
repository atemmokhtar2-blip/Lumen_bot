# AI Agent 7h Bot Engine 🤖

محرك توليد بوتات تيليجرام من وصف طبيعي — **عام لجميع مستخدمي تيليجرام**.

التوليد حالياً يتم عبر مسار **حتمي (zero-AI)** باستخدام presets + محركات برمجة محددة مسبقاً.  
لا يعتمد توليد المشروع على OpenAI / Groq / Hugging Face.

> مسار الـ AI (Execution Planner + Codegen) **معطّل نهائياً** في `generate_bot`.  
> طبقة الدردشة الذكية (اختياري) قد تستخدم مزودي AI للردود فقط، وليست جزءاً من توليد الكود.

---

## المسار النشط (التوليد)

```text
وصف المستخدم
  → فهم الطلب + اختيار preset مناسب (spec_core)
  → محركات برمجة حتمية (coding / structure / handlers)
  → ملفات مشروع جاهزة داخل sandbox خاص بالمستخدم
```

---

## لمن البوت؟

- **عام**: يقبل جميع مستخدمي تيليجرام بشكل افتراضي (نمط SaaS / نمو).
- يمكن تقييده لاحقاً عبر:
  - `ALLOWED_USER_IDS=123,456`
  - أو `LOCK_BOT_TO_ALLOWLIST=1`

---

## العزل القوي (Isolation) — حماية البوت الأساسي

كل مستخدم يعمل داخل **مساحة معزولة** خاصة به، ولا يمكنه التأثير على البوت الرئيسي أو على مستخدمين آخرين:

### 1. عزل الملفات (User Sandbox)
```
OUTPUT_DIR/users/<shard>/<telegram_user_id>/
  ├── projects/     # البوتات المولّدة لهذا المستخدم فقط
  ├── clones/       # استنساخات git خاصة به
  ├── runtime/      # سجلات وعلامات تشغيل
  └── index.json
```

### 2. عزل التشغيل (Docker مفضّل)
عند توفر Docker يتم تشغيل كل بوت مولّد داخل حاوية منفصلة مع:

| الحماية                    | التفاصيل                                      |
|---------------------------|-----------------------------------------------|
| اسم فريد                  | `tbe-u{user_id}-{id}`                         |
| حدود موارد                | memory ≈ 192m · CPUs ≈ 0.4 · pids ≈ 48       |
| ulimits                   | nproc=32 · nofile=128                         |
| capabilities              | `--cap-drop ALL`                              |
| privileges                | `no-new-privileges:true`                      |
| نظام الملفات              | `--read-only` + tmpfs محدود لـ `/tmp`         |
| الشبكة                    | bridge فقط (خروج لـ Telegram API، بدون ports) |
| البيئة                    | توكن البوت فقط — **لا** مفاتيح AI ولا توكن المضيف |
| المستخدم داخل الحاوية     | non-root (65534) عند الإمكان                  |
| إعادة التشغيل            | `--restart no`                                |
| حجم اللوجات               | max 2m × 2 ملفات                              |

### 3. العزل المحلي (Fallback)
إذا لم يتوفر Docker:
- حدود `resource` (CPU / memory / nproc / nofile / no core dumps)
- بيئة نظيفة عبر `clean_child_env` (لا ترث توكن البوت الأساسي ولا مفاتيح AI)
- تشغيل داخل مجلد المستخدم فقط

### 4. حدود إضافية
- Rate limit افتراضي: 12 رسالة / دقيقة لكل مستخدم
- حد أقصى للمشاريع لكل مستخدم (`MAX_PROJECTS_PER_USER=50`)

---

## المتطلبات

```bash
pip install -r requirements.txt
```

### متغيرات البيئة الأساسية

```env
# إلزامي
TELEGRAM_BOT_TOKEN=          # توكن البوت الأساسي (من BotFather)

# الوصول (افتراضي = عام للجميع)
# ALLOWED_USER_IDS=          # قائمة معرفات مسموح بها (اختياري)
# LOCK_BOT_TO_ALLOWLIST=1    # قفل البوت على القائمة فقط
# ALLOW_ALL_USERS=1          # تأكيد الوضع العام (الافتراضي)

# حدود الاستخدام
# RATE_LIMIT_PER_MINUTE=12
# MAX_PROJECTS_PER_USER=50
# OUTPUT_DIR=/tmp/generated

# العزل عبر Docker (مُفعّل تلقائياً عند توفر Docker)
# TBE_PREFER_DOCKER=1
# TBE_DOCKER_IMAGE=python:3.11-slim
# TBE_DOCKER_MEMORY=192m
# TBE_DOCKER_CPUS=0.4
# TBE_DOCKER_PIDS=48
# TBE_DOCKER_USER=65534:65534

# مزودو AI (اختياري — للردود الذكية فقط، وليس لتوليد الكود)
# OPENAI_API_KEY=
# HF_TOKEN=
# GROQ_API_KEY=
# AI_PROVIDER_ORDER=openai,hf,groq
```

---

## التشغيل

```bash
python main.py
```

أو برمجياً:

```python
from telegram_bot_engine import generate_bot

result = generate_bot("بوت يرد على الرسائل ويحفظ الملاحظات")
if result.success:
    print("المشروع جاهز في:", result.project_path)
else:
    print("أخطاء:", result.errors)
```

---

## ملاحظات أمنية مهمة

1. **لا تشارك أبداً** Personal Access Tokens أو مفاتيح API في الدردشة أو في الكود.
2. البوت العام يعني أن أي شخص يمكنه طلب توليد بوتات — العزل القوي (Docker + sandbox) هو خط الدفاع الأساسي.
3. يُفضّل دائماً تشغيل الخدمة على سيرفر يحتوي Docker لتفعيل العزل الكامل.
4. لا تمرّر مفاتيح AI الخاصة بك إلى الحاويات المولّدة (الكود يمنع ذلك تلقائياً).

---

## الهيكل

- `bot_interface/` — واجهة تيليجرام (أوامر + رسائل + صحة)
- `telegram_bot_engine/` — محرك التوليد والعزل
  - `spec_core/` — المسار الحتمي الحالي
  - `engines/generators/live_deployment/` — تشغيل معزول (Docker / Local)
  - `services/user_sandbox/` — مساحات الملفات لكل مستخدم
