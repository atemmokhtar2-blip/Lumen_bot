"""Production PostgreSQL durability tests.

These tests run against the dedicated PostgreSQL service in CI. They deliberately
use a spawned second process: an in-process cache cannot make these tests pass.
"""
from __future__ import annotations

import multiprocessing
import os
import uuid
from typing import TypedDict

import pytest

POSTGRES_URL = (os.getenv("TEST_POSTGRES_URL") or os.getenv("DATABASE_URL") or "").strip()
if not POSTGRES_URL:
    pytest.skip("PostgreSQL durability tests require TEST_POSTGRES_URL", allow_module_level=True)


class ApprovalState(TypedDict, total=False):
    approved: str
    agent: object
    agent_type: str
    event_type: str


def _approval_node(state: ApprovalState) -> dict:
    from langgraph.types import interrupt

    decision = interrupt({"kind": "approval", "message": "Approve this task?"})
    agent = state.get("agent")
    return {
        "approved": str(decision),
        "agent_type": type(agent).__name__,
        "event_type": type(agent.events[0]).__name__ if getattr(agent, "events", None) else "",
    }


def _approval_graph(checkpointer):
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(ApprovalState)
    graph.add_node("approval", _approval_node)
    graph.add_edge(START, "approval")
    graph.add_edge("approval", END)
    return graph.compile(checkpointer=checkpointer)


def _resume_in_child(thread_id: str, result_queue) -> None:
    os.environ["ENVIRONMENT"] = "production"
    try:
        from langgraph.types import Command

        from lumen.engine.services.multi_agent.langgraph_pipeline.flags import (
            _shared_checkpointer,
            close_shared_checkpointer,
        )

        app = _approval_graph(_shared_checkpointer())
        result = app.invoke(
            Command(resume="approved"),
            config={"configurable": {"thread_id": thread_id}},
        )
        result_queue.put(("ok", result.get("approved"), result.get("agent_type"), result.get("event_type")))
        close_shared_checkpointer()
    except Exception as exc:
        result_queue.put(("error", type(exc).__name__, str(exc)[:500]))


def _read_blackboard_in_child(state_id: str, result_queue) -> None:
    os.environ["ENVIRONMENT"] = "production"
    try:
        from lumen.engine.services.multi_agent.blackboard import PostgresBlackboardStore
        from lumen.platform.postgres_pool import close_postgres_pool

        state = PostgresBlackboardStore().get(state_id)
        result_queue.put(
            ("ok", state.state_id if state else "", state.user_id if state else -1)
        )
        close_postgres_pool()
    except Exception as exc:
        result_queue.put(("error", type(exc).__name__, str(exc)[:500]))


@pytest.fixture(autouse=True)
def _production_postgres(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", POSTGRES_URL)
    monkeypatch.setenv("MULTI_AGENT_CHECKPOINT", "1")
    monkeypatch.setenv("MULTI_AGENT_LANGGRAPH_HITL", "1")

    from lumen.engine.services.multi_agent import blackboard
    from lumen.engine.services.multi_agent.langgraph_pipeline import flags
    from lumen.platform import postgres_pool

    flags._SHARED_CHECKPOINTER = None
    postgres_pool._POOL = None
    blackboard._default_board = None
    yield
    flags.close_shared_checkpointer()
    blackboard._default_board = None


def test_langgraph_checkpoint_resumes_in_a_separate_process():
    from lumen.engine.services.multi_agent.langgraph_pipeline.flags import _shared_checkpointer
    from lumen.engine.services.multi_agent.state import AgentState

    thread_id = f"lumen-cross-process-{uuid.uuid4().hex}"
    app = _approval_graph(_shared_checkpointer())
    agent = AgentState(user_id=901, user_text="cross-process checkpoint")
    agent.record("test", "checkpoint-created")

    interrupted = app.invoke(
        {"agent": agent},
        config={"configurable": {"thread_id": thread_id}},
    )
    assert interrupted.get("__interrupt__"), "first process must persist a real interrupt"

    ctx = multiprocessing.get_context("spawn")
    result_queue = ctx.Queue()
    child = ctx.Process(target=_resume_in_child, args=(thread_id, result_queue))
    child.start()
    child.join(timeout=45)
    if child.is_alive():
        child.terminate()
        child.join(timeout=5)
        pytest.fail("checkpoint resume process timed out")
    assert child.exitcode == 0
    result = result_queue.get(timeout=5)
    assert result == ("ok", "approved", "AgentState", "AgentEvent")

    _shared_checkpointer().delete_thread({"configurable": {"thread_id": thread_id}})


def test_application_blackboard_is_shared_between_processes():
    from lumen.engine.services.multi_agent.blackboard import get_blackboard, PostgresBlackboardStore
    from lumen.engine.services.multi_agent.state import AgentState

    board = get_blackboard()
    assert isinstance(board, PostgresBlackboardStore)
    state = AgentState(user_id=902, user_text="shared blackboard state")
    board.put(state)

    ctx = multiprocessing.get_context("spawn")
    result_queue = ctx.Queue()
    child = ctx.Process(target=_read_blackboard_in_child, args=(state.state_id, result_queue))
    child.start()
    child.join(timeout=30)
    if child.is_alive():
        child.terminate()
        child.join(timeout=5)
        pytest.fail("blackboard read process timed out")
    assert child.exitcode == 0
    assert result_queue.get(timeout=5) == ("ok", state.state_id, 902)

    with board._pool.connection(timeout=10) as conn:
        conn.execute("DELETE FROM lumen_agent_states WHERE state_id=%s", (state.state_id,))


def test_blackboard_rejects_cross_user_state_id_overwrite():
    from lumen.engine.services.multi_agent.blackboard import get_blackboard
    from lumen.engine.services.multi_agent.state import AgentState

    board = get_blackboard()
    original = AgentState(user_id=903, user_text="owned by user 903")
    board.put(original)

    forged = AgentState(
        state_id=original.state_id,
        user_id=904,
        user_text="attempted overwrite by another user",
    )
    with pytest.raises(PermissionError, match="agent_state_owner_mismatch"):
        board.put(forged)

    persisted = board.get(original.state_id)
    assert persisted is not None
    assert persisted.user_id == 903
    assert persisted.user_text == "owned by user 903"
    board.delete(original.state_id)


def test_postgres_blackboard_never_persists_raw_hitl_token():
    from lumen.engine.services.multi_agent.blackboard import get_blackboard
    from lumen.engine.services.multi_agent.hitl import (
        confirmation_token_for_state,
        request_confirmation,
    )
    from lumen.engine.services.multi_agent.state import AgentState

    board = get_blackboard()
    state = AgentState(user_id=905, user_text="approval token persistence test")
    pending = request_confirmation(
        state,
        tool="langgraph_plan_approve",
        params={"goal": "safe test"},
        reason="PostgreSQL token storage regression",
        board=board,
    )

    persisted = board.get(state.state_id)
    assert persisted is not None
    assert "confirm_token" not in persisted.extensions["pending_action"]
    assert pending.confirm_token not in (persisted.final_message or "")
    assert confirmation_token_for_state(persisted) == pending.confirm_token

    with board._pool.connection(timeout=10) as conn:
        row = conn.execute(
            "SELECT payload::text AS payload_text FROM lumen_agent_states WHERE state_id=%s",
            (state.state_id,),
        ).fetchone()
    assert row is not None
    assert pending.confirm_token not in row["payload_text"]
    board.delete(state.state_id)



def test_postgres_blackboard_scopes_same_numeric_user_to_distinct_principals():
    from lumen.engine.services.multi_agent.blackboard import get_blackboard
    from lumen.engine.services.multi_agent.state import AgentState

    board = get_blackboard()
    telegram = AgentState(
        user_id=906,
        principal_id="telegram:906",
        user_text="telegram private state",
    )
    tenant = AgentState(
        user_id=906,
        principal_id="tenant:acme",
        user_text="tenant private state",
    )
    board.put(telegram)
    board.put(tenant)

    assert board.latest_for_principal("telegram:906").state_id == telegram.state_id
    assert board.latest_for_principal("tenant:acme").state_id == tenant.state_id
    assert board.latest_for_user(906).state_id == telegram.state_id
    assert board.latest_for_principal("legacy:user:906") is None

    forged = AgentState(
        state_id=telegram.state_id,
        user_id=906,
        principal_id="tenant:attacker",
        user_text="cross-principal overwrite",
    )
    with pytest.raises(PermissionError, match="agent_state_owner_mismatch"):
        board.put(forged)

    assert board.get(telegram.state_id).user_text == "telegram private state"
    assert board.get(tenant.state_id).user_text == "tenant private state"
    board.delete(telegram.state_id)
    board.delete(tenant.state_id)



def test_postgres_host_registry_persists_tenant_principal_and_quarantines_legacy():
    from lumen.engine.services.hosting.pg_state_store import PgHostStateStore

    store = PgHostStateStore()
    tenant_id = "tenant:pg-isolation-test"
    store.upsert({
        "instance_id": "host-principal-test-tenant",
        "user_id": 906,
        "tenant_id": tenant_id,
        "principal_id": f"tenant:{tenant_id}",
        "project_path": "/tmp/tenant-project",
        "status": "running",
    })
    rows = [r for r in store.list_all() if r["instance_id"] == "host-principal-test-tenant"]
    assert len(rows) == 1
    assert rows[0]["tenant_id"] == tenant_id
    assert rows[0]["principal_id"] == f"tenant:{tenant_id}"
    store.delete("host-principal-test-tenant")

    store.upsert({
        "instance_id": "host-principal-test-legacy",
        "user_id": 906,
        "project_path": "/tmp/legacy-project",
        "status": "running",
    })
    rows = [r for r in store.list_all() if r["instance_id"] == "host-principal-test-legacy"]
    assert len(rows) == 1
    assert rows[0]["principal_id"] == "legacy:user:906"
    store.delete("host-principal-test-legacy")
