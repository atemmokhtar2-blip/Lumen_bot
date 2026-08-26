# Phase E — UX Console

> **Scope only:** Dashboard · Agents window · Pause / Steer / Cancel · Diff viewer · Live status (SSE).  
> No Phase F (MCP / Playwright / external integrations).

## Official tools

| Tool | Package / surface | Role |
|------|-------------------|------|
| Next.js 14 | `next` | App Router console |
| TanStack Query | `@tanstack/react-query` | Live server state |
| React Flow | `@xyflow/react` | Agent pipeline graph |
| Monaco | `@monaco-editor/react` | Code + side-by-side diff |
| SSE | `EventSource` + aiohttp | Live job stream |
| JobRunner | `lumen.platform.jobs` | pause · resume · cancel · **steer** |

## Control plane API

| Method | Path | Role |
|--------|------|------|
| GET | `/v1/jobs` | List |
| GET | `/v1/jobs/{id}` | Detail (+ `steer_notes`, `last_steer`) |
| GET | `/v1/jobs/{id}/events` | SSE (includes `last_steer`) |
| POST | `/v1/jobs/{id}/pause` | Cooperative pause |
| POST | `/v1/jobs/{id}/resume` | Resume |
| POST | `/v1/jobs/{id}/cancel` | Soft cancel |
| POST | `/v1/jobs/{id}/steer` | Body: `{"message":"..."}` — human intervention |
| GET | `/v1/jobs/{id}/files` | Generated tree |
| GET | `/v1/jobs/{id}/file?path=` | File content |
| GET | `/v1/runs/agent-reports` | multi_agent reports |

## Console routes

| Route | Role |
|-------|------|
| `/` | Dashboard stats |
| `/runs` | Job table + live counts |
| `/runs/[jobId]` | SSE timeline + Pause/Resume/Cancel/**Steer** |
| `/agents` | Agents window + React Flow graph |
| `/diff` | Monaco viewer / DiffEditor |

## Run

```bash
cd web && npm install
export NEXT_PUBLIC_LUMEN_API_URL=http://127.0.0.1:8080
export NEXT_PUBLIC_LUMEN_API_KEY=your_key
npm run dev
```

## Phase E checklist

- [x] Dashboard
- [x] Agents window + trajectory graph
- [x] Pause / Resume / Cancel
- [x] **Steer** (API + detail UI)
- [x] Diff viewer (Monaco)
- [x] Live status (SSE + TanStack Query)
