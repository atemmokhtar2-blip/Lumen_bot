# Lumen Web Console (Phase E)

Next.js 14 App Router console for runs / agents / SSE / cancel.

```bash
cd web
npm install
export NEXT_PUBLIC_LUMEN_API_URL=http://127.0.0.1:8080
export NEXT_PUBLIC_LUMEN_API_KEY=your_key
npm run dev
```

API:

- `GET /v1/jobs` — list
- `GET /v1/jobs/{id}/events` — SSE
- `POST /v1/jobs/{id}/cancel` — cancel
