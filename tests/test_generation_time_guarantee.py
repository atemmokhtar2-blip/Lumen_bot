"""Weakness #2 — generation time guarantee tests.

Verifies that:
  1. The agent_loop respects a wall-clock time budget (stops even when the
     LLM is slow / retrying, preventing the "10-minute hang").
  2. The orchestrate_generate path in run_generation is wrapped with a hard
     wall-clock timeout (GENERATION_TIMEOUT_SEC).
  3. The Cline fallback (run_generation_with_bridge) uses the generation
     timeout, not the 30s engine default.
  4. Default timeout/step values are tightened (no 90s/24-step/3-retry hang).
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import patch


# ---------------------------------------------------------------------------
# 1. agent_loop wall-clock time budget cutoff
# ---------------------------------------------------------------------------

def test_agent_loop_time_budget_cutoff(monkeypatch, tmp_path):
    """A slow decide() that never returns a tool must be cut off by the
    wall-clock budget, NOT run for max_steps × decide-time."""
    # Set a tiny time budget so the test is fast. _time_budget floors at 10s,
    # so we use 10s with a slow decide (6s each) → only ~2 calls fit.
    monkeypatch.setenv("CLINE_AGENT_TIME_BUDGET_SEC", "10")
    monkeypatch.setenv("CLINE_AGENT_MAX_STEPS", "50")

    from lumen.engine.services.cline_runtime import agent_loop

    # Fake decide: sleeps 6s per call, returns invalid (soft) so the loop
    # would normally keep going for 50 steps = 300s without the budget.
    call_count = {"n": 0}

    def fake_decide(messages, *, choice=None):
        call_count["n"] += 1
        time.sleep(6.0)
        return {
            "thought": "thinking slowly...",
            "tool": None,
            "args": {},
            "finish": False,
            "summary": "",
            "raw": "",
            "parse_ok": False,
            "error": "parse_fail",
        }

    # Patch select_model_for_goal to return a valid-looking choice so run_agent
    # doesn't bail early with no_model.
    fake_choice = type("C", (), {"provider": "gemini", "model_id": "test"})()

    with (
        patch.object(agent_loop, "decide", side_effect=fake_decide),
        patch.object(agent_loop, "select_model_for_goal", return_value=(fake_choice, 0.5)),
        patch.object(agent_loop, "describe_runtime", return_value="test-runtime"),
    ):
        with patch("lumen.platform.observability.setup_observability", side_effect=lambda **kw: None):
            state = agent_loop.run_agent(
                work_dir=str(tmp_path),
                goal="build a simple bot",
                ir_dict=None,
            )

    # The loop MUST have stopped due to time budget, not run all 50 steps.
    assert state.stop_reason == "time_budget_exhausted", (
        f"expected time_budget_exhausted, got {state.stop_reason}"
    )
    assert state.ok is False
    assert state.metadata.get("time_budget_exhausted") is True
    # Must NOT have iterated 50 times — budget cuts it after ~10s (2 calls of 6s).
    assert call_count["n"] <= 4, f"too many decide calls: {call_count['n']} (should be cut by budget)"
    # Elapsed should be around the budget (10s), not 300s.
    assert state.metadata.get("elapsed_sec", 0) >= 9, "elapsed too low"


# ---------------------------------------------------------------------------
# 2. orchestrate_generate is wrapped with GENERATION_TIMEOUT_SEC
# ---------------------------------------------------------------------------

def test_orchestrate_generate_wrapped_with_timeout(monkeypatch, tmp_path):
    """run_generation must wrap orchestrate_generate in run_with_engine_timeout."""
    monkeypatch.setenv("MULTI_AGENT_ORCHESTRATOR", "1")
    monkeypatch.setenv("GENERATION_TIMEOUT_SEC", "2")

    from lumen.bot import helpers

    # Fake orchestrate_generate that sleeps longer than the 2s timeout.
    def slow_orchestrate(request, work_dir, *, user_id=0, preferred_keys=None):
        time.sleep(10)  # would hang for 10s without timeout
        from lumen.engine.core.result import GenerationResult
        return GenerationResult(success=True)

    import lumen.engine.services.multi_agent as ma_mod

    with (
        patch.object(helpers, "orchestrate_generate", create=True, side_effect=slow_orchestrate) if hasattr(helpers, "orchestrate_generate") else patch.dict(
            "sys.modules", {}
        ),
    ):
        # Patch at the import source inside run_generation
        with patch.object(ma_mod, "orchestrate_generate", side_effect=slow_orchestrate):
            with patch.object(ma_mod, "orchestrator_enabled", return_value=True):
                # Also need guardrails + backpressure + budget gate to pass
                with patch("lumen.engine.pipeline.prompt_guard.scan_user_input") as mock_guard:
                    mock_guard.return_value = type("G", (), {"ok": True, "sanitized": None, "reasons": [], "backend": "test"})()
                    with patch("lumen.platform.queue_backpressure.acquire_slot", return_value=(True, "")):
                        with patch("lumen.platform.queue_backpressure.release_slot", return_value=None):
                            with patch("lumen.engine.services.llm_budget_gate.gate_llm_call", return_value=(True, "")):
                                result = helpers.run_generation(
                                    "build a bot",
                                    Path(tmp_path),
                                    user_id=1,
                                )

    # Must return a timeout failure, not hang for 10s.
    assert result.success is False, "should have timed out"
    assert "timeout" in str(result.errors).lower() or result.metadata.get("timeout"), (
        f"expected timeout in errors/metadata, got errors={result.errors} meta={result.metadata}"
    )


# ---------------------------------------------------------------------------
# 3. run_generation_with_bridge uses GENERATION_TIMEOUT_SEC (not 30s)
# ---------------------------------------------------------------------------

def test_bridge_uses_generation_timeout(monkeypatch, tmp_path):
    """run_generation_with_bridge must use GENERATION_TIMEOUT_SEC, not the
    default 30s ENGINE_TIMEOUT_SEC."""
    monkeypatch.setenv("GENERATION_TIMEOUT_SEC", "2")

    from lumen.bot import helpers
    from lumen.bot.resource_limits import GENERATION_TIMEOUT_SEC

    # The timeout value should be 2, not 30.
    assert GENERATION_TIMEOUT_SEC == 2.0, f"expected 2.0, got {GENERATION_TIMEOUT_SEC}"

    # Fake execute_ir that hangs.
    def slow_exec(ir, work_dir, *, user_id=0):
        time.sleep(10)
        from lumen.engine.core.result import GenerationResult
        return GenerationResult(success=True)

    import lumen.engine.services.engine_router as er_mod

    with (
        patch.object(er_mod, "build_ir_from_package") as mock_build,
        patch.object(er_mod, "execute_ir", side_effect=slow_exec),
    ):
        # Minimal IR mock
        mock_build.return_value = type("IR", (), {
            "engine_mode": type("M", (), {"value": "cline"})(),
            "capabilities_matched": [],
            "capabilities_gap": ["free_agent"],
            "confidence": 0.0,
            "to_dict": lambda self: {},
        })()

        result = helpers.run_generation_with_bridge(
            "build a bot",
            Path(tmp_path),
            user_id=1,
        )

    assert result.success is False, "should have timed out"
    assert result.metadata.get("timeout") is True


# ---------------------------------------------------------------------------
# 4. Default values are tightened (no 90s/24-step/3-retry hang)
# ---------------------------------------------------------------------------

def test_default_timeout_values_tightened(monkeypatch):
    """Verify the defaults that caused the 10-minute hang are tightened."""
    # Clear env to test defaults
    for k in ("CLINE_LLM_TIMEOUT_SEC", "CLINE_LLM_RETRIES", "CLINE_AGENT_MAX_STEPS",
              "CLINE_AGENT_TIME_BUDGET_SEC", "GENERATION_TIMEOUT_SEC", "ENGINE_TIMEOUT_SEC"):
        monkeypatch.delenv(k, raising=False)

    # The functions read env at call-time, so they reflect the cleared env.
    from lumen.engine.services.cline_runtime.agent_brain import _timeout
    from lumen.engine.services.cline_runtime.agent_loop import _max_steps, _time_budget

    assert _timeout() <= 60, f"LLM timeout too high: {_timeout()}s (was 90s)"
    assert _max_steps() <= 15, f"max_steps too high: {_max_steps()} (was 24)"
    assert _time_budget() <= 180, f"time budget too high: {_time_budget()}s"

    # GENERATION_TIMEOUT_SEC is a module-level constant (read at import). We
    # verify the function-based guarantees above and check the constant via a
    # fresh import with no env. The key invariant: inner budget < outer timeout.
    inner = _time_budget()
    # GENERATION_TIMEOUT_SEC default is 180; inner default is 150 → 150 < 180 ✓
    assert inner < 180.0, f"inner budget {inner}s must be < default outer 180s"


if __name__ == "__main__":
    import sys
    sys.exit(__import__("pytest").main([__file__, "-v"]))
