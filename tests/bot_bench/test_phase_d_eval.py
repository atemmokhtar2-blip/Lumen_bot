"""Phase D bot-bench — multi-platform scenarios + success/latency/cost summary."""
from __future__ import annotations

from pathlib import Path

from lumen.engine.services.evaluation import (
    EvalRunRecord,
    append_eval_record,
    finalize_record,
    load_eval_records,
    run_bot_bench_suite,
    summarize_evals,
)


def test_eval_record_roundtrip(tmp_path: Path):
    rec = EvalRunRecord(scenario_id="s1", platform="discord", attempts=2)
    finalize_record(rec, success=True)
    path = append_eval_record(rec, path=tmp_path / "runs.jsonl")
    rows = load_eval_records(path=path)
    assert len(rows) == 1
    assert rows[0]["success"] is True
    assert rows[0]["platform"] == "discord"
    summary = summarize_evals(rows)
    assert summary["n"] == 1
    assert summary["success_rate"] == 1.0


def test_bot_bench_suite_multi_platform(tmp_path: Path):
    result = run_bot_bench_suite(work_root=tmp_path / "bench", persist=False)
    assert "summary" in result
    assert result["summary"]["n"] >= 7
    # global bar for contract-level bench: high success on deterministic scenarios
    assert result["summary"]["success_rate"] >= 0.85
    platforms = {r["platform"] for r in result["records"]}
    assert "discord" in platforms
    assert "whatsapp" in platforms
    assert result.get("ok") is True


def test_metrics_record_eval_outcome():
    from lumen.engine.services.multi_agent.metrics import get_metrics, record_eval_outcome, metrics_snapshot

    record_eval_outcome(success=True, attempts=1, latency_s=0.01, cost_usd=0.001, platform="telegram")
    snap = metrics_snapshot()
    assert "counters" in snap


def test_cost_model_from_tokens():
    from lumen.engine.services.evaluation.cost_model import estimate_cost_usd

    c = estimate_cost_usd({"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000})
    assert c > 0


def test_live_bridge_from_fake_state(tmp_path: Path):
    from types import SimpleNamespace
    from lumen.engine.services.evaluation.live_bridge import record_from_agent_state, persist_state_evaluation
    import os

    os.environ["LUMEN_EVAL_DIR"] = str(tmp_path)
    state = SimpleNamespace(
        state_id="s1",
        attempts=2,
        qa_passed=True,
        status="passed",
        generated_path="",
        build_errors=[],
        qa_report={"errors": []},
        extensions={"usage": {"prompt_tokens": 100, "completion_tokens": 50}, "platform": "discord"},
        metadata={},
    )
    rec = record_from_agent_state(state)
    assert rec.success is True
    assert rec.platform == "discord"
    assert rec.cost_usd >= 0
    out = persist_state_evaluation(state)
    assert out["ok"] is True


def test_regression_gate():
    from lumen.engine.services.evaluation.regression import compare_to_baseline

    current = {"success_rate": 0.9, "avg_latency_s": 0.1, "n": 10}
    baseline = {"success_rate": 0.92, "avg_latency_s": 0.1, "n": 10}
    r = compare_to_baseline(current, baseline)
    assert r["ok"] is True
    bad = compare_to_baseline({"success_rate": 0.5, "avg_latency_s": 1.0}, baseline, min_success_rate=0.85)
    assert bad["ok"] is False


def test_markdown_report():
    from lumen.engine.services.evaluation.markdown_report import render_eval_markdown

    md = render_eval_markdown({"n": 3, "success_rate": 1.0, "avg_attempts": 1, "avg_latency_s": 0.01, "avg_cost_usd": 0, "by_platform": {"discord": {"n": 1, "success_rate": 1.0}}})
    assert "success_rate" in md
    assert "discord" in md


def test_bot_bench_has_at_least_10_scenarios(tmp_path: Path):
    from lumen.engine.services.evaluation.bot_bench_runner import SCENARIOS, run_bot_bench_suite

    assert len(SCENARIOS) >= 10
    result = run_bot_bench_suite(work_root=tmp_path / "bench2", persist=False)
    assert result["summary"]["n"] >= 10
    assert result["summary"]["success_rate"] >= 0.85
