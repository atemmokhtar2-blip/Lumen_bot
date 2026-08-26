# Generation (from code)

## Canonical path

```
user text
  → optional translate / bridge package
  → BuildIR (lumen.engine.core.ir)
  → validate_and_normalize_ir
  → execute_ir (engine_router)
  → execute_cline_ir (cline_runtime)
  → agent_loop writes under work_dir
  → smoke test
  → ZIP delivery (Telegram) or job artifact (API)
```

## BuildIR

Fields used as handoff: `original_text`, `spec_request`, `purpose`, `preferred_keys`, `capabilities_matched`, `capabilities_gap`, `integrations`, `engine_mode`, `confidence`, `metadata`, `user_id`.

Product always sets/forces `engine_mode=cline` before execution.

## Cline agent (`CLINE_MODE=agent`)

- Goal built from IR (`provider_agent._goal_from_ir`)
- `run_agent`: max steps from `CLINE_AGENT_MAX_STEPS` (clamped)
- Brain decides tool calls; FS tools write the project
- Acceptance check on resulting tree
- Audit file `CLINE_AGENT.md` written in work dir

Kill switch: `CLINE_ENABLED=0`.

## What is not the generator

- Telegram chat models
- `spec_core` package (helpers only)
- Catalog / infinite modes (present in enums and legacy metadata; not selected by router)
