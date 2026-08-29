# Lumen Root Fix — ONE Strong Path (from foundation)

## Phase 0: Research & Plan
- [x] Read actual code (message_router, helpers, agent_loop, agent_brain, resource_limits, progress_tracker, orchestrator)
- [x] Research strongest real solutions (web + YouTube + LangGraph official docs)
- [x] Save research findings to RESEARCH_FINDINGS.md
- [x] Create this todo.md plan

## Phase 1: Weakness #2 — Generation Time Guarantee (COMPLETE, PUSHED)
- [x] Add GENERATION_TIMEOUT_SEC to resource_limits.py (180s default, cap 600s)
- [x] Wrap orchestrate_generate with run_with_engine_timeout(GENERATION_TIMEOUT_SEC) in helpers.py
- [x] Wrap run_generation_with_bridge with GENERATION_TIMEOUT_SEC
- [x] Add _time_budget() wall-clock cutoff in agent_loop.run_agent (150s default)
- [x] Tighten agent_brain: timeout 90s→45s, retries 3→2, max_steps 24→12
- [x] Write 4 tests (test_generation_time_guarantee.py) — ALL PASS
- [x] Run existing tests — no regressions
- [x] COMMIT 3190cec + PUSH + verify

## Phase 2: Weakness #1 — Simplify Message Router (ONE clear path)
- [x] 2.1 Read full message_router.py (1434 lines) + message_intent.py — map all branches
      DEAD CODE IDENTIFIED:
      (a) _free_agent_mode() always returns True — 5 call sites (router L301,545,546,1348; early_gates import-only L30)
      (b) _qwen_rescue_translation() always returns None — 1 call site (router L711) + dead test file
      (c) The "free-agent mode" block (L301-310): condition reduces to `not force_generate_once` — _free_agent_mode() is dead noise
      (d) The "skip chat / free-agent vs engine" block (L545-558): if _free_agent_mode() is always True, the `else` branch (L553-558) is unreachable dead code
      (e) L1348: `if _free_agent_mode():` sets detection_preferred_keys=[] — since always True, the `else` branch is unreachable dead code
- [x] 2.2 Delete _free_agent_mode() dead code:
      - Removed _free_agent_mode() function + public alias from message_intent.py
      - Removed import + all 5 call sites in message_router.py (simplified conditions to True-branch)
      - Removed unused import from early_gates.py
      - Deleted dead test test_qwen_rescue_fallback.py (tests retired no-op)
- [x] 2.3 Delete _qwen_rescue_translation() dead code:
      - Removed function + public alias from message_intent.py
      - Removed call site + dead variable block (L695-735) in message_router.py — simplified to single `if isinstance(chat_result, dict):` path
- [x] 2.4 Verify: syntax check + imports + 21 tests PASS (4 generation-time + 17 hitl/confirm) — no regressions
      - Fixed test isolation bug in test_generation_time_guarantee.py (module-level constant caching)
      - Confirmed pre-existing failures (capability_detection, firecracker) are NOT caused by these changes
- [ ] 2.5 COMMIT + PUSH + verify

## Phase 3: Weakness #4 — Clean Sprawling Code (audit + delete dead tools)
- [ ] 3.1 Audit unused tools/services (repo_intelligence, static_dev_gate, package_reality, browser_use)
- [ ] 3.2 Delete confirmed dead code
- [ ] 3.3 COMMIT + PUSH + verify
