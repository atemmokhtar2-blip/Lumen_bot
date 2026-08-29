# Lumen Root Fix — ONE Strong Path (from foundation)

## Phase 0: Research & Plan
- [x] Read actual code (message_router, helpers, agent_loop, agent_brain, resource_limits, progress_tracker, orchestrator)
- [x] Research strongest real solutions (web + YouTube + LangGraph official docs)
- [x] Save research findings to RESEARCH_FINDINGS.md
- [x] Create this todo.md plan

## Phase 1: Clean Dead Code (spec_core removal — 61 refs in 26 files)
- [x] 1a. Remove dead spec_core blocks from message_router.py (~300 lines: Stage-5 eval, Stage-3 feedback, L3 clarify) — 1701→1434 lines
- [x] 1b. Remove spec_core refs from message_stages/pre_generate.py
- [x] 1c. Remove dead spec_core blocks from engine services (feasibility_gate, anti_hallucination/gate, ui_state/engine_needs) — restored real logic hidden behind dead ImportError blocks
- [x] 1d. Remove spec_core refs from engine core (ir_validate) — domain_detector+lean_packs block removed
- [x] 1e. Remove spec_core refs from delivery.py — Stage-4 narrative + Stage-5 metrics (102 lines)
- [x] 1f. Remove dead spec_core refs from generate_bridge.py (skip_clarify_once)
- [x] 1g. Delete 7 dead test files (phase4/7/8/14_15, detection_phase2, qwen_translator_client, capabilities_scale)
- [x] 1h. Verified: ZERO imports of deleted lumen.engine.spec_core package remain. Remaining "spec_core" references are: (a) comments/docstrings documenting removal, (b) _spec_core_capabilities() function name (imports LIVE catalog, returns []), (c) "spec_core_capabilities" context dict key (functional, passes caps to LLM). All functional, none dead.
- [x] 1i. Syntax verified OK on all 8 modified files; imports verified OK on 6/7 (1 needs telegram pkg not in sandbox)
- [x] 1j. Implemented is_clearly_non_bot() in feasibility_gate.py (real guardrail, was dead behind raise ImportError) + _is_clearly_non_bot/_detect_bot_request_arabic in anti_hallucination/gate.py
- [x] 1k. Tests: 699 passed (up from 680), 133 failed (down from 152). Baseline confirmed identical — ZERO regressions. Fixed 19 NameError failures.

## Phase 2: Add Wall-Clock Deadline Propagation (THE critical fix)
- [ ] 2a. Create lumen/engine/services/deadline.py — Deadline class with remaining(), expired(), clamp()
- [ ] 2b. Add GENERATION_DEADLINE_SEC env (default 300s = 5min, configurable)
- [ ] 2c. Wire deadline into run_generation (helpers.py) — propagated to both multi-agent AND Cline paths
- [ ] 2d. Wire deadline into agent_loop.run_agent — check deadline before each step, stop if expired
- [ ] 2e. Wire deadline into agent_brain.decide — clamp per-call timeout to deadline.remaining()
- [ ] 2f. Wire deadline into orchestrator.orchestrate_generate — stop if deadline expired
- [ ] 2g. Add stagnation detection in agent_loop — detect repeated tool calls/errors → auto-finish
- [ ] 2h. When deadline expires: deliver PARTIAL result with clear Arabic message (not hang)
- [ ] 2i. Update run_with_heartbeat to accept deadline — stop heartbeat when deadline expires

## Phase 3: Simplify Message Router (ONE clear path)
- [ ] 3a. Remove redundant active_repo binding (early bind + later bind → keep one)
- [ ] 3b. Remove redundant force_generate_once detection (4 places → consolidate)
- [ ] 3c. Remove dead Stage-5/Stage-3/L3 blocks (done in 1a, verify clean)
- [ ] 3d. Document the ONE clear message path in comments
- [ ] 3e. Verify router handles all cases through the single path

## Phase 4: Fix Multi-Agent → Cline Fallback UX Equality
- [ ] 4a. Both paths receive same deadline budget
- [ ] 4b. Both paths produce same UX (heartbeat, progress, delivery)
- [ ] 4c. HITL resume works with deadline (resume uses remaining deadline, not restart)
- [ ] 4d. Fallback triggers cleanly when multi-agent fails (error_handler pattern)

## Phase 5: Tests & Quality Gate
- [ ] 5a. Write test for deadline propagation (deadline expires → partial delivery, not hang)
- [ ] 5b. Write test for stagnation detection (repeated calls → auto-finish)
- [ ] 5c. Run full test suite — confirm no regressions
- [ ] 5d. Verify generated bot quality (README, token setup clarity)

## Phase 6: Commit & Push
- [ ] 6a. Commit with clear message
- [ ] 6b. Push to origin/Lumen
- [ ] 6c. Verify push success
- [ ] 6d. Report to user
