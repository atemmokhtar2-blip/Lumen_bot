"""Owner button confirm must not fail on stale session token."""
from __future__ import annotations

import os
os.environ.setdefault("ENVIRONMENT", "test")

from lumen.engine.services.multi_agent.hitl import request_confirmation, confirm_action
from lumen.engine.services.multi_agent.state import AgentState, AgentStatus
from lumen.engine.services.multi_agent.blackboard import get_blackboard


def test_owner_confirm_with_stale_token():
    board = get_blackboard()
    state = AgentState(user_id=42, status=AgentStatus.PLANNING.value)
    board.put(state)
    pending = request_confirmation(
        state,
        tool="langgraph_plan_approve",
        params={"plan": "x"},
        reason="test",
    )
    assert pending is not None
    action_id = pending.action_id
    real = pending.confirm_token
    assert real
    ok, st, reason = confirm_action(
        state.state_id, action_id, user_id=42, confirm_token="deadbeef_stale_token_xxx"
    )
    assert ok is True, f"reason={reason}"
