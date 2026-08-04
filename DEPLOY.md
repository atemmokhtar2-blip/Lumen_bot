# نشر المشروع على Railway

## المتطلبات

1. حساب على [Railway](https://railway.app)
2. توكن بوت من [@BotFather](https://t.me/BotFather)

## خطوات النشر

### 1. ربط الريبو

- New Project → Deploy from GitHub
- اختر الريبو `ai_Agent_7h_bot` (أو ارفع الكود يدوياً)

### 2. المتغيرات (Variables)

في تبويب **Variables** أضف:

| الاسم | القيمة | مطلوب؟ |
|--------|--------|--------|
| `TELEGRAM_BOT_TOKEN` | التوكن من BotFather | ✅ نعم |
| `ALLOWED_USER_IDS` | أرقام المستخدمين مفصولة بفاصلة (اختياري) | لا |
| `OUTPUT_DIR` | `/tmp/generated` (افتراضي) | لا |

### 3. أمر التشغيل

المشروع جاهز بـ:

- `railway.toml` → `startCommand = "python main.py"`
- `Procfile` → `web: python main.py`
- `requirements.txt`

Railway سيكتشف Python تلقائياً عبر Nixpacks.

### 4. بعد النشر

1. افتح البوت على تليجرام
2. أرسل `/start`
3. أرسل وصفاً مثل: `اعمل بوت متجر إلكتروني`
4. البوت سيشغّل المحركات ويرد بالنتيجة + ملف zip إن وُجد

## ملاحظات مهمة

- **المحركات ما زالت قيد التطوير**: بعض المراحل قد تكون غير مكتملة. البوت يعمل مع الموجود حالياً.
- التخزين على Railway **مؤقت** (ephemeral). الملفات المولَّدة تُحذف عند إعادة التشغيل. لذلك البوت يرسل الـ zip مباشرة في الشات.
- إذا أردت Webhook بدلاً من Polling لاحقاً، يمكن إضافة `WEBHOOK_URL` وتعديل `main.py`.

## تشغيل محلي للتجربة

```bash
cp .env.example .env
# عدّل TELEGRAM_BOT_TOKEN في .env

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## الأوامر داخل البوت

| الأمر | الوظيفة |
|--------|---------|
| `/start` | ترحيب وشرح |
| `/help` | نفس الترحيب |
| `/status` | حالة المحركات |
| أي نص | طلب توليد بوت |
