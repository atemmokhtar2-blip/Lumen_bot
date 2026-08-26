# Phase E — UX Console

## بعد بوابة D

D: bot-bench + cost + live_bridge + baseline (عقود متعددة المنصات).  
**ليس** تقييم LLM-SOTA عالمي مغلق — لكنه كافٍ للانتقال مع القياس.

## E مكوّنات

| سطح | تنفيذ |
|------|--------|
| API SSE | `GET /v1/jobs/{id}/events` (aiohttp StreamResponse) |
| Cancel | `POST /v1/jobs/{id}/cancel` + `JobRunner.cancel` |
| Console | `web/` Next.js 14 — Runs / Agents |

```bash
cd web && npm install && npm run dev
```


## API (Phase E)

| Endpoint | Role |
|----------|------|
| `GET /v1/jobs` | list runs |
| `GET /v1/jobs/{id}/events?api_key=` | SSE (EventSource) |
| `POST /v1/jobs/{id}/cancel` | cancel |
| `GET /v1/jobs/{id}/files` | generated file tree |
| `GET /v1/jobs/{id}/file?path=` | file content for diff |
| `GET /v1/runs/agent-reports` | multi-agent trajectory reports |

Console pages: `/runs`, `/agents`, `/diff?job=…`
