# Telegram message flow (from code)

Source: `lumen/bot/routers/message_router.py` → `handle_message`.

## Order of gates

1. Allowlist (`is_allowed`)
2. Mongo user ensure + plan
3. Rate limit
4. Groups: require @mention or reply-to-bot
5. Clamp text length
6. Under-development complaint short-circuit
7. Multi-agent HITL (`try_handle_hitl_message`)
8. `/plan` status
9. Capability ops commands
10. Restore durable session (`session_store`)
11. Bot token paste → `token_handler` (before thinking bubble)
12. Thinking indicator for normal paths

## Force-generate path

Triggers when generation heuristics match (explicit verbs, bot-spec, confirm phrases).

Then:

1. Instant ack + status message
2. Rule/capability feature extraction (`engine_groq_bridge.analyze_and_prepare` — **no** LLM translate/chat)
3. `build_ir_from_package` → `execute_ir` (agent loop + model_catalog)
4. Fallback: `run_generation` → multi-agent or Cline bridge
5. `deliver_generation_result` (smoke test required before ZIP)
6. Generation cache + session persist

## LLM ownership

- **Single path:** `select_model_for_goal` → `agent_brain.decide` → provider adapters
- **Catalog:** `lumen/engine/services/llm/model_catalog.py`
- **Removed permanently:** `translate_request`, `chat_request`, `llm/facade`, `llm_budget_gate`

## Delegated routers (before final generate)

1. `try_handle_token`
2. `try_handle_git`
3. `try_handle_hosting`
4. `try_handle_repo_dev`
5. Engine-only tools via `execute_tool`
6. If `active_repo` bound and message is free-form Q → force `repo_understand`
