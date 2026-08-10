# AI Agent 7h Bot

بوت تيليجرام عام يولّد مشاريع بوتات تيليجرام من وصف نصي.

## الوضع الحالي (نهائي)

| البند | الحالة |
|--------|--------|
| مسار التوليد | **حتمي فقط (zero-AI)** عبر `spec_core` |
| مسار الذكاء الاصطناعي | **محذوف نهائياً** (لا OpenAI / Groq / HF / planner / codegen بالـ LLM) |
| الوصول | **عام** لجميع مستخدمي تيليجرام افتراضياً |
| التحقق بعد التوليد | بوابة **anti-hallucination** إلزامية |
| تشغيل البوتات المولّدة | عزل قوي (Docker مفضّل + sandbox لكل مستخدم) |

## كيف يعمل التوليد

```text
وصف المستخدم
  → اختيار preset / تكوين المواصفات (spec_core)
  → كتابة ملفات المشروع (محركات حتمية)
  → بوابة ضد الهلوسة (syntax + handlers حقيقية + أوامر مؤكدة)
  → تسليم للمستخدم فقط إذا نجح التحقق
```

لا يُعلن عن ميزة أو أمر إلا بعد التحقق من وجود كود حقيقي (وليس stub).

## التشغيل

```bash
pip install -r requirements.txt
cp .env.example .env   # ثم ضع TELEGRAM_BOT_TOKEN
python main.py
```

أو برمجياً:

```python
from telegram_bot_engine import generate_bot

result = generate_bot("بوت فيه /start ويرد على الرسائل")
print(result.success, result.project_path, result.metadata)
```

## متغيرات البيئة

| المتغير | الوصف |
|---------|--------|
| `TELEGRAM_BOT_TOKEN` | توكن البوت الأساسي (إلزامي) |
| `ALLOWED_USER_IDS` | قائمة معرفات (اختياري؛ فارغ = عام) |
| `LOCK_BOT_TO_ALLOWLIST` | `1` لقفل البوت على القائمة فقط |
| `RATE_LIMIT_PER_MINUTE` | حد الرسائل لكل مستخدم (افتراضي 12) |
| `MAX_PROJECTS_PER_USER` | حد المشاريع لكل مستخدم (افتراضي 50) |
| `OUTPUT_DIR` | مجلد المشاريع (افتراضي `/tmp/generated`) |
| `TBE_PREFER_DOCKER` | تفضيل Docker للعزل (افتراضي مفعّل) |
| `TBE_DOCKER_MEMORY` / `CPUS` / `PIDS` | حدود موارد الحاوية |

انظر `.env.example` للتفاصيل.

## هيكل المشروع

```text
main.py                 نقطة تشغيل واجهة تيليجرام
bot_interface/          أوامر، رسائل، إعدادات، صحة
telegram_bot_engine/
  spec_core/            مسار التوليد الحتمي
  services/
    anti_hallucination/ بوابة منع الهلوسة
    user_sandbox/       مجلدات معزولة لكل مستخدم
    live_runner/        تشغيل/تشخيص البوتات المولّدة
  engines/generators/
    live_deployment/    Docker / local isolation
requirements.txt
.env.example
```

## العزل

1. **ملفات:** كل مستخدم تحت  
   `OUTPUT_DIR/users/<shard>/<telegram_id>/projects|clones|runtime`
2. **تشغيل (Docker):** حاوية منفصلة، `cap-drop ALL`، read-only، حدود memory/CPU/pids، توكن البوت المولَّد فقط (بدون توكن المضيف).
3. **Fallback محلي:** حدود `resource` + بيئة نظيفة عبر `clean_child_env`.

## ملاحظات

- لا يوجد مسار LLM لتوليد الكود أو لردود الشريك الذكي.
- فشل بوابة anti-hallucination → المشروع **غير جاهز** ولن يُطلب توكن التشغيل.
- هذا هو ملف التوثيق الوحيد في المستودع.

## Capability scale (registry)

- حوالي **30,270** capability key حتمية في `spec_core.registry`
- كل مفتاح يمر على مسار تنفيذي (`service.method` → SQLite durable)
- Domain handlers متخصصة لأعلى الخدمات حجماً + مسار عام مُحسَّن
- اختبارات: `tests/test_capabilities_scale.py`
  - exhaustive لكل المفاتيح
  - load متزامن (آلاف العمليات/ثانية)
  - سيناريوهات واقعية متعددة الخطوات

