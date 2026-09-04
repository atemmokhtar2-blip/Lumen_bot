# طبقة تيليجرام

## المكوّنات

| مسار | وظيفة |
|------|--------|
| `lumen/bot/routers/` | توجيه الرسائل، التوليد، التوكن، git، hosting |
| `lumen/bot/ui/` | لوحات، دفع Stars، Pro، callbacks |
| `lumen/bot/session_store.py` | جلسات دائمة |
| `lumen/bot/sanitize.py` | تنقية أسرار من النصوص |
| `lumen/bot/telegram_text.py` / `rich_messages.py` | تنسيق وإرسال |
| `lumen/bot/progress_tracker.py` | ربط تقدم التوليد برسائل البوت |
| `lumen/bot/ptb_redis_persistence.py` | persistence لـ python-telegram-bot عبر Redis |

## تدفق الرسالة (من الكود)

ترتيب عام في مسار الرسائل:

1. Allowlist (`ALLOW_ALL_USERS` / قوائم)
2. مستخدم Mongo + الخطة
3. Rate limit
4. المجموعات: منشن أو رد على البوت
5. حد طول النص
6. HITL multi-agent إن وُجد
7. أوامر `/plan` وcapability ops
8. **hydrate** من `session_store` (Redis)
9. لصق توكن بوت
10. مؤشر «جاري العمل» / thinking
11. مسار توليد أو أدوات repo/hosting

## Markdown

- تنظيف قبل الإرسال لتقليل أخطاء Telegram parse.
- نصوص طويلة تُقسَّم حسب حدود تيليجرام (4096).
- الأسرار تُمرَّر عبر `sanitize` قبل عرض الأخطاء.

## التنقّل والـ UI

- لوحات في `ui/keyboards.py` و`callback_router.py`.
- خطط Pro: `view_pro_plan` / `buy_pro_plan` → `payment_handlers.py`.
- بعد الدفع: تفعيل entitlement وفتح حدود الاستضافة — `pro_plan_entitlement.py`.

## إلغاء التوليد

- طلب إلغاء يُكتب كـ marker؛ الحلقة تتحقق `is_cancelled` عبر العمليات.
- لا تُمسح علامة الإلغاء عند بداية الحلقة بشكل يتجاهل طلب المستخدم.

## التقدّم الحي (Dead Wait)

- `progress_bus` يستقبل أحداثًا من العامل (provider/model، أدوات، خطوات).
- الواجهة تعدّل رسالة الحالة دوريًا حتى لا يبقى المستخدم أمام انتظار ميت.
