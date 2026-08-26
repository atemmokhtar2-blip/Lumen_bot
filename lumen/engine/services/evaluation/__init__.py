"""Phase D — Evaluation: success rate, attempts, latency, cost (live + bench)."""
from __future__ import annotations

from .bot_bench_runner import run_bot_bench_suite
from .cost_model import estimate_cost_usd
from .eval_store import append_eval_record, load_eval_records, summarize_evals
from .live_bridge import persist_state_evaluation, record_from_agent_state, record_from_run_report
from .markdown_report import render_eval_markdown
from .regression import compare_to_baseline, regression_check, save_baseline
from .run_record import EvalRunRecord, finalize_record

__all__ = [
    "EvalRunRecord",
    "finalize_record",
    "append_eval_record",
    "load_eval_records",
    "summarize_evals",
    "run_bot_bench_suite",
    "estimate_cost_usd",
    "persist_state_evaluation",
    "record_from_agent_state",
    "record_from_run_report",
    "render_eval_markdown",
    "compare_to_baseline",
    "regression_check",
    "save_baseline",
]
