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

## BuildIR (`telegram_bot_engine/core/ir.py`)

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
