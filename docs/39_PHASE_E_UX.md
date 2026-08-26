# Phase E — UX Console (deepened)

## الهدف

واجهة Power-User عالمية المستوى لمراقبة وتشغيل الـ agents — ليست شاشة تجريبية.

## المكوّنات

| سطح | تنفيذ رسمي |
|------|------------|
| API SSE | `GET /v1/jobs/{id}/events` (aiohttp StreamResponse, timeout افتراضي 600s) |
| Cancel | `POST /v1/jobs/{id}/cancel` + `JobRunner.cancel` |
| Pause | `POST /v1/jobs/{id}/pause` + `JobRunner.pause` (cooperative) |
| Resume | `POST /v1/jobs/{id}/resume` + `JobRunner.resume` |
| Files | `GET /v1/jobs/{id}/files` · `GET /v1/jobs/{id}/file?path=` |
| Agent reports | `GET /v1/runs/agent-reports` |
| Console | Next.js 14 App Router + **Monaco Editor** (`@monaco-editor/react`) |

## صفحات الـ Console

| Route | الوظيفة |
|-------|---------|
| `/` | لوحة دخول + خريطة القدرات |
| `/runs` | جدول jobs حي · Pause / Resume / Cancel · رابط التفصيل |
| `/runs/[jobId]` | تفصيل job + **Live SSE timeline** + تحكم |
| `/agents` | نافذة Agents · trajectory قابل للطي |
| `/diff` | شجرة ملفات + **Monaco Viewer** + **side-by-side DiffEditor** |

## تشغيل

```bash
# API
python api_main.py

# Console
cd web
npm install
export NEXT_PUBLIC_LUMEN_API_URL=http://127.0.0.1:8080
export NEXT_PUBLIC_LUMEN_API_KEY=your_key
npm run dev
```

## أدوات رسمية مستخدمة

- **Next.js 14** (App Router)
- **React 18**
- **Monaco Editor** عبر `@monaco-editor/react` (محرك VS Code)
- **Server-Sent Events** أصلية (`EventSource`) + aiohttp stream
- **JobRunner** في `lumen.platform.jobs` — لا سكربتات وهمية

## حالات Job

`queued` · `running` · `paused` · `succeeded` · `failed` · `cancelled`

`paused` غير terminal؛ Resume يعيد `running` أو `queued` حسب `started_at`.

## ملاحظات

- Pause تعاوني (مثل soft-cancel): يحدّث الحالة في المتجر.
- SSE يمرّر `api_key` في query لأن EventSource لا يدعم headers مخصصة.
- مسار التوليد: Cline + multi_agent — ليس catalog.
