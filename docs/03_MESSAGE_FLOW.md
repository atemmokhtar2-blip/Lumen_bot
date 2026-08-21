# تدفق الرسالة (message_router)

الملف المركزي: `bot_interface/routers/message_router.py`  
الدالة: `async def handle_message(update, context)`

## ترتيب المعالجة (مهم جداً)

الترتيب هنا يحدد ليه رسالة تروح توليد ولا فهم مستودع ولا شات.

```
1. مؤشر "بيفكر…"
2. صلاحية المستخدم + rate limit + قواعد الجروبات
3. HITL multi-agent (تأكيد/رفض)
4. أوامر خطة /plan
5. توكن بوت تيليجرام (قبل أي مسار Gemini)  ← token_handler
6. كشف طلب توليد صريح → last_bot_request + force_generate_once (أفعال: عايز بوت…)
7. تأكيدات قصيرة (ابدأ / أنجز) → generate-now
8. مسار force_generate_once → ترجمة → توليد فوري ثم return
9. EARLY active_repo bind
     - لو في مستودع نشط + الرسالة مش توليد/مواصفات بوت
     - → execute_tool(repo_understand) ثم return
10. شات LLM (Gemini/Groq حسب الإعداد) لفهم النية
11. خط أنابيب الفهم:
      Gemini understanding → Translator → spec_request
12. توليد عبر generation_flow / spec_core إن اكتملت المواصفات
13. Phase 4: chat_router + ربط active_repo للأسئلة الحرة
14. أدوات صلبة (engine-only): repo_understand, static_analysis, …
15. مساعدة افتراضية إن مفيش مسار واضح
```

## قواعد التوجيه الحرجة

| نوع الرسالة | يجب أن تروح لـ |
|-------------|----------------|
| `عايز بوت جروب…` / `اعمل بوت…` | توليد (force أو Gemini→translate→engine) |
| `بوت متجر إلكتروني لعرض المنتجات…` (مواصفات بدون فعل) | **Gemini → Translator → Engine** — **ممنوع** EARLY repo bind |
| رابط GitHub / `اسحب` | `git_router` / `clone_repo` |
| `كم سطر` / `هات main.py` ومعاك active_repo | أدوات المستودع (`repo_understand` + repo_tools) |
| توكن `123456:AA…` | `token_handler` للتشغيل الحي |

## دوال الكشف

- `_looks_like_generation_request` — أفعال صريحة مع كلمة بوت (يشغّل force_generate)
- `_looks_like_bot_spec` في `chat_router/service.py` — وصف بوت (يبدأ بـ «بوت …») بدون ما يتخطف للمستودع
- `looks_like_bot_token` — توكن BotFather

## `active_repo` في الجلسة

بعد clone ناجح، `user_data["active_repo"]` يحتوي تقريباً:

```python
{
  "path": "/tmp/.../clones/...",
  "url": "https://github.com/...",
  "dossier": {...},   # قياسات للمحادثة
  "facts": {...},
  "contract": {...},  # فهم المستودع
  "bound_for_grok": True,
}
```

**يجب عدم مسح dossier عند تحديث contract** — الدمج وليس الاستبدال.

## ماذا لا تفعله هنا؟

- لا تنفّذ git بنفسك في الراوتر — استدعِ `execute_tool` أو `git_router`
- لا تولّد ملفات بوت من الشات مباشرة — `spec_core` فقط
- لا تربط وصف بوت جديد على `repo_understand` لمجرد وجود مستودع قديم
