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
    # langgraph_pipeline is a package — gate logic lives in graph_builder.py
    src = Path("lumen/engine/services/multi_agent/langgraph_pipeline/graph_builder.py").read_text(encoding="utf-8")
    assert "if hitl_deliver_enabled():" in src
    assert 'return "human_deliver_gate"' in src


def test_pipeline_registers_deliver_tool():
    # langgraph_pipeline is a package. The deliver gate node type is registered
    # in graph_builder.py ("approve_deliver") and the resume tool name is mapped
    # in runner.py ("langgraph_deliver_approve").
    gb = Path("lumen/engine/services/multi_agent/langgraph_pipeline/graph_builder.py").read_text(encoding="utf-8")
    runner = Path("lumen/engine/services/multi_agent/langgraph_pipeline/runner.py").read_text(encoding="utf-8")
    assert "langgraph_deliver_approve" in runner
    assert "approve_deliver" in gb


def test_bridge_knows_deliver_approve():
    src = Path("lumen/bot/multi_agent_bridge.py").read_text(encoding="utf-8")
    assert "langgraph_deliver_approve" in src
    assert "awaiting_deliver_approval" in src
