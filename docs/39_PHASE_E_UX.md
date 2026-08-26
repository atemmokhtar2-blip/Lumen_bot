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
