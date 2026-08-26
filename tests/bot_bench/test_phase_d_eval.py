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
