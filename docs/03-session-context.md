# الجلسات وفقدان السياق (Lost Context)

## المشكلة

`context.user_data` في python-telegram-bot = **RAM للعملية**.  
Restart أو replica ثانية = فقدان المرحلة، المشروع النشط، وطلبات HITL.

## الحل: `lumen/bot/session_store.py`

لكل رسالة تقريبًا:

1. `hydrate(user_id, user_data)` — Redis يoverwrite المفاتيح الدائمة في الذاكرة
2. الـ handler يعدّل `user_data`
3. `persist` / `persist_ui_session` — إعادة كتابة المفاتيح الدائمة إلى Redis

مفتاح Redis: `lumen:tg:session:{user_id}`  
TTL افتراضي: **30 يومًا**  
مع اشتراك Pro في البيانات: TTL **45 يومًا** (هامش بعد انتهاء الشهر)

### Backend

- إنتاج: Redis (`REDIS_URL`)
- تطوير بدون Redis: `_MemoryBackend` فقط إذا `SESSION_ALLOW_MEMORY=1` وليس منصة نشر

## المفاتيح الدائمة (`_DURABLE_KEYS`)

- تدفقات معلّقة: `pending_run`, `pending_live_run`, `pending_deploy`, `pending_host`, `pending_clone_auth`, `pending_create_repo`, `pending_git_push`
- مشروع: `active_repo`, `last_project_path`, `active_bot_path`, `last_clone_url`, `repo_sections`
- حوار: `chat_history`, `last_bot_request`, `translated_preferred_keys`, `translated_source`, `force_generate_once`, `engine_ui_await_generate`
- **`engine_ui`** — آلة حالات الواجهة (كان إسقاطها سبب فقدان سياق كبير)
- لغة/ترحيب: `lang`, `lumen_welcome_shown`, `lumen_welcome_msg_id`
- multi-agent: `multi_agent_state_id`, `multi_agent_pending`
- **`pro_plan`** — نسخة كاش للاشتراك في الجلسة

أي مفتاح خارج القائمة يبقى RAM-only عمدًا.

## الأسرار في الجلسة

`_redact_secrets`: لا يُحفظ توكن بوت نصًا؛ أسرار أخرى تُحاول `seal_token` أو تُحذف.

## الاشتراك المدفوع ≠ الجلسة وحدها

`subscription_store.py`:

- **MongoDB** `users.metadata.pro_subscription` = مصدر الحقيقة الدائم (بدون TTL)
- Redis `pro_plan` داخل الجلسة = كاش سريع
- قراءة: Redis ثم Mongo مع إعادة ملء Redis (self-heal)
- الكتابة عند الدفع الناجح تكتب الاثنين

هذا يمنع فقدان Pro بعد flush Redis أو حذف البوت وإعادة الدخول.
