"""Deterministic local LangGraph HITL persistence tests (no external LLM provider)."""
from __future__ import annotations

from typing import TypedDict

import pytest

pytest.importorskip("langgraph")


class ApprovalState(TypedDict, total=False):
    decision: str


def _approval_node(_state: ApprovalState) -> dict:
    from langgraph.types import interrupt

    decision = interrupt({"type": "approve_plan", "message": "Approve test plan?"})
    return {"decision": str(decision)}


def _approval_graph(checkpointer):
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(ApprovalState)
    graph.add_node("approval", _approval_node)
    graph.add_edge(START, "approval")
    graph.add_edge("approval", END)
    return graph.compile(checkpointer=checkpointer)


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("MULTI_AGENT_LANGGRAPH_HITL", "1")
    monkeypatch.setenv("MULTI_AGENT_CHECKPOINT", "1")
    monkeypatch.setenv("LANGGRAPH_CHECKPOINT_PATH", str(tmp_path / "ckpt.sqlite"))
    monkeypatch.setenv("MULTI_AGENT_MAX_ATTEMPTS", "1")
    from lumen.engine.services.multi_agent.langgraph_pipeline import flags

    flags._SHARED_CHECKPOINTER = None
    yield
    flags.close_shared_checkpointer()


def test_sqlite_checkpointer_preferred(tmp_path, monkeypatch):
    monkeypatch.setenv("LANGGRAPH_CHECKPOINT_PATH", str(tmp_path / "ckpt.sqlite"))
    from lumen.engine.services.multi_agent.langgraph_pipeline.flags import _shared_checkpointer
    from langgraph.checkpoint.sqlite import SqliteSaver

    checkpointer = _shared_checkpointer()
    assert isinstance(checkpointer, SqliteSaver)
    assert (tmp_path / "ckpt.sqlite").parent.exists()


def test_interrupt_creates_pending_action_without_persisting_raw_token():
    from lumen.engine.services.multi_agent.blackboard import MemoryBlackboard
    from lumen.engine.services.multi_agent.hitl import (
        confirmation_token_for_state,
        request_confirmation,
    )
    from lumen.engine.services.multi_agent.state import AgentState

    state = AgentState(user_id=7, user_text="build a calculator bot")
    board = MemoryBlackboard()
    pending = request_confirmation(
        state,
        tool="langgraph_plan_approve",
        params={"goal": "calculator bot"},
        board=board,
    )
    persisted = board.get(state.state_id)
    assert persisted is not None
    stored = persisted.extensions["pending_action"]
    assert stored.get("tool") == "langgraph_plan_approve"
    assert stored.get("action_id") == pending.action_id
    assert "confirm_token" not in stored
    assert confirmation_token_for_state(persisted) == pending.confirm_token
    assert pending.confirm_token not in (persisted.final_message or "")


def test_langgraph_interrupt_resumes_with_same_local_checkpointer():
    from langgraph.types import Command

    from lumen.engine.services.multi_agent.langgraph_pipeline.flags import _shared_checkpointer

    thread_id = "local-hitl-resume-test"
    app = _approval_graph(_shared_checkpointer())
    config = {"configurable": {"thread_id": thread_id}}

    paused = app.invoke({}, config=config)
    assert paused.get("__interrupt__")

    resumed = app.invoke(Command(resume="approved"), config=config)
    assert resumed.get("decision") == "approved"
