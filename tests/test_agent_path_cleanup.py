"""Architectural inflation cleanup — deleted modules must stay gone."""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "lumen" / "engine" / "services" / "multi_agent"

DELETED = [
    "fallback_template.py",
    "swarm.py",
    "worker_pool.py",
    "concurrency.py",
    "circuit.py",
    "generated_tests.py",
    "redis_board.py",
    "workflow_engine.py",
    "durable_workflow.py",
]


@pytest.mark.parametrize("name", DELETED)
def test_bloat_module_deleted(name: str):
    assert not (ROOT / name).exists(), f"{name} must remain deleted"


def test_core_surface_imports():
    from lumen.engine.services.multi_agent import (
        assemble_plan,
        evaluate_task,
        run_all_layer_scenarios,
        langgraph_available,
    )
    assert callable(assemble_plan)
    assert callable(evaluate_task)
    assert callable(run_all_layer_scenarios)


def test_production_policy_no_swarm():
    from lumen.engine.services.multi_agent.production_policy import policy_snapshot
    snap = policy_snapshot()
    assert "allow_swarm" not in snap
    engine = str(snap.get("workflow_engine") or "")
    assert "temporal_sequential" in engine or "langgraph" in engine
