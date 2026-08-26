# Phase E — UX Console (complete stack)

## الهدف

واجهة Power-User جاهزة للمنافسة: مراقبة agents، تحكم في jobs، diff احترافي، graph للـ pipeline.

## أدوات رسمية (إلزامي — ليست سكربتات)

| الأداة | الحزمة / المنتج | الدور |
|--------|------------------|--------|
| Next.js 14 | `next` | App Router UI |
| TanStack Query | `@tanstack/react-query` | server state · refetch · mutations |
| React Flow | `@xyflow/react` | رسم pipeline الـ agents |
| Monaco Editor | `@monaco-editor/react` | viewer + DiffEditor |
| SSE | `EventSource` + aiohttp | بث حي لتقدّم الـ job |
| JobRunner | `lumen.platform.jobs` | pause / resume / cancel |

## API

| Endpoint | الوظيفة |
|----------|---------|
| `GET /v1/jobs` | قائمة |
| `GET /v1/jobs/{id}` | تفصيل |
| `GET /v1/jobs/{id}/events` | SSE |
| `POST /v1/jobs/{id}/cancel` | إلغاء |
| `POST /v1/jobs/{id}/pause` | إيقاف مؤقت |
| `POST /v1/jobs/{id}/resume` | استئناف |
| `GET /v1/jobs/{id}/files` | شجرة ملفات |
| `GET /v1/jobs/{id}/file?path=` | محتوى ملف |
| `GET /v1/runs/agent-reports` | تقارير multi_agent |

## صفحات

| Route | الوظيفة |
|-------|---------|
| `/` | لوحة إحصائيات (TanStack Query) |
| `/runs` | جدول + mutations + عدّادات |
| `/runs/[jobId]` | SSE timeline + تحكم |
| `/agents` | React Flow graph + قائمة التقارير |
| `/diff` | Monaco viewer / side-by-side |

## تشغيل

```bash
cd web
npm install
export NEXT_PUBLIC_LUMEN_API_URL=http://127.0.0.1:8080
export NEXT_PUBLIC_LUMEN_API_KEY=your_key
npm run dev
```

## اكتمال Phase E

- [x] Live job list + detail SSE
- [x] Pause / Resume / Cancel (JobRunner)
- [x] Agents window + trajectory graph (React Flow)
- [x] Monaco code + diff
- [x] TanStack Query data layer
- [x] توثيق محدث

الخطوة التالية المقترحة (خارج E): Temporal Web UI signals، أو Phase F (MCP / Playwright).
