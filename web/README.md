# Lumen Web Console — Phase E

## Official dependencies

```text
next
react / react-dom
@tanstack/react-query   # server state
@xyflow/react           # React Flow agent graphs
@monaco-editor/react    # VS Code editor + diff
monaco-editor
```

## Setup

```bash
npm install
export NEXT_PUBLIC_LUMEN_API_URL=http://127.0.0.1:8080
export NEXT_PUBLIC_LUMEN_API_KEY=your_key
npm run dev
```

## Routes

- `/` — live stats (TanStack Query)
- `/runs` — jobs + pause/resume/cancel
- `/runs/[jobId]` — SSE timeline
- `/agents` — React Flow pipeline + reports
- `/diff` — Monaco viewer / DiffEditor
