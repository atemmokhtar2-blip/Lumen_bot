# التشغيل الحي والتوكن وواجهة مختصرة

## تدفق التوكن

```
توليد ناجح → pending_* في context + session_store
     ↓
المستخدم يلصق توكن BotFather
     ↓
message_router: looks_like_bot_token → try_handle_token (بدون thinking)
     ↓
pending_run.project_path؟ نعم → live_runner
لا → استرجاع آخر main.py تحت sandbox المستخدم
لا يوجد مشروع → رسالة توضيح (لا يُعامل التوكن كوصف بوت)
```

## متغيرات

| المتغير | المعنى |
|---------|--------|
| `QUIET_DELIVERY` | `1` = ملخص قصير للتوليد (افتراضي) |
| `LIVE_RUN_SECONDS` | مدة التشغيل الحي |
| `MONGODB_URI` | إلزامي لهوية المستخدم |
| `OUTPUT_DIR` | جذر مشاريع المستخدمين |

## صيانة

- فشل «مايسترو يفكر» بعد التوكن: تأكد أن `session_store` يُحمَّل قبل `try_handle_token`.
- فشل التثبيت: راجع logs `live_runner` ومتطلبات `requirements.txt` في المشروع المولَّد.
- رسائل طويلة قديمة: اضبط `QUIET_DELIVERY=1` وأعد تشغيل العملية.
