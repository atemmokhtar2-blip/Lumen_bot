# HITL Infinite-Loop Bug Fix — ROOT CAUSE

## Root Cause (IDENTIFIED)
- `langgraph-checkpoint-sqlite` missing from requirements → MemorySaver fallback (process-local) → checkpoint lost across processes (RQ worker vs Telegram webhook) → `Command(resume=...)` with missing thread_id silently restarts graph → re-interrupts → infinite "confirm the plan" loop, no generation ever starts.

## Fixes Applied (CODE CHANGED)
- [x] requirements.txt: add `langgraph-checkpoint-sqlite==3.1.1`
- [x] flags.py: `_shared_checkpointer()` loud error when HITL + MemorySaver only
- [x] langgraph_pipeline/__init__.py: export `_shared_checkpointer`
- [x] runner.py: `resume_langgraph_hitl()` detect missing checkpoint + re-interrupt → raise RuntimeError
- [x] orchestrator.py: `_resume_or_rerun()` don't fall through to orch.run() on approved resume exception → FAILED with Arabic error
- [x] graph_builder.py: fix 4 wrong relative imports (`.X` → `..X`)

## Verify
- [x] Confirm repro scripts show fix working (repro_nostate, repro_full, repro_hitl)
- [x] Determine test_hitl_deliver_routing failures: PRE-EXISTING (stale langgraph_pipeline.py file path, fails without my changes too)
- [x] All 5 test failures are pre-existing (stale file path + missing exports), zero regressions from my changes
- [ ] Write new test for cross-process checkpoint-missing scenario
- [ ] Run full test suite, confirm no regressions from my changes

## Push
- [ ] Commit HITL fixes
- [ ] Push to GitHub: Lumen + security-hardening-v1 branches
- [ ] Verify push success
