# Debug: Engine hangs — no bot generated

## Problem
User sends request to Lumen bot in Telegram. Bot responds to /start but then hangs for very long time with no bot output. No bot generated, nothing delivered.

## Investigation (COMPLETE — root causes confirmed by testing)
- [x] 1. Trace full path: Telegram → message_router → execute_bot_generation → run_with_heartbeat → run_generation → orchestrator → LangGraph → agent_loop
- [x] 2. Confirmed RC1: `check_tenant_llm_budget` returns `False, "llm_budget_backend_unavailable"` without Redis → generation blocked instantly (0.13s, not hang, but broken)
- [x] 3. Confirmed RC2: When budget passes, orchestrator hits HITL plan gate (0.66s) → returns awaiting_approval → user sees "📋 الخطة جاهزة"
- [x] 4. Confirmed RC3: `langgraph-checkpoint-sqlite` NOT installed → MemorySaver only → HITL resume across processes fails → infinite "confirm the plan" loop (THE HANG)
- [x] 5. Confirmed RC4: When no LLM keys + budget passes + same-process resume → work fails gracefully (no_llm_provider) in 4.7s, status=FAILED
- [x] 6. Confirmed RC5: `run_with_heartbeat` has NO timeout on `asyncio.to_thread` — defense-in-depth gap

## Fixes (RADICAL — root cause, not symptom)
- [x] F1. Install `langgraph-checkpoint-sqlite` → durable checkpoints → HITL resume works across processes
- [x] F2. Fix `check_tenant_llm_budget` — add in-process budget fallback when Redis unavailable (dev/small deployments)
- [x] F3. When `select_model` returns "none" (no LLM keys), skip HITL plan gate entirely — surface clear "no LLM keys" error instead of trapping user in approval loop
- [x] F4. Add `asyncio.wait_for` timeout on `run_with_heartbeat`'s `to_thread` as defense-in-depth
- [x] F5. Ensure HITL resume failure surfaces clear error to user (no silent infinite loop)

## Verification
- [x] V1. Test: no Redis + no LLM keys → clear error (not budget_backend_unavailable)
- [x] V2. Test: Redis/budget passes + no LLM keys → clear "no LLM keys" error (not HITL trap)
- [x] V3. Test: HITL resume across simulated process boundary → works with SqliteSaver
- [x] V4. Test: run_with_heartbeat timeout fires

## Ship
- [ ] S1. COMMIT + PUSH
