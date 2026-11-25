"""HITL approval tokens must be exact and execution grants bind full params."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("ENVIRONMENT", "test")

from lumen.engine.services.multi_agent.blackboard import MemoryBlackboard
from lumen.engine.services.multi_agent.hitl import (
    _params_digest,
    confirm_action,
    consume_execute_grant,
    request_confirmation,
)
from lumen.engine.services.multi_agent.state import AgentState, AgentStatus


def test_wrong_token_is_rejected_but_exact_owner_token_succeeds(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    board = MemoryBlackboard()
    state = AgentState(user_id=42, status=AgentStatus.PLANNING.value)
    board.put(state)
    pending = request_confirmation(
        state,
        tool="langgraph_plan_approve",
        params={"plan": "x"},
        reason="test",
        board=board,
    )

    ok, _, reason = confirm_action(
        state.state_id,
        pending.action_id,
        user_id=42,
        confirm_token="deadbeef_stale_token_xxx",
        board=board,
    )
    assert ok is False
    assert reason == "bad_token"

    ok, confirmed, reason = confirm_action(
        state.state_id,
        pending.action_id,
        user_id=42,
        confirm_token=pending.confirm_token,
        board=board,
    )
    assert ok is True, f"reason={reason}"
    assert confirmed is not None
    assert confirmed.extensions["hitl_execute_grant"]["single_use"] is True


def test_execution_grant_digest_covers_entire_parameter_value():
    prefix = "x" * 200
    original = {"command": prefix + "safe"}
    modified = {"command": prefix + "dangerous"}
    assert _params_digest(original) != _params_digest(modified)


def test_execution_grant_digest_is_key_order_independent():
    assert _params_digest({"a": 1, "b": {"x": 2, "y": 3}}) == _params_digest(
        {"b": {"y": 3, "x": 2}, "a": 1}
    )


def test_production_hitl_requires_configured_hmac_secret(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("MULTI_AGENT_HITL_SECRET", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    from lumen.engine.services.multi_agent.hitl import _hmac_secret

    with pytest.raises(RuntimeError, match="required for production approvals"):
        _hmac_secret()



def test_execution_grant_rejects_missing_or_mismatched_user():
    state = AgentState(user_id=0, status=AgentStatus.PLANNING.value)
    params = {"target": "tenant-resource"}
    state.extensions["hitl_execute_grant"] = {
        "tool": "host_start",
        "user_id": 42,
        "params_digest": _params_digest(params),
        "single_use": True,
    }
    assert not consume_execute_grant(
        state, "host_start", user_id=0, params=params
    )
    assert "hitl_execute_grant" in state.extensions

    state.user_id = 42
    assert consume_execute_grant(
        state, "host_start", user_id=42, params=params
    )
    assert "hitl_execute_grant" not in state.extensions


def test_execution_grant_rejects_zero_owner():
    state = AgentState(user_id=42, status=AgentStatus.PLANNING.value)
    params = {"target": "tenant-resource"}
    state.extensions["hitl_execute_grant"] = {
        "tool": "host_start",
        "user_id": 0,
        "params_digest": _params_digest(params),
        "single_use": True,
    }
    assert not consume_execute_grant(
        state, "host_start", user_id=42, params=params
    )
    assert "hitl_execute_grant" in state.extensions
