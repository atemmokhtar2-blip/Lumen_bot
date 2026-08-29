"""End-to-end HITL confirm/reject wiring — must stay green."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("ENVIRONMENT", "dev")
os.environ.setdefault("MULTI_AGENT_BOARD", "memory")


@pytest.fixture()
def board():
    from lumen.engine.services.multi_agent.blackboard import MemoryBlackboard, set_blackboard
    from lumen.engine.services.multi_agent import blackboard as bb_mod

    mem = MemoryBlackboard()
    set_blackboard(mem)
    yield mem
    # reset singleton
    bb_mod._default_board = None


def _make_pending_state(user_id: int = 42, tool: str = "langgraph_plan_approve"):
    from lumen.engine.services.multi_agent.state import AgentState, AgentStatus
    from lumen.engine.services.multi_agent.hitl import request_confirmation
    from lumen.engine.services.multi_agent.blackboard import get_blackboard

    st = AgentState(user_id=user_id, user_text="بوت تيليجرام بسيط")
    st.status = AgentStatus.AWAITING_CONFIRMATION.value
    st.extensions["langgraph_interrupt"] = True
    st.extensions["hitl_status"] = "awaiting_approval"
    st.extensions["langgraph_thread_id"] = "thread-test-1"
    pending = request_confirmation(
        st,
        tool,
        params={"goal": "simple bot"},
        reason="test plan approve",
    )
    get_blackboard().put(st)
    return st, pending


def test_signed_hitl_callbacks_roundtrip():
    os.environ["CALLBACK_HMAC_SECRET"] = "test-hitl-hmac-secret-32chars!!"
    from lumen.bot.ui.keyboards import encode_callback, decode_callback
    from lumen.engine.services.ui_state.catalog import is_known_action

    assert is_known_action("hitl_confirm")
    assert is_known_action("hitl_reject")
    for action in ("hitl_confirm", "hitl_reject"):
        wire = encode_callback(action, "", user_id=42)
        assert wire.startswith("L2.")
        assert len(wire.encode()) <= 64
        assert decode_callback(wire, user_id=42) == (action, "")


def test_confirm_verb_only_with_user_data(board):
    from lumen.bot.multi_agent_bridge import try_handle_hitl_message

    st, pending = _make_pending_state(user_id=7)
    ud = {
        "multi_agent_state_id": st.state_id,
        "multi_agent_pending": {
            "action_id": pending.action_id,
            "state_id": st.state_id,
            "confirm_token": pending.confirm_token,
            "tool": "langgraph_plan_approve",
        },
    }
    handled, reply, _state = try_handle_hitl_message("تأكيد", user_id=7, user_data=ud)
    assert handled is True
    # confirm_action must succeed; continue may fail without full langgraph graph — still not bad_token
    assert "bad_token" not in reply
    assert "بيانات الموافقة ناقصة" not in reply
    assert "تعذر التأكيد: لا يوجد" not in reply
    # pending should be cleared after confirm attempt
    assert "multi_agent_pending" not in ud


def test_confirm_recovers_token_from_board_when_user_data_empty(board):
    from lumen.bot.multi_agent_bridge import try_handle_hitl_message

    st, pending = _make_pending_state(user_id=9)
    ud = {"multi_agent_state_id": st.state_id}  # no pending dict / no token
    handled, reply, _state = try_handle_hitl_message("تأكيد", user_id=9, user_data=ud)
    assert handled is True
    assert "بيانات الموافقة ناقصة" not in reply
    assert "bad_token" not in reply


def test_reject_verb_only(board):
    from lumen.bot.multi_agent_bridge import try_handle_hitl_message
    from lumen.engine.services.multi_agent.blackboard import get_blackboard

    st, pending = _make_pending_state(user_id=11)
    ud = {
        "multi_agent_state_id": st.state_id,
        "multi_agent_pending": {
            "action_id": pending.action_id,
            "state_id": st.state_id,
            "confirm_token": pending.confirm_token,
            "tool": "langgraph_plan_approve",
        },
    }
    handled, reply, _state = try_handle_hitl_message("رفض", user_id=11, user_data=ud)
    assert handled is True
    assert "تعذر الرفض" not in reply
    live = get_blackboard().get(st.state_id)
    assert live is not None
    pend = (live.extensions or {}).get("pending_action") or {}
    assert pend.get("status") == "rejected"
    assert "multi_agent_pending" not in ud


def test_reject_empty_action_id_uses_pending(board):
    from lumen.engine.services.multi_agent.hitl import reject_action

    st, pending = _make_pending_state(user_id=13)
    ok, state, reason = reject_action(st.state_id, "", user_id=13)
    assert ok is True
    assert reason == "ok"
    assert (state.extensions.get("pending_action") or {}).get("status") == "rejected"


def test_confirm_then_reuse_fails(board):
    from lumen.engine.services.multi_agent.hitl import confirm_action

    st, pending = _make_pending_state(user_id=15)
    ok1, _, r1 = confirm_action(
        st.state_id, pending.action_id, user_id=15, confirm_token=pending.confirm_token
    )
    assert ok1 is True
    ok2, _, r2 = confirm_action(
        st.state_id, pending.action_id, user_id=15, confirm_token=pending.confirm_token
    )
    assert ok2 is False
    assert r2 in {"token_reused", "already_confirmed"} or str(r2).startswith("already_")


def test_keyboard_builds_hitl_buttons():
    os.environ["CALLBACK_HMAC_SECRET"] = "test-hitl-hmac-secret-32chars!!"
    from lumen.bot.multi_agent_bridge import build_hitl_keyboard

    kb = build_hitl_keyboard(user_id=42)
    assert kb is not None
    # InlineKeyboardMarkup with 2 buttons
    rows = kb.inline_keyboard
    assert len(rows) == 1
    assert len(rows[0]) == 2
    texts = {b.text for b in rows[0]}
    assert any("تأكيد" in t for t in texts)
    assert any("رفض" in t for t in texts)
