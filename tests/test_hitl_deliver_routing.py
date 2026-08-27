"""HITL deliver gate must be reachable from after_critique."""
from __future__ import annotations

import os
from pathlib import Path

from lumen.engine.services.multi_agent.state import AgentState, AgentStatus
from lumen.engine.services.multi_agent.task_tree import TaskTree, TaskNode, TaskStatus


def test_after_critique_routes_to_deliver_gate_when_enabled(monkeypatch):
    monkeypatch.setenv("MULTI_AGENT_HITL_DELIVER", "1")
    # Import after env — hitl_deliver_enabled reads env at call time
    from lumen.engine.services.multi_agent.langgraph_pipeline import hitl_deliver_enabled
    assert hitl_deliver_enabled() is True
    src = Path("lumen/engine/services/multi_agent/langgraph_pipeline.py").read_text(encoding="utf-8")
    assert "if hitl_deliver_enabled():" in src
    assert 'return "human_deliver_gate"' in src


def test_pipeline_registers_deliver_tool():
    src = Path("lumen/engine/services/multi_agent/langgraph_pipeline.py").read_text(encoding="utf-8")
    assert "langgraph_deliver_approve" in src
    assert "approve_deliver" in src


def test_bridge_knows_deliver_approve():
    src = Path("lumen/bot/multi_agent_bridge.py").read_text(encoding="utf-8")
    assert "langgraph_deliver_approve" in src
    assert "awaiting_deliver_approval" in src
