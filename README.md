# Maestro — capability_maestro_bot

منصة توليد واستضافة بوتات تيليجرام + B2B API.

**التوثيق الكامل:** ابدأ من [`docs/MASTER.md`](docs/MASTER.md)

## تشغيل سريع

```bash
pip install -r requirements.txt
cp .env.example .env   # TELEGRAM_BOT_TOKEN=...
python main.py         # بوت التيليجرام
# أو API فقط:
python api_main.py
```

## مبادئ سريعة

| الطبقة | الدور |
|--------|------|
| شات (افتراضي Groq) | توجيه نية فقط — لا تنفيذ |
| ترجمة (افتراضي Gemini) | عقد `spec_core` |
| `spec_core` | توليد حتمي بدون هلوسة كود من النموذج |
| `tool_runtime` | تنفيذ clone / host / repo / generate |
| `active_repo` | مستودع مسحوب للأسئلة والقياس |

## فهرس التوثيق

| الملف | الموضوع |
|-------|---------|
| [docs/MASTER.md](docs/MASTER.md) | الخريطة الكاملة |
| [docs/00_ARCHITECTURE.md](docs/00_ARCHITECTURE.md) | البنية |
| [docs/03_MESSAGE_FLOW.md](docs/03_MESSAGE_FLOW.md) | تدفق الرسالة |
| [docs/04_CHAT_AND_GROK.md](docs/04_CHAT_AND_GROK.md) | الشات وحدود Grok |
| [docs/06_SPEC_CORE.md](docs/06_SPEC_CORE.md) | محرك التوليد |
| [docs/08_REPO_AND_GIT.md](docs/08_REPO_AND_GIT.md) | المستودعات |
| [docs/11_B2B_API.md](docs/11_B2B_API.md) | REST API |
| [docs/13_CONFIG_ENV.md](docs/13_CONFIG_ENV.md) | متغيرات البيئة |

## أسطح المنتج

- **Consumer Bot** — `python main.py`
- **B2B API** — `ENABLE_API=1` أو `python api_main.py`
- **Managed Hosting** — أدوات host_* + `/v1/hosts/*`
- **White-label** — خطط Business+ عبر API
