# Lumen

منصة توليد واستضافة بوتات تيليجرام + B2B API.

التوثيق مبني على الكود الحالي فقط (ليس على وثائق قديمة).

## تشغيل سريع

```bash
pip install -r requirements.txt
cp .env.example .env   # TELEGRAM_BOT_TOKEN=...
python main.py         # بوت التيليجرام (افتراضي: API مغلق)
# أو API فقط:
python api_main.py
```

تفعيل API مع البوت: `ENABLE_API=1`.

## ما ينفّذ التوليد فعليًا؟

| الطبقة | الدور في الكود |
|--------|----------------|
| `message_router` | توجيه رسالة تيليجرام، بوابات، force-generate |
| Chat (Gemini / translator) | فهم نية وترجمة مواصفات — **لا يكتب كود مشروع** |
| `BuildIR` + `engine_router` | عقد التوليد؛ يفرض مسار **Cline فقط** |
| `cline_runtime` (agent) | محرك التوليد الوحيد: حلقة plan → tool → observe |
| `tool_runtime` | تنفيذ أدوات: clone / host / repo_* / … |
| ~~`spec_core`~~ | **محذوف نهائيًا** — لا يوجد مسار توليد حتمي/قوالب |

## أسطح المنتج

- **Consumer Bot** — `python main.py`
- **B2B API** — `ENABLE_API=1` أو `python api_main.py`
- **Web control plane** — مجلد `web/` (Next.js UX للـ jobs)

## التوثيق

| الملف | المحتوى |
|-------|---------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | الحزم والتدفقات من الكود |
| [docs/MESSAGE_FLOW.md](docs/MESSAGE_FLOW.md) | مسار رسالة تيليجرام |
| [docs/GENERATION.md](docs/GENERATION.md) | IR → Cline agent |
| [docs/API.md](docs/API.md) | مسارات B2B |
| [docs/CONFIG.md](docs/CONFIG.md) | متغيرات بيئة أساسية |
| [SECURITY.md](SECURITY.md) | سياسة الإبلاغ عن الثغرات |

## هيكل الحزم

```
main.py / api_main.py
lumen/
  bot/          # واجهة تيليجرام فقط
  engine/       # IR، Cline، tools، خدمات
  api/          # aiohttp B2B
  platform/     # خطط، credits، jobs، rate limit
```
