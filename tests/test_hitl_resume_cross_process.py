"""Cross-process HITL resume: missing checkpoint must raise, not infinite-loop.

This is the ROOT-CAUSE regression test for the bug where a user confirms the plan
but generation never starts (infinite "تأكيد الخطة" loop).

Scenario: the initial generation runs in an RQ worker process using a
process-local MemorySaver. The confirm handler runs in the Telegram webhook
process, which has a DIFFERENT MemorySaver instance with no checkpoint for the
thread_id. Calling ``graph.invoke(Command(resume=...))`` then silently restarts
the graph from START, re-interrupts at the plan gate, and shows a NEW "confirm
the plan" prompt — forever, with no generation.

The fix: ``resume_langgraph_hitl`` detects the missing checkpoint + re-interrupt
and raises ``RuntimeError("checkpoint_missing_for_thread: ...")`` instead of
returning a new AWAITING_CONFIRMATION state.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("langgraph")

from lumen.engine.services.multi_agent.state import AgentState, AgentStatus
from lumen.engine.services.multi_agent import langgraph_pipeline as lgp
from lumen.engine.services.multi_agent.langgraph_pipeline.runner import (
    resume_langgraph_hitl,
)


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("MULTI_AGENT_LANGGRAPH_HITL", "1")
    monkeypatch.setenv("MULTI_AGENT_CHECKPOINT", "1")
    monkeypatch.setenv("LANGGRAPH_CHECKPOINT_PATH", str(tmp_path / "ckpt.sqlite"))
    monkeypatch.setenv("MULTI_AGENT_MAX_ATTEMPTS", "1")
    # reset singleton so each test gets a fresh, empty checkpointer.
    # We inject a fresh MemorySaver (process-local, empty) to SIMULATE the
    # cross-process scenario: the webhook process has a checkpointer that
    # knows nothing about the worker process's checkpoint for this thread.
    from langgraph.checkpoint.memory import MemorySaver
    lgp._SHARED_CHECKPOINTER = MemorySaver()


def _make_state(tmp_path, thread_id: str) -> AgentState:
    state = AgentState(
        user_id=42,
        user_text="build a telegram bot",
        capability_id="generate_bot",
        status=AgentStatus.PENDING.value,
    )
    state.extensions = {
        "work_dir": str(tmp_path),
        "langgraph_thread_id": thread_id,
        "langgraph_interrupt": True,
        "hitl_status": "awaiting_approval",
        "pending_action": {
            "tool": "langgraph_plan_approve",
            "action_id": "act-x-proc-1",
            "confirm_token": "tok-x-proc-1",
        },
    }
    return state


def test_resume_raises_when_checkpoint_missing(tmp_path):
    """Resume with a thread_id that was NEVER checkpointed must raise RuntimeError.

    This simulates the cross-process case: process A (worker) ran the initial
    generation and created a checkpoint in ITS MemorySaver; process B (webhook)
    calls resume with a fresh MemorySaver that knows nothing about that thread.
    """
    # Use a thread_id that no checkpoint exists for.
    state = _make_state(tmp_path, "ghost-thread-no-checkpoint")

    with pytest.raises(RuntimeError) as excinfo:
        resume_langgraph_hitl(state, "approved", context={"work_dir": str(tmp_path)})

    msg = str(excinfo.value)
    assert "checkpoint_missing_for_thread" in msg, (
        f"Expected checkpoint_missing_for_thread error, got: {msg}"
    )


def test_resume_no_infinite_loop_on_missing_checkpoint(tmp_path):
    """The old behaviour returned an AWAITING_CONFIRMATION state (re-interrupt),
    causing the bot to loop forever asking the user to confirm again.

    The fix must instead raise, so the caller can surface a clear error and stop.
    """
    state = _make_state(tmp_path, "ghost-thread-no-checkpoint-2")
    raised = False
    try:
        out = resume_langgraph_hitl(state, "approved", context={"work_dir": str(tmp_path)})
    except RuntimeError as exc:
        raised = True
        assert "checkpoint_missing_for_thread" in str(exc)
        # Critical: must NOT silently return a state that looks like a fresh
        # awaiting-approval prompt (which would loop forever).
    assert raised, (
        "resume_langgraph_hitl must RAISE on missing checkpoint, not return a "
        "new awaiting-approval state (that causes the infinite HITL loop)."
    )


def test_orchestrator_surfaces_failed_not_restarts(tmp_path):
    """At the orchestrator layer, an approved-resume that fails due to a missing
    checkpoint must end in FAILED with a clear Arabic message — NOT fall through
    to a full orch.run() restart (which would also loop).
    """
    from lumen.engine.services.multi_agent.orchestrator import (
        continue_after_confirm,
    )
    from lumen.engine.services.multi_agent.blackboard import get_blackboard
    from lumen.engine.services.multi_agent.hitl import (
        confirm_action,
        request_confirmation,
    )

    board = get_blackboard()
    state = _make_state(tmp_path, "ghost-thread-orch-1")
    # Create a properly-signed, non-expired pending action via the real API.
    pending = request_confirmation(
        state,
        tool="langgraph_plan_approve",
        params={"plan_summary": "build a telegram bot"},
        reason="تأكيد الخطة",
        board=board,
    )
    board.put(state)

    ok, st, reason = confirm_action(
        state.state_id,
        pending.action_id,
        user_id=42,
        confirm_token=pending.confirm_token,
        board=board,
    )
    assert ok, reason

    resumed = continue_after_confirm(
        state.state_id, user_id=42, work_dir=str(tmp_path), board=board
    )
    # Must NOT be an awaiting-approval state again (that would loop).
    ext = resumed.extensions or {}
    assert ext.get("langgraph_interrupt") is not True, (
        "continue_after_confirm must not return a fresh awaiting-approval state "
        "(that would cause the infinite loop the user reported)."
    )
    # Must surface a FAILED status with a clear message pointing at the root cause.
    assert str(resumed.status).upper() in {"FAILED", "FAILURE"}, (
        f"Expected FAILED status, got {resumed.status!r}"
    )
    msg = resumed.final_message or ""
    err = str(ext.get("hitl_resume_error", "") or "")
    assert "تعذّر" in msg or "HITL" in msg or "checkpoint" in err.lower(), (
        f"Expected a clear Arabic/English error message, got: {msg!r} / "
        f"hitl_resume_error={ext.get('hitl_resume_error')!r}"
    )
