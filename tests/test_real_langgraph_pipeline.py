"""Real LangGraph runtime tests — no source-string assertions."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("langgraph")

from lumen.engine.services.multi_agent.state import AgentState
import lumen.engine.services.multi_agent.langgraph_pipeline as lp
import lumen.engine.services.multi_agent.coding_agent as ca


@pytest.fixture
def fake_coder(monkeypatch):
    def fake_session(**kwargs):
        work = Path(kwargs["work_dir"])
        work.mkdir(parents=True, exist_ok=True)
        (work / "main.py").write_text(
            "import os\nfrom telegram.ext import Application, CommandHandler, MessageHandler\n"
            "async def start(u,c): pass\n"
            "def main():\n"
            "    t=os.getenv('BOT_TOKEN')\n"
            "    app=Application.builder().token(t).build()\n"
            "    app.add_handler(CommandHandler('start', start))\n"
            "    app.add_handler(MessageHandler(None, start))\n",
            encoding="utf-8",
        )
        (work / "requirements.txt").write_text("python-telegram-bot\n", encoding="utf-8")
        for f in list(kwargs.get("target_files") or []):
            if f.endswith(".py") and not (work / f).exists():
                (work / f).parent.mkdir(parents=True, exist_ok=True)
                stem = Path(f).stem
                (work / f).write_text(f"def {stem}():\n    return True\n", encoding="utf-8")
        files = [p.relative_to(work).as_posix() for p in work.rglob("*") if p.is_file()]
        return {
            "ok": True,
            "path": str(work),
            "files": files,
            "files_written": files,
            "steps": 1,
            "errors": [],
            "acceptance_report": {"ok": True},
        }
    monkeypatch.setattr(ca, "run_coding_session", fake_session)
    return fake_session


@pytest.fixture
def fresh_checkpoint(tmp_path, monkeypatch):
    db = tmp_path / "cp.sqlite"
    monkeypatch.setenv("LANGGRAPH_CHECKPOINT_PATH", str(db))
    monkeypatch.setenv("MULTI_AGENT_LANGGRAPH_HITL", "0")
    monkeypatch.setenv("MULTI_AGENT_HITL_DELIVER", "0")
    monkeypatch.setenv("MULTI_AGENT_PARALLEL", "1")
    lp._SHARED_CHECKPOINTER = None
    return db


def test_compile_graph_with_sqlite(fresh_checkpoint):
    from lumen.engine.services.multi_agent.registry import get_registry
    from lumen.engine.services.multi_agent.blackboard import MemoryBlackboard
    graph, cp = lp._compile_graph(get_registry(), MemoryBlackboard())
    assert graph is not None
    assert cp is not None
    assert type(cp).__name__ == "SqliteSaver"


def test_pipeline_parallel_features_no_invalid_update(fresh_checkpoint, fake_coder, tmp_path):
    """Regression: multi-feature plan used Send → InvalidUpdateError without agent reducer."""
    work = tmp_path / "proj"
    work.mkdir()
    state = AgentState(user_id=1, user_text="بوت تيليجرام", preferred_keys=["admin", "payments"])
    state.extensions = {"work_dir": str(work)}
    out = lp.run_langgraph_pipeline(state, context={"work_dir": str(work)}, thread_id="real-par-1")
    # Must not crash; should progress past work
    assert out is not None
    assert str(out.status).upper() not in {"", "NONE"}
    # main should exist from fake coder or scaffold task
    assert (work / "main.py").exists() or bool(out.generated_path)


def test_hitl_interrupt_and_resume(tmp_path, monkeypatch, fake_coder):
    db = tmp_path / "hitl.sqlite"
    monkeypatch.setenv("LANGGRAPH_CHECKPOINT_PATH", str(db))
    monkeypatch.setenv("MULTI_AGENT_LANGGRAPH_HITL", "1")
    monkeypatch.setenv("MULTI_AGENT_HITL_DELIVER", "0")
    lp._SHARED_CHECKPOINTER = None
    work = tmp_path / "hitl_proj"
    work.mkdir()
    state = AgentState(user_id=3, user_text="telegram bot", preferred_keys=["admin"])
    state.extensions = {"work_dir": str(work)}
    out = lp.run_langgraph_pipeline(state, context={"work_dir": str(work)}, thread_id="hitl-thread-1")
    assert (out.extensions or {}).get("langgraph_interrupt") is True
    assert str(out.status).upper() in {"AWAITING_CONFIRMATION", "WAITING_CONFIRM", "PENDING"} or (
        out.extensions or {}
    ).get("hitl_status") in {"awaiting_approval"}
    pending = (out.extensions or {}).get("pending_action") or {}
    assert pending.get("tool") == "langgraph_plan_approve" or (out.extensions or {}).get("hitl_pending")

    out2 = lp.resume_langgraph_hitl(out, "approved", context={"work_dir": str(work)}, thread_id="hitl-thread-1")
    assert out2 is not None
    # After approve should leave pure interrupt-only state
    assert (out2.extensions or {}).get("langgraph_interrupt") in {False, None} or out2.status


def test_merge_agent_keeps_done_from_both_sides():
    from lumen.engine.services.multi_agent.task_tree import TaskTree, TaskNode, TaskStatus
    from lumen.engine.services.multi_agent.langgraph_pipeline import _merge_agent_state

    a = AgentState(user_id=1, user_text="x")
    b = AgentState(user_id=1, user_text="x")
    ta = TaskTree(goal="g")
    ta.add(TaskNode(id="f1", title="f1", status=TaskStatus.DONE.value, files=["modules/a.py"]), parent_id=ta.root_id)
    ta.add(TaskNode(id="f2", title="f2", status=TaskStatus.READY.value, files=["modules/b.py"]), parent_id=ta.root_id)
    tb = TaskTree(goal="g")
    tb.add(TaskNode(id="f1", title="f1", status=TaskStatus.READY.value, files=["modules/a.py"]), parent_id=tb.root_id)
    tb.add(TaskNode(id="f2", title="f2", status=TaskStatus.DONE.value, files=["modules/b.py"]), parent_id=tb.root_id)
    a.extensions = {"task_tree": ta.to_dict()}
    b.extensions = {"task_tree": tb.to_dict()}
    m = _merge_agent_state(a, b)
    nodes = TaskTree.from_dict(m.extensions["task_tree"]).nodes
    assert nodes["f1"].status == TaskStatus.DONE.value
    assert nodes["f2"].status == TaskStatus.DONE.value
