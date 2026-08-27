"""Durability path after inflation cleanup: SqliteSaver + Temporal optional."""
from __future__ import annotations

from pathlib import Path

from lumen.engine.services.multi_agent.production_policy import required_workflow_engine
from lumen.engine.services.multi_agent.event_wake import temporal_enabled
from lumen.engine.services.multi_agent.langgraph_pipeline import hitl_interrupt_enabled, hitl_deliver_enabled


def test_workflow_engine_is_langgraph_sqlite_temporal():
    eng = required_workflow_engine()
    assert "langgraph_sqlite" in eng
    assert "temporal" in eng


def test_hitl_gates_exist():
    assert callable(hitl_interrupt_enabled)
    assert callable(hitl_deliver_enabled)


def test_temporal_enabled_is_bool():
    assert isinstance(temporal_enabled(), bool)


def test_deleted_workflow_engine_import_fails():
    import importlib
    with __import__("pytest").raises(ModuleNotFoundError):
        importlib.import_module("lumen.engine.services.multi_agent.workflow_engine")
