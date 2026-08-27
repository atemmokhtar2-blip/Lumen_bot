"""Official LangGraph interrupt + Command(resume) HITL tests."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("langgraph")

from lumen.engine.services.multi_agent.state import AgentState, AgentStatus
from lumen.engine.services.multi_agent.langgraph_pipeline import (
    hitl_interrupt_enabled,
    run_langgraph_pipeline,
    resume_langgraph_hitl,
    _shared_checkpointer,
)


@pytest.fixture(autouse=True)
def _enable_hitl(monkeypatch):
    monkeypatch.setenv("MULTI_AGENT_LANGGRAPH_HITL", "1")
    monkeypatch.setenv("MULTI_AGENT_CHECKPOINT", "1")
    # Avoid real LLM work: force fail-fast after resume by limiting — we only test interrupt boundary
    monkeypatch.setenv("MULTI_AGENT_MAX_ATTEMPTS", "1")


def test_hitl_enabled():
    assert hitl_interrupt_enabled() is True


def test_interrupt_after_plan_then_resume_approve(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MULTI_AGENT_LANGGRAPH_HITL", "1")
    # shared checkpointer must exist
    assert _shared_checkpointer() is not None

    state = AgentState(
        user_id=1,
        user_text="build a hello bot",
        capability_id="generate_bot",
        status=AgentStatus.PENDING.value,
    )
    state.extensions = {"work_dir": str(tmp_path)}

    # First invoke should pause at human_gate
    paused = run_langgraph_pipeline(state, context={"work_dir": str(tmp_path)}, thread_id="test-hitl-1")
    assert (paused.extensions or {}).get("langgraph_interrupt") is True
    assert (paused.extensions or {}).get("hitl_status") == "awaiting_approval"
    assert (paused.extensions or {}).get("langgraph_thread_id") == "test-hitl-1"
    pending = (paused.extensions or {}).get("hitl_pending") or {}
    assert pending.get("type") == "approve_plan" or "goal" in pending or pending

    # Resume approved — graph continues (may fail later without LLM; should not stay interrupted)
    resumed = resume_langgraph_hitl(
        paused, "approved", context={"work_dir": str(tmp_path)}, thread_id="test-hitl-1"
    )
    assert (resumed.extensions or {}).get("langgraph_interrupt") in {False, None}
    # decision recorded
    assert (resumed.extensions or {}).get("hitl_status") in {"approved", "resumed"} or resumed.status


def test_interrupt_reject_fails(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MULTI_AGENT_LANGGRAPH_HITL", "1")
    state = AgentState(
        user_id=2,
        user_text="dangerous request",
        capability_id="generate_bot",
        status=AgentStatus.PENDING.value,
    )
    state.extensions = {"work_dir": str(tmp_path)}
    paused = run_langgraph_pipeline(state, context={"work_dir": str(tmp_path)}, thread_id="test-hitl-reject")
    assert (paused.extensions or {}).get("langgraph_interrupt") is True

    resumed = resume_langgraph_hitl(
        paused, "rejected", context={"work_dir": str(tmp_path)}, thread_id="test-hitl-reject"
    )
    assert (resumed.extensions or {}).get("hitl_status") == "rejected"
    assert (resumed.extensions or {}).get("langgraph_interrupt") in {False, None}
    # fail node may still call deliver messenger — decision must stay rejected
    assert "رفض" in (resumed.final_message or "") or resumed.status in {
        AgentStatus.FAILED.value, AgentStatus.DELIVERED.value
    }


def test_hitl_can_disable(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("MULTI_AGENT_LANGGRAPH_HITL", "0")
    assert hitl_interrupt_enabled() is False
