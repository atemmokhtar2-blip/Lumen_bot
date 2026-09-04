# الجلسات وفقدان السياق

## المشكلة التي يحلّها النظام

`context.user_data` في PTB **ذاكرة عملية فقط**. إعادة التشغيل أو أكثر من replica يمحوان السياق.

## الحل: `lumen/bot/session_store.py`

- **المصدر الحقيقي:** Redis (`REDIS_URL` / مفاتيح الجلسة).
- كل طلب:
  1. hydrate المفاتيح الدائمة من Redis → `user_data`
  2. يعدّل الـ handler الـ `user_data`
  3. يpersist المفاتيح الدائمة إلى Redis

SQLite على القرص أُزيل (غير مناسب لـ Railway/ephemeral وتعدد الـ replicas).

## مفاتيح دائمة (أمثلة من الكود)

- تدفقات: `pending_run`, `pending_deploy`, `pending_host`, …
- مشروع: `active_repo`, `last_project_path`, `active_bot_path`, …
- حوار: `chat_history`, `last_bot_request`, `engine_ui`, …
- multi-agent: `multi_agent_state_id`, `multi_agent_pending`, …
- تفضيلات: `lang`, ترحيب Lumen

أي مفتاح خارج القائمة يبقى RAM-only عمدًا.

## التطوير بدون Redis

- فقط مع `SESSION_ALLOW_MEMORY=1` وخارج منصات النشر.
- الإنتاج: Redis إلزامي عمليًا (جلسات + rate limit + jobs).

## الاشتراك Pro

سجل Pro يُقرأ من `subscription_store` (Redis ثم Mongo كاحتياطي) — لا يُوثق من `user_data` وحده كمصدر حقيقة للحدود.
