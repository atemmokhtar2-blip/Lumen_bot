# AI Handoff & Roadmap — Capability Maestro Bot

> **IMPORTANT FOR ANY AI / DEVELOPER CONTINUING THIS WORK**  
> This platform is **in active construction**. Do not assume the stack is finished.  
> Read this file first, then `docs/MASTER.md` and `docs/14_ENGINE_ROUTER_AND_IR.md`.  
> Prefer **extending** existing contracts over inventing parallel paths.  
> After every change: test catalog bots (shop/group/tasks) + push.

---

## Product intent (do not break)

| Principle | Meaning |
|-----------|---------|
| Grok = chat/router only | Does not write bot code for the user product path |
| Catalog first | Known bots use deterministic `spec_core` |
| IR is control plane | `BuildIR` is a contract, not a “translator layer” |
| Cline = general path | Under policy; default builtin tools, not blind shell |
| Planning ≠ Generation | Validate IR before write |
| Channels ≠ Engine | Telegram/OpenClaw deliver; they do not build |
| Repo Intelligence is derived | Never treat analysis as source of truth over code |

---

## Architecture (current)

```text
USER (Telegram)
  → bot_interface (message_router / Grok chat)
  → analyze_and_prepare (bridge rules + optional translation dict)
  → BuildIR + validate_and_normalize_ir
  → engine_router.execute_ir
        ├─ catalog  → telegram_bot_engine.generate_bot (spec_core)
        ├─ hybrid   → catalog + hybrid_scaffolds
        └─ cline    → cline_runtime (builtin provider or CLINE_PROVIDER)
  → control_plane (permission, plan, project, delivery_gate)
  → ZIP / host to user
```

### Control Plane vs Runtime Plane

| Control (`telegram_bot_engine/control_plane/`) | Runtime |
|-----------------------------------------------|---------|
| `projects.py` ProjectStore | `spec_core` generate |
| `plans.py` PlanStore | `cline_runtime` tools |
| `permissions.py` | workers / smoke |
| `delivery_gate.py` | hybrid_scaffolds |

| Channels (`telegram_bot_engine/channels/`) |
|------------------------------------------|
| `openclaw_boundary.py` — multi-channel publish contract only |

---

## File map (where things live)

### Core contracts
| Path | Role |
|------|------|
| `telegram_bot_engine/core/ir.py` | BuildIR, EngineMode, acceptance criteria |
| `telegram_bot_engine/core/ir_validate.py` | Normalize IR, lean pack enrich, check_project_against_ir |
| `telegram_bot_engine/core/contracts.py` | Engine/Builder/PipelineStage ABCs |
| `telegram_bot_engine/core/context.py` | Generation context (do not turn into God Object) |

### Routing & generation
| Path | Role |
|------|------|
| `telegram_bot_engine/services/engine_groq_bridge.py` | Text → package (keys, gap, mode) |
| `telegram_bot_engine/services/engine_router.py` | IR → catalog/hybrid/cline + finalize |
| `telegram_bot_engine/generate_bot.py` | Main catalog generator |
| `telegram_bot_engine/spec_core/` | Registry, domain_detector, acceptance_gate, lean_packs |
| `bot_interface/helpers.py` | `run_generation`, `run_generation_with_bridge` |
| `bot_interface/routers/message_router.py` | User Telegram force_generate path |

### Phase 2 — lean + hybrid
| Path | Role |
|------|------|
| `telegram_bot_engine/spec_core/lean_packs.py` | Domain minimum feature sets |
| `telegram_bot_engine/services/hybrid_scaffolds.py` | webhook/http/cron stubs + ENV.example |

### Phase 3 — Cline runtime (builtin)
| Path | Role |
|------|------|
| `cline_runtime/tools.py` | ToolSpec registry (safe tools) |
| `cline_runtime/tool_runner.py` | Policy enforcement per tool call |
| `cline_runtime/provider_builtin.py` | Default pipeline when CLINE_ENABLED=1 |
| `cline_runtime/model_router.py` | gemini / xai / ollama selection |
| `cline_runtime/mcp_bridge.py` | Activepieces webhook contract |
| `cline_runtime/executor.py` | Entry + policy + provider dispatch |

### Phase 4 — Control plane + channels
| Path | Role |
|------|------|
| `control_plane/*` | projects, plans, permissions, delivery_gate |
| `channels/openclaw_boundary.py` | OpenClaw publish stub |

### Docs
| Path | Role |
|------|------|
| `docs/MASTER.md` | Index |
| `docs/14_ENGINE_ROUTER_AND_IR.md` | IR + modes |
| `docs/15_ROADMAP_AND_AI_HANDOFF.md` | **This file** |

---

## Environment variables

| Var | Default | Meaning |
|-----|---------|---------|
| `CLINE_ENABLED` | 0 | Enable general path (builtin provider) |
| `CLINE_PROVIDER` | (builtin) | `module:function` override |
| `CLINE_ALLOW_SHELL` | 0 | Allow run_shell tool |
| `CLINE_ALLOW_WEB` | 0 | Allow fetch_web tool |
| `ENGINE_MODE_FORCE` | — | Force catalog\|hybrid\|cline |
| `ENGINE_LLM_PROVIDER` | auto | gemini\|xai\|ollama |
| `GOOGLE_API_KEY` / `GEMINI_API_KEY` | — | Gemini |
| `XAI_API_KEY` | — | Grok model under router |
| `OLLAMA_HOST` | — | Local/remote Ollama |
| `ACTIVEPIECES_WEBHOOK_BASE` | — | Integration webhooks |
| `OPENCLAW_URL` / `OPENCLAW_TOKEN` | — | Multi-channel |
| `CONTROL_PLANE_DIR` | /tmp/maestro_control | Plan/project JSON store |
| `IR_ACCEPTANCE_HARD` | 0 | Fail delivery if features missing |

---

## Roadmap status

| Phase | Status | Notes |
|-------|--------|-------|
| 1 IR + engine_router | **Done (baseline)** | Was thin; reinforced in later commits |
| 2 Lean packs + hybrid scaffolds | **Done (hardened)** | More domains + ENV.example |
| 3 Cline builtin tools + model router + MCP contract | **Done (hardened)** | ToolRunner; not official Cline npm SDK yet |
| 4 Control plane + OpenClaw boundary | **Done (this commit)** | File-backed stores; OpenClaw stub |
| 5 Official Cline SDK package embed | **NOT DONE** | Optional when Node/SDK available in deploy |
| 6 Activepieces live MCP client | **NOT DONE** | Only webhook helper exists |
| 7 OpenClaw real multi-channel | **NOT DONE** | Boundary only; product still Telegram-native |
| 8 Capability marketplace / pack versioning | **NOT DONE** | capability_packs load exists; no market UI |
| 9 Full separation Runtime workers/containers | **NOT DONE** | Conceptual only |

---

## Known weaknesses (do not ignore)

1. **Builtin Cline ≠ full Cline SDK** — no autonomous multi-file agent loop yet.  
2. **Gemini translator path still exists** — optional; prefer IR from rules + bridge; do not rebuild a second brain.  
3. **Control plane storage is local JSON** — not multi-instance safe without shared volume/DB.  
4. **OpenClaw / Activepieces** are contracts — production wiring remaining.  
5. **Domain coverage** is wide in registry (343 keys) but AR rules + lean packs cover a subset well.  
6. **Blackboard JSON** may log non-serializable objects (noise; non-fatal).  

---

## How to continue safely

1. Read IR + router tests mentally: shop / group / tasks must stay `catalog` + smoke green.  
2. New features: add capability in registry → lean pack if domain → AR rule if Arabic UX needs it.  
3. General “any idea” work: extend `tools.py` + policies, not free shell.  
4. Never merge Planning into Generation inside Grok chat.  
5. Push after each coherent change; update **this file** when phase status changes.

---

## Quick test commands (local)

```bash
CLINE_ENABLED=1 python -c "
from pathlib import Path
from telegram_bot_engine.services.engine_groq_bridge import analyze_and_prepare
from telegram_bot_engine.services.engine_router import build_ir_from_package, execute_ir
pkg = analyze_and_prepare('بوت متجر سلة', None)
ir = build_ir_from_package(pkg, user_id=1)
r = execute_ir(ir, Path('/tmp/t'), user_id=1)
print(r.success, r.metadata.get('project_id'), r.metadata.get('engine_router_mode'))
"
```

---

*Last structured handoff: Phase 4 complete. Next recommended: shared DB for control plane OR live Activepieces webhook E2E.*
