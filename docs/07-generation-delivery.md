# التوليد والتسليم

## المسار

1. اكتشاف طلب توليد من الرسالة/الـ UI
2. استخراج ميزات مبدئي (`engine_groq_bridge` + capability catalog)
3. تشغيل الوكيل / multi-agent على مجلد مشروع معزول
4. أحداث تقدم → تيليجرام
5. **Smoke test** قصير للمشروع (`generation_steps/helpers.py`)
6. عند النجاح: تعبئة ZIP وتسليم المستخدم
7. تحديث كاش التوليد + persist الجلسة

## الجسور

- `lumen/bot/generation_flow.py` — تنسيق التسليم من جهة البوت
- `lumen/bot/generation_steps/` — خطوات التسليم والتحقق
- `lumen/bot/multi_agent_bridge.py` — ربط HITL/نتائج الوكيل بالدردشة

## الإلغاء والطوابير

- إلغاء المستخدم يحترم marker عبر العمليات
- ضغط الطوابير / حدود الموارد عبر `resource_limits` وخدمات platform عند التفعيل
