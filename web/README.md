# Lumen Web Console (Phase E — deepened)

Next.js 14 + Monaco Editor console for runs, agents, live SSE, pause/resume/cancel, and side-by-side diff.

## Setup

```bash
cd web
npm install
export NEXT_PUBLIC_LUMEN_API_URL=http://127.0.0.1:8080
export NEXT_PUBLIC_LUMEN_API_KEY=your_key
npm run dev
```

## Official stack

| Package | Role |
|---------|------|
| `next` | App Router UI |
| `react` / `react-dom` | UI runtime |
| `@monaco-editor/react` | Code viewer + DiffEditor (VS Code engine) |
| Browser `EventSource` | SSE to `/v1/jobs/{id}/events` |

## API used

- `GET /v1/jobs` — list
- `GET /v1/jobs/{id}` — detail
- `GET /v1/jobs/{id}/events` — SSE
- `POST /v1/jobs/{id}/cancel` — cancel
- `POST /v1/jobs/{id}/pause` — pause
- `POST /v1/jobs/{id}/resume` — resume
- `GET /v1/jobs/{id}/files` — file tree
- `GET /v1/jobs/{id}/file?path=` — file content
- `GET /v1/runs/agent-reports` — multi-agent trajectory

## Routes

- `/runs` — job table + controls
- `/runs/[jobId]` — live timeline
- `/agents` — agent reports window
- `/diff` — Monaco viewer / side-by-side diff
