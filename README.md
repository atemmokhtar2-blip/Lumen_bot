# AI Agent 7h Bot Engine 🤖

محرك توليد بوتات تيليجرام من وصف طبيعي عبر **AI فقط** (Execution Plan + Codegen).

> مسار Formal / DSL الحتمي **أُزيل نهائياً** من `generate_bot`.

---

## المسار النشط

```text
وصف المستخدم
  → Execution Planner (OpenAI / HF / Groq)
  → Plan-driven Codegen
  → ملفات المشروع
```

## المتطلبات

```bash
pip install -r requirements.txt
```

متغيرات البيئة (مزود واحد على الأقل):

```env
OPENAI_API_KEY=          # مفضّل للكود المعقد
HF_TOKEN=                # احتياطي
GROQ_API_KEY=            # اختياري
AI_PROVIDER_ORDER=openai,hf,groq
HF_DIRECT_CODEGEN=1
TELEGRAM_BOT_TOKEN=
```

## التشغيل

```bash
python main.py
```

أو برمجياً:

```python
from telegram_bot_engine import generate_bot
result = generate_bot("وصف البوت هنا...")
```
