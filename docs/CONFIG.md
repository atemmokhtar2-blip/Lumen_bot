# Config (from code)

Primary bot config: `lumen/bot/config.py` (+ `.env` / `.env.example`).

## Required / common

| Variable | Role |
|----------|------|
| `TELEGRAM_BOT_TOKEN` | Required for `main.py` |
| `OUTPUT_DIR` | Writable root for sandboxes / artifacts |
| `PORT` | Health or API bind (default 8080) |
| `ENABLE_API` | `1` to start B2B with the bot process |
| `API_PROCESS_MODE` | `process` (default) or `thread` / `runner` |
| `ALLOWED_USER_IDS` | Comma-separated Telegram ids |
| `ALLOW_ALL_USERS` / `LOCK_BOT_TO_ALLOWLIST` | Access policy |
| `RATE_LIMIT_PER_MINUTE` | Bot text rate limit |
| `CLINE_ENABLED` | Default on; `0` kills generation engine |
| `CLINE_MODE` | `agent` (default) or `builtin` |
| `CLINE_AGENT_MAX_STEPS` | Agent loop bound |
| `CLINE_ALLOW_SHELL` | Required if IR gaps mention shell |
| `GROQ_CODEGEN_ENABLED` | Manual alternate codegen path |
| `MULTI_AGENT_ORCHESTRATOR` | Multi-agent path before Cline |
| `SENTRY_DSN` / `OTEL_SERVICE_NAME` | Observability |
| `API_CORS_ORIGIN` | Exact origin allowlist for API |
| `ENVIRONMENT` | Affects fail-closed behavior |

Copy `.env.example` for the full operator surface; treat secrets as production credentials only.
