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

## Force-generate fast path

Triggers when:

- Explicit generation verbs + bot (`_looks_like_generation_request`)
- Free-agent / bot-spec heuristics (`_looks_like_bot_spec`)
- Confirm phrases after a prior bot request (`_is_confirm_phrase`)
- Pending chat action confirm for generate/refine

Then:

1. Instant ack + status message
2. Optional `translate_request` + `analyze_and_prepare`
3. `build_ir_from_package` → `execute_ir` (heartbeat)
4. Fallback: `run_generation` → multi-agent or Cline bridge
5. `deliver_generation_result` (smoke test required before ZIP)
6. Generation cache + session persist

## Chat understanding path

When not already force-generate:

1. Gemini `chat_request` (intent + optional action/translation)
2. On generate/refine action: Qwen `translate_request` → validated spec fields
3. Gemini failure + explicit build → Qwen rescue translation
4. Sets `force_generate_once` and continues into generation

Chat does not write project files.

## Delegated routers (before final generate)

1. `try_handle_token`
2. `try_handle_git`
3. `try_handle_hosting`
4. `try_handle_repo_dev`
5. Engine-only tools via `execute_tool` (`repo_understand`, `repo_inspect`, …)
6. If `active_repo` bound and message is free-form Q → force `repo_understand`
7. Non-bot / non-hard → short deterministic help (no LLM partner routing)

## `run_generation` order (`helpers.py`)

1. Queue backpressure slot
2. LLM budget gate
3. Optional forced Groq codegen (`GROQ_CODEGEN_ENABLED`)
4. Multi-agent orchestrator if enabled → verified template fallback on failure
5. `run_generation_with_bridge` → IR → `execute_ir` (Cline)
