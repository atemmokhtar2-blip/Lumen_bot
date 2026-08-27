"""Market-grade scenario suite for all four agent layers."""
from __future__ import annotations

from lumen.engine.services.multi_agent.layer_scenarios import run_all_layer_scenarios


def test_all_market_layer_scenarios():
    out = run_all_layer_scenarios()
    failed = [r for r in out["results"] if not r["ok"]]
    assert out["ok"], f"failed={failed}"
    assert out["passed"] == out["total"]
    assert out["total"] >= 12
