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

## `spec_core` status

Package still exists under `lumen/engine/spec_core/`.

Its own `__init__.py` states: generation is performed exclusively by the Cline SDK path; this package keeps modules used by IR validation, capability detection, chat UX, and delivery personalization.

`builder.py` is a re-export stub; old Spec Builder / BuilderSession is removed.

Live uses include: `registry.CAPABILITIES`, `command_map`, `domain_detector`, `lean_packs`, `language_understanding/*` (imported from IR validate, capability_detection, message_router, etc.).

It is **not** the code-writing engine.

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

## Tools

`lumen/engine/services/tool_runtime`: chat/LLM may **select** a tool; engines **execute**.

Catalog includes: `clone_repo`, `create_repo`, `git_push`, `git_pull`, `repo_inspect`, `repo_understand`, `repo_modify`, `generate_bot`, `refine_bot`, `host_*`.

Risk tiers drive HITL confirmation for high/critical actions.

## Platform

- Plans + `plan_gate` filter features post-generation.
- Credits ledger, metering, rating, balance lifecycle under `lumen/platform/`.
- Per-user sandbox under `OUTPUT_DIR` via `user_sandbox`.
- Job queue + backpressure for heavy work (especially API generate).
