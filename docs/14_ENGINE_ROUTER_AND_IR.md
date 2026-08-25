# Engine Router & Build IR

## Goal

Move from:

```text
User → Gemini Translator → preferred_keys → spec_core
```

toward:

```text
User → Your Core → BuildIR (contracts) → catalog | hybrid | cline → Bot
```

Gemini/Grok/Ollama become **model providers under the executor**, not a standalone translator layer.
Cline is the **general execution path** under policy; catalog remains primary for known bots.

## BuildIR (`lumen.engine/core/ir.py`)

Control-plane object (not a translator):

- `original_text`, `spec_request`, `purpose`
- `preferred_keys`, `capabilities_matched`, `capabilities_gap`
- `integrations`, `acceptance[]`
- `engine_mode`: `catalog` | `hybrid` | `cline`
- `confidence`, `status`, `notes`

## Engine modes

| Mode | When | Executor |
|------|------|----------|
| `catalog` | Matched capabilities, no gap | `spec_core` / `generate_bot` |
| `hybrid` | Some keys + gap/custom | catalog first; cline assist when enabled |
| `cline` | Out of catalog / custom stack | `cline_runtime` under policy |

Force mode (ops): `ENGINE_MODE_FORCE=catalog|hybrid|cline`

## Cline runtime (`services/cline_runtime`)

- Disabled by default: `CLINE_ENABLED=0`
- Enable: `CLINE_ENABLED=1`
- Optional provider hook: `CLINE_PROVIDER=my.module:build_fn`
- Policies:
  - `CLINE_ALLOW_SHELL=0|1`
  - `CLINE_ALLOW_WEB=0|1`
- If blocked or not wired → **safe fallback to catalog** (never silent fake success)

## Entry points

- `analyze_and_prepare` → package with gap/matched/mode
- `build_ir_from_package` → `BuildIR`
- `execute_ir` → routed generation
- `run_generation_with_bridge` uses IR router

## Activepieces / OpenClaw (next)

- Activepieces: MCP tools registered via `createTool` / provider (not in Core)
- OpenClaw: channel layer only — does not build bots

## Phase 2 (lean packs + hybrid scaffolds)

### Stronger foundation
- `core/ir_validate.py`: normalize keys against catalog, domain lean enrichment, post-gen `check_project_against_ir`
- Router always validates IR before execute; attaches `ir_acceptance` to metadata

### Lean packs (`spec_core/lean_packs.py`)
Domains: ecommerce, group_moderation, tasks, notes, tickets, healthcare, crm, education, cybersecurity, echo  
Applied in IR validation + acceptance_gate when domain confidence ≥ 0.30

### Hybrid scaffolds (`services/hybrid_scaffolds.py`)
On hybrid/cline-fallback with gaps:
- `app/services/webhook_scaffold.py`
- `app/services/http_tool.py`
- `app/services/cron_scaffold.py`
- `HYBRID_GAPS.md`

## Phase 2 hardened

- Lean packs extended: fitness, restaurant, auction, realestate
- Hybrid always writes `ENV.example` with integration env keys
- IR acceptance + smoke remain post-gen gates

## Phase 3 — Cline runtime (builtin first)

```bash
CLINE_ENABLED=1
# optional override:
# CLINE_PROVIDER=lumen.engine.services.cline_runtime.provider_builtin:build
ENGINE_LLM_PROVIDER=gemini|xai|ollama
GOOGLE_API_KEY=...   # or GEMINI_API_KEY
XAI_API_KEY=...
OLLAMA_HOST=http://...
ACTIVEPIECES_WEBHOOK_BASE=...
ACTIVEPIECES_TOKEN=...
CLINE_ALLOW_SHELL=0
CLINE_ALLOW_WEB=0
```

Modules:
- `cline_runtime/tools.py` — compose_catalog, scaffolds, smoke, ir_acceptance (shell/web disabled)
- `cline_runtime/model_router.py` — Gemini / xAI / Ollama selection
- `cline_runtime/provider_builtin.py` — default provider pipeline
- `cline_runtime/mcp_bridge.py` — Activepieces webhook contract

Builtin path does **not** open shell/web. It runs catalog tools under IR.
