# Phase D — Gate report (honest)

## Primary checks

| Check | Result |
|-------|--------|
| evaluation package (record/store/bench/cost/live/regression) | YES |
| bot-bench multi-platform scenarios (≥10) | YES |
| metrics: success / attempts / latency / cost | YES |
| live_bridge from run_report | YES |
| baseline + REPORT committed | YES (`docs/eval/`) |
| pytest `tests/bot_bench/` | 20 passed (last run) |

## Secondary / residual

| Gap | Status |
|-----|--------|
| Thousands of live LLM generations scored in prod | NOT yet |
| Human preference / SWE-bench class harness | NOT yet |
| Always-on eval dashboard | deferred to E metrics views |

**Decision:** D accepted for transition to E on contract + instrumentation grounds — **not** claimed as closed global-SOTA evaluation.


## Hard generation depth (follow-up)

| Check | Result |
|-------|--------|
| Medium-hard multi-module E2E per platform | YES (`hard_generation.py`) |
| quality_score 0..1 | YES |
| Critic + repair loop in bench | YES |
| CI runs full `tests/bot_bench/` | YES |
| Live LLM generation in CI | optional via `LUMEN_BENCH_LIVE_LLM` |
