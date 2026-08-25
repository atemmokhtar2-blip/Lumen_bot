# نقاط التشغيل (Entry Points)

## 1) بوت التيليجرام — `main.py`

```bash
pip install -r requirements.txt
cp .env.example .env   # TELEGRAM_BOT_TOKEN=...
python main.py
```

**ماذا يشغّل؟**
- Polling لتيليجرام عبر `python-telegram-bot`
- أوامر: `/start` `/help` `/status` `/lang`
- كل رسالة نصية → `lumen.bot.handle_message` → `routers/message_router.py`
- Health HTTP خفيف على `PORT` (إن وُجد)
- اختياري: مع `ENABLE_API=1` يشغّل B2B API في process/thread منفصل

**متغيرات حرجة:**
- `TELEGRAM_BOT_TOKEN`
- `ALLOWED_USER_IDS` أو وضع عام (`ALLOW_ALL_USERS`)
- `OUTPUT_DIR` — مخرجات التوليد والنسخ المحلية للمستودعات

## 2) API فقط — `api_main.py`

```bash
python api_main.py
```

يدخل `api.app.run_api` — سطح B2B بدون بوت تيليجرام.

تفاصيل المسارات: [11_B2B_API.md](11_B2B_API.md)

## 3) الحزمة `lumen.bot`

واجهة التيليجرام فقط. الاستيراد الثقيل lazy حتى تختبر وحدات بدون `telegram`.

| ملف | وظيفة |
|-----|--------|
| `config.py` | توكن، مستخدمين مسموح، مسارات، logger |
| `commands.py` | أوامر + رسائل غير نصية |
| `routers/message_router.py` | **قلب التوجيه** لكل رسالة |
| `routers/git_router.py` | سحب/دفع git من واجهة الشات |
| `routers/hosting_router.py` | أوامر استضافة |
| `generation_flow.py` | مسار التوليد من الواجهة |
| `session_store.py` | حفظ جلسة المستخدم (`active_repo`, …) |
| `handlers/token_handler.py` | استقبال توكن BotFather للتشغيل الحي |

## 4) الحزمة `lumen.engine`

المحرك الحقيقي: لا UI. يُستدعى من الواجهة أو الـ API.

لا تشغّله مباشرة كسيرفر؛ استورد خدماته:

```python
from lumen.engine.services.tool_runtime import execute_tool
from lumen.engine.spec_core.pipeline import build_from_spec
```

## ترتيب القراءة للمطوّر الجديد

1. هذا الملف
2. [03_MESSAGE_FLOW.md](03_MESSAGE_FLOW.md)
3. [04_CHAT_AND_GROK.md](04_CHAT_AND_GROK.md)
4. [06_SPEC_CORE.md](06_SPEC_CORE.md)
