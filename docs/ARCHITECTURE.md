# Architecture (from code)

Last aligned with tree under `lumen/` on branch `Lumen`.

## Packages

| Package | Responsibility |
|---------|----------------|
| `lumen/bot/` | Telegram only: handlers, routers, session, delivery, limits |
| `lumen/engine/` | Generation IR, Cline runtime, tool_runtime, services |
| `lumen/api/` | aiohttp B2B surface |
| `lumen/platform/` | tenants, plans, credits, jobs, rate limit, observability |

## Entry points

- `main.py` — Telegram polling (singleton lock). Optionally starts B2B API process/thread if `ENABLE_API=1`.
- `api_main.py` — API-only (`lumen.api.app.run_api`).

## Generation policy (hard-coded)

`lumen/engine/services/engine_router.py`:

- `decide_engine_mode` always returns `EngineMode.CLINE`.
- Non-Cline `engine_mode` values in packages are logged and ignored.
- `execute_ir` always calls `execute_cline_ir`.

`EngineMode` enum still lists `catalog`, `hybrid`, `cline`, `infinite` for legacy IR shapes; product path is Cline-only.

## `spec_core` — removed permanently

The entire `lumen/engine/spec_core` package has been **deleted**.

- Generation is **Cline-only** (`engine_router` → `execute_cline_ir`).
- Capability detection uses an empty local catalog: `lumen/engine/services/capability_detection/catalog.py`.
- Language-understanding / template-builder paths that depended on `spec_core` fail soft (try/except) and are no longer product paths.

## Cline path

```
BuildIR
  → validate_and_normalize_ir
  → execute_cline_ir
       → policy (CLINE_ENABLED, shell gaps)
       → optional CLINE_PROVIDER
       → CLINE_MODE=agent (default): provider_agent → agent_loop
            plan → tool (agent_fs) → observe → until finish / max steps
       → or builtin catalog compose if CLINE_MODE=builtin
```



## Message ownership (engine turn)

Telegram NL messages are owned by ``lumen.engine.services.multi_agent.engine_turn.handle_user_turn``:

1. ``RouterAgent`` selects capability/tool (via ``chat_router`` phrase routing — not a chat LLM).
2. Tools run through ``execute_tool_gated`` → ``tool_runtime``.
3. ``generate_bot`` / ``refine_bot`` signal the multi-agent / Cline generation pipeline.
4. Active repo + soft intent → ``repo_understand`` (agents measure the project).

There is **no** standalone conversational chat layer on the bot path.

## Tools

`lumen/engine/services/tool_runtime`: capability router (`chat_router`) selects; engines **execute**. Standalone conversational chat layer removed — multi-agent/Cline owns generation and tool outcomes.

Catalog includes: `clone_repo`, `create_repo`, `git_push`, `git_pull`, `repo_inspect`, `repo_understand`, `repo_modify`, `generate_bot`, `refine_bot`, `host_*`.

Risk tiers drive HITL confirmation for high/critical actions.

## Platform

- Plans + `plan_gate` filter features post-generation.
- Credits ledger, metering, rating, balance lifecycle under `lumen/platform/`.
- Per-user sandbox under `OUTPUT_DIR` via `user_sandbox`.
- Job queue + backpressure for heavy work (especially API generate).

## Hosting (two planes)

| Plane | Code | Role |
|-------|------|------|
| **TRIAL_CHAT** | `lumen/engine/services/live_runner/` | Short-lived preview only |
| **PERMANENT_HOST** | `lumen/engine/services/hosting/` | Long-running commercial host (Firecracker in production) |

Production isolation is fail-closed: multi-tenant / non-dev → Firecracker only (`isolation_policy`, `sandbox_runtime.select`, `hosting.market_gate`).

Full field contract, ordered start gates, and market-gate checklist: [HOSTING_CONTRACT.md](HOSTING_CONTRACT.md).


## Platform extensions (post Phase E)

| Module | Role |
|--------|------|
| `services/browser_use` | Playwright Chromium computer-use |
| `services/skills` | Skill registry + MCP HTTP JSON-RPC client |
| `services/events` | Redis/in-process event bus |
| `services/integrations/github` | GitHub REST Issues/PRs |
| `multi_agent/swarm` | Parallel worker partitions |
