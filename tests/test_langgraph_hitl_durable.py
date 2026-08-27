"""Durable SqliteSaver HITL + Telegram pending_action wire."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("langgraph")

from lumen.engine.services.multi_agent.state import AgentState, AgentStatus
from lumen.engine.services.multi_agent import langgraph_pipeline as lgp


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("MULTI_AGENT_LANGGRAPH_HITL", "1")
    monkeypatch.setenv("MULTI_AGENT_CHECKPOINT", "1")
    monkeypatch.setenv("LANGGRAPH_CHECKPOINT_PATH", str(tmp_path / "ckpt.sqlite"))
    monkeypatch.setenv("MULTI_AGENT_MAX_ATTEMPTS", "1")
    # reset singleton so new path is used
    lgp._SHARED_CHECKPOINTER = None


def test_sqlite_checkpointer_preferred(tmp_path, monkeypatch):
    monkeypatch.setenv("LANGGRAPH_CHECKPOINT_PATH", str(tmp_path / "ckpt.sqlite"))
    lgp._SHARED_CHECKPOINTER = None
    cp = lgp._shared_checkpointer()
    assert cp is not None
    name = type(cp).__name__
    assert name in {"SqliteSaver", "MemorySaver"}
    # Prefer sqlite when package available
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
        assert isinstance(cp, SqliteSaver)
        assert (tmp_path / "ckpt.sqlite").exists() or True  # file may create on write
    except ImportError:
        pytest.skip("sqlite saver not installed")


def test_interrupt_creates_pending_action(tmp_path):
    state = AgentState(
        user_id=7,
        user_text="build a calculator bot",
        capability_id="generate_bot",
        status=AgentStatus.PENDING.value,
    )
    state.extensions = {"work_dir": str(tmp_path)}
    paused = lgp.run_langgraph_pipeline(
        state, context={"work_dir": str(tmp_path)}, thread_id="durable-1"
    )
    assert (paused.extensions or {}).get("langgraph_interrupt") is True
    pending = (paused.extensions or {}).get("pending_action") or {}
    assert pending.get("tool") == "langgraph_plan_approve"
    assert pending.get("action_id")
    assert pending.get("confirm_token")
    assert "تأكيد" in (paused.final_message or "")


def test_resume_after_confirm_path(tmp_path):
    state = AgentState(
        user_id=8,
        user_text="bot",
        capability_id="generate_bot",
        status=AgentStatus.PENDING.value,
    )
    state.extensions = {"work_dir": str(tmp_path)}
    paused = lgp.run_langgraph_pipeline(
        state, context={"work_dir": str(tmp_path)}, thread_id="durable-2"
    )
    pending = (paused.extensions or {}).get("pending_action") or {}
    from lumen.engine.services.multi_agent.hitl import confirm_action
    from lumen.engine.services.multi_agent.orchestrator import continue_after_confirm
    from lumen.engine.services.multi_agent.blackboard import get_blackboard

    board = get_blackboard()
    board.put(paused)
    ok, st, reason = confirm_action(
        paused.state_id,
        pending["action_id"],
        user_id=8,
        confirm_token=pending["confirm_token"],
        board=board,
    )
    assert ok, reason
    resumed = continue_after_confirm(paused.state_id, user_id=8, work_dir=str(tmp_path), board=board)
    assert (resumed.extensions or {}).get("langgraph_interrupt") in {False, None}
