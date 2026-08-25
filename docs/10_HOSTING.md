# الاستضافة (Hosting)

## الدور

تشغيل بوت مولَّد أو مشروع كعملية طويلة الأمد: start / stop / status / diagnose.

الحزمة: `lumen.engine/services/hosting/`

| ملف | دور |
|-----|-----|
| `service.py` | `HostingService` — الواجهة الرئيسية |
| `worker.py` | عمال التشغيل |
| `fleet.py` / `capacity.py` | سعة الأسطول |
| `deploy_queue.py` | طابور النشر |
| `network.py` | شبكة |
| `pg_*` | حالة/طابور Postgres عند التفعيل |
| `market_gate.py` | بوابة سوق/خطة |

## من التيليجرام

- `routers/hosting_router.py`
- أدوات: `host_start`, `host_stop`, `host_status`, `host_diagnose`
- بعد توليد بوت runnable: طلب توكن BotFather → `token_handler` → تشغيل حي

## من الـ API

```
POST /v1/hosts/start   { "project_path", "bot_token" }
POST /v1/hosts/stop
GET  /v1/hosts
POST /v1/hosts/diagnose
```

## الحدود

`boundaries/hosting_boundary.py` تفصل **Hosting** عن **Workspace** و **Git**.

التشغيل يفضّل عزل Docker وحدود CPU/RAM عند التوفر — انظر سياسات العزل و`isolation_policy`.
