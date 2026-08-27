"""Real runtime: reject stays FAILED; worker cannot lie about acceptance."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("langgraph")

from lumen.engine.services.multi_agent.state import AgentState, AgentStatus
import lumen.engine.services.multi_agent.langgraph_pipeline as lp
import lumen.engine.services.multi_agent.coding_agent as ca


def _setup(tmp_path, monkeypatch, *, hitl_plan="0", hitl_del="0"):
    monkeypatch.setenv("LANGGRAPH_CHECKPOINT_PATH", str(tmp_path / "cp.sqlite"))
    monkeypatch.setenv("MULTI_AGENT_LANGGRAPH_HITL", hitl_plan)
    monkeypatch.setenv("MULTI_AGENT_HITL_DELIVER", hitl_del)
    monkeypatch.setenv("MULTI_AGENT_PARALLEL", "0")
    lp._SHARED_CHECKPOINTER = None


def test_reject_hitl_status_is_failed_not_delivered(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, hitl_plan="1")
    def fake(**kw):
        return {"ok": True, "path": kw["work_dir"], "files": [], "files_written": [], "steps": 0, "errors": []}
    monkeypatch.setattr(ca, "run_coding_session", fake)
    work = tmp_path / "w"
    work.mkdir()
    st = AgentState(user_id=1, user_text="telegram bot")
    st.extensions = {"work_dir": str(work)}
    out = lp.run_langgraph_pipeline(st, context={"work_dir": str(work)}, thread_id="rej-rt")
    assert (out.extensions or {}).get("langgraph_interrupt")
    out2 = lp.resume_langgraph_hitl(out, "rejected", context={"work_dir": str(work)}, thread_id="rej-rt")
    status = str(out2.status).upper()
    assert status == "FAILED", f"reject must stay FAILED, got {status}"
    assert status != "DELIVERED"


def test_worker_cannot_lie_acceptance_report(tmp_path, monkeypatch):
    """Worker returns acceptance_report ok=True but writes broken Python — must not DONE."""
    _setup(tmp_path, monkeypatch, hitl_plan="0")
    def liar(**kw):
        work = Path(kw["work_dir"])
        work.mkdir(parents=True, exist_ok=True)
        (work / "main.py").write_text("def broken(\n", encoding="utf-8")
        return {
            "ok": True,
            "path": str(work),
            "files": ["main.py"],
            "files_written": ["main.py"],
            "steps": 1,
            "errors": [],
            "acceptance_report": {"ok": True},  # intentional lie
        }
    monkeypatch.setattr(ca, "run_coding_session", liar)
    work = tmp_path / "w"
    st = AgentState(user_id=1, user_text="telegram bot with /start")
    st.extensions = {"work_dir": str(work)}
    out = lp.run_langgraph_pipeline(st, context={"work_dir": str(work)}, thread_id="lie-rt")
    tt = (out.extensions or {}).get("task_tree") or {}
    nodes = tt.get("nodes") if isinstance(tt, dict) else {}
    # scaffold or first worker task must not be cleanly DONE with broken syntax
    worker_statuses = [
        v.get("status")
        for k, v in (nodes or {}).items()
        if isinstance(v, dict) and k not in {"root", tt.get("root_id")}
    ]
    # At least one failed OR qa not passed OR status FAILED
    assert (
        any(s == "failed" for s in worker_statuses)
        or out.qa_passed is False
        or str(out.status).upper() == "FAILED"
    ), f"liar worker must not fully succeed: status={out.status} nodes={worker_statuses}"


def test_deliver_agent_keeps_failed():
    from lumen.engine.services.multi_agent.roles.deliver import DeliverAgent
    st = AgentState(user_id=1, user_text="x", status=AgentStatus.FAILED.value)
    st.qa_passed = False
    st.build_errors = ["x"]
    out = DeliverAgent().run(st)
    assert str(out.status).upper() == "FAILED"
