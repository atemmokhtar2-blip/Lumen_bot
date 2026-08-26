"""Phase B — durable journal, resume, backpressure, workflow engine selection."""
from __future__ import annotations

import os
from pathlib import Path

import pytest


def test_journal_write_and_resume_lookup(tmp_path, monkeypatch):
    monkeypatch.setenv("TBE_WORKFLOW_JOURNAL_DIR", str(tmp_path / "journal"))
    from lumen.engine.services.multi_agent.durable_workflow import (
        DurableWorkflowJournal,
        JournalEntry,
        get_journal,
        next_step_after,
    )

    # reset singleton if any
    import lumen.engine.services.multi_agent.durable_workflow as dw
    dw._JOURNAL = None  # type: ignore

    j = get_journal()
    entry = JournalEntry(
        workflow_id="wf-test-1",
        state_id="st-1",
        step="builder",
        status="running",
        user_id=9,
        description="phase b",
        attempts=1,
    )
    j.write(entry)
    loaded = j.get_by_state("st-1")
    assert loaded is not None
    assert loaded.step == "builder"
    assert loaded.workflow_id == "wf-test-1"
    assert next_step_after("architect") in {"builder", "critic", "deliver", "done"}


def test_memory_workflow_engine_checkpoint():
    from lumen.engine.services.multi_agent.workflow_engine import MemoryWorkflowEngine

    eng = MemoryWorkflowEngine()
    wid = eng.start("state-a", step="start", payload={"x": 1})
    cp = eng.checkpoint(wid, state_id="state-a", step="architect", status="running", payload={"x": 2})
    assert cp.step == "architect"
    got = eng.get_checkpoint(wid)
    assert got is not None
    assert got.state_id == "state-a"
    r = eng.resume(wid)
    assert r is not None


def test_get_workflow_engine_memory_default(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("JOB_REDIS_URL", raising=False)
    monkeypatch.setenv("TBE_WORKFLOW_ENGINE", "memory")
    import lumen.engine.services.multi_agent.workflow_engine as we
    we._ENGINE = None
    eng = we.get_workflow_engine()
    assert type(eng).__name__ == "MemoryWorkflowEngine"


def test_temporal_engine_requires_package_or_runs(monkeypatch):
    monkeypatch.setenv("TBE_WORKFLOW_ENGINE", "temporal")
    import lumen.engine.services.multi_agent.workflow_engine as we
    we._ENGINE = None
    try:
        import temporalio  # noqa: F401
        has = True
    except ImportError:
        has = False
    if not has:
        eng = we.get_workflow_engine()
        # falls back to memory when temporalio missing
        assert type(eng).__name__ in {"MemoryWorkflowEngine", "TemporalWorkflowEngine"}
    else:
        eng = we.get_workflow_engine()
        assert type(eng).__name__ == "TemporalWorkflowEngine"


def test_worker_pool_backpressure(monkeypatch):
    monkeypatch.setenv("MULTI_AGENT_WORKER_POOL", "1")
    monkeypatch.setenv("MULTI_AGENT_QUEUE_LIMIT", "1")
    import lumen.engine.services.multi_agent.worker_pool as wp
    wp._POOL = None
    pool = wp.get_worker_pool()
    import time

    def slow():
        time.sleep(0.3)
        return 1

    f1 = pool.submit(slow)
    # second may be queued or rejected depending on timing
    f2 = pool.submit(slow)
    stats = pool.stats()
    assert stats["max_workers"] == 1
    assert "queue_limit" in stats
    if f1:
        f1.result(timeout=2)


def test_orchestration_slot_backpressure(monkeypatch):
    monkeypatch.setenv("MULTI_AGENT_MAX_CONCURRENT", "1")
    monkeypatch.setenv("MULTI_AGENT_MAX_PER_USER", "1")
    monkeypatch.setenv("MULTI_AGENT_SLOT_TIMEOUT_SEC", "0.2")
    from lumen.engine.services.multi_agent.concurrency import orchestration_slot
    import threading

    held = threading.Event()
    release = threading.Event()

    def holder():
        with orchestration_slot(user_id=42) as got:
            assert got is True
            held.set()
            release.wait(2)

    t = threading.Thread(target=holder)
    t.start()
    assert held.wait(1)
    with orchestration_slot(timeout=0.15, user_id=42) as got2:
        assert got2 is False
    release.set()
    t.join(timeout=2)


def test_temporal_defs_importable_without_temporalio():
    from lumen.engine.services.multi_agent import temporal_defs as td
    # should not crash
    assert hasattr(td, "workflow_classes")
    assert hasattr(td, "activity_fns")


def test_orchestrator_checkpoint_starts_workflow_engine(tmp_path, monkeypatch):
    monkeypatch.setenv("TBE_WORKFLOW_ENGINE", "memory")
    monkeypatch.setenv("TBE_WORKFLOW_JOURNAL_DIR", str(tmp_path / "j"))
    import lumen.engine.services.multi_agent.workflow_engine as we
    import lumen.engine.services.multi_agent.durable_workflow as dw
    we._ENGINE = None
    dw._JOURNAL = None
    from lumen.engine.services.multi_agent.orchestrator import Orchestrator
    from lumen.engine.services.multi_agent.state import AgentState, AgentStatus
    from lumen.engine.services.multi_agent.blackboard import MemoryBlackboard

    board = MemoryBlackboard()
    orch = Orchestrator(board=board)
    st = AgentState(state_id="cp-1", user_id=1, user_text="hi")
    st.status = AgentStatus.BUILDING.value
    board.put(st)
    orch._wf_checkpoint(st, "architect")
    assert st.extensions.get("workflow_id")
    assert st.extensions.get("workflow_engine") == "MemoryWorkflowEngine"
    eng = we.get_workflow_engine()
    cp = eng.get_checkpoint(st.extensions["workflow_id"])
    assert cp is not None
    assert cp.step == "architect"


def test_rate_limit_pause_marks_needs_resume(tmp_path, monkeypatch):
    monkeypatch.setenv("TBE_WORKFLOW_ENGINE", "memory")
    monkeypatch.setenv("TBE_WORKFLOW_JOURNAL_DIR", str(tmp_path / "j2"))
    import lumen.engine.services.multi_agent.workflow_engine as we
    import lumen.engine.services.multi_agent.durable_workflow as dw
    we._ENGINE = None
    dw._JOURNAL = None
    from lumen.engine.services.multi_agent.orchestrator import Orchestrator
    from lumen.engine.services.multi_agent.state import AgentState
    from lumen.engine.services.multi_agent.blackboard import MemoryBlackboard

    board = MemoryBlackboard()
    orch = Orchestrator(board=board)
    st = AgentState(state_id="rl-1", user_id=2, user_text="bot")
    st.build_errors = ["gemini_http_429:rate limit exceeded"]
    assert orch._rate_limit_errors(st) is True
    st2 = orch._pause_for_rate_limit(st)
    assert st2.extensions.get("needs_resume") is True
    assert st2.extensions.get("paused_reason") == "rate_limit_429"
    from lumen.engine.services.multi_agent.durable_workflow import get_journal
    entry = get_journal().get_by_state("rl-1")
    assert entry is not None
    assert entry.step == "paused_429"
