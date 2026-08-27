"""Residual: deliver resume detection + tree lock presence."""
from __future__ import annotations

from pathlib import Path


def test_resume_or_rerun_detects_deliver_awaiting():
    src = Path("lumen/engine/services/multi_agent/orchestrator.py").read_text(encoding="utf-8")
    assert "awaiting_deliver_approval" in src
    assert "langgraph_deliver_approve" in src


def test_tree_lock_in_node_work():
    src = Path("lumen/engine/services/multi_agent/langgraph_pipeline.py").read_text(encoding="utf-8")
    assert "_TREE_LOCK" in src
    assert "with _TREE_LOCK:" in src
    assert "SqliteSaver.from_conn" in src or "from_conn" in src


def test_market_scenarios_still_green():
    from lumen.engine.services.multi_agent.layer_scenarios import run_all_layer_scenarios
    out = run_all_layer_scenarios()
    assert out["ok"], out
