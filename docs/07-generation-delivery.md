# التوليد والتسليم

## من الرسالة إلى المشروع

1. نية توليد (`message_intent`) أو تأكيد بعد `last_bot_request` / Engine UI `GEN_CONFIRM`
2. استخراج ميزات: قواعد عربية/إنجليزية + catalog القدرات (`capability_detection`)
3. بناء مواصفات / IR
4. تشغيل:
   - **Orchestrator** multi-agent إن مفعّل
   - أو **provider_agent / agent_loop** مباشرة
5. تحديثات حية على رسالة الحالة
6. **Acceptance** على ملفات المشروع
7. **Smoke test** (`generation_steps/helpers._smoke_test_project`) — تشغيل قصير (افتراضي ~10s)
8. عند النجاح: تعبئة ZIP وتسليم عبر `generation_steps/delivery.py`
9. فشل QA → repair أو رسالة خطأ منقّاة من الأسرار

## ملفات البوت ذات الصلة

- `generation_flow.py` — واجهة تدفق التسليم
- `generation_steps/` — delivery، helpers، مراحل
- `generation_cache.py` — كاش نتائج عند التفعيل
- `multi_agent_bridge.py` — ربط نتائج/HITL بالدردشة

## ما لا يحدث

- لا استدعاء `translate_request`/`chat_request` لتوليد الملفات
- لا تسليم ZIP إن فشل smoke/acceptance حسب سياسة المسار
