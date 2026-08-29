"""Verb-only HITL confirmation: "تأكيد" (no action_id/token) must be recognized.

This is the regression test for the SECOND root cause of the infinite
"confirm the plan" loop reported by the user:
    "ببعت تاكيد مش بيبدا التوليد ليه"
    ("I send a confirmation and it doesn't start generation, why?")

The user types just "تأكيد" (the verb alone, possibly with a ✓ emoji) because
the plan-approval prompt only needs a yes/no. But the old
``parse_confirmation_message`` required ``len(parts) >= 2`` (i.e. the user had
to type "تأكيد <action_id> <token>"), so a verb-only "تأكيد" returned ``None``.
``message_router`` then treated the confirm as a NEW generation request
("استقبلت الطلب ✓ جاري التوليد الآن...") → a new plan → re-ask confirm →
infinite loop, no generation ever starts.

The fix: ``parse_confirmation_message`` now accepts verb-only messages and the
bridge resolves ``action_id``/``token`` from the ``user_data["multi_agent_pending"]``
stored by ``remember_hitl_pending`` when the plan-approval prompt was shown.
``remember_hitl_pending`` now also stores ``confirm_token``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from lumen.engine.services.multi_agent.hitl import (
    parse_confirmation_message,
    request_confirmation,
    confirm_action,
)
from lumen.engine.services.multi_agent.blackboard import BlackboardStore, MemoryBlackboard
from lumen.engine.services.multi_agent.state import AgentState, AgentStatus, AgentRole
from lumen.bot.multi_agent_bridge import (
    try_handle_hitl_message,
    remember_hitl_pending,
)


@pytest.fixture
def board():
    """Process-local in-memory blackboard (fast, isolated per test)."""
    bb = MemoryBlackboard()
    return bb


def _make_state(board: BlackboardStore, user_id: int = 77) -> AgentState:
    state = AgentState(
        user_id=user_id,
        user_text="build a telegram bot that sends daily quotes",
        capability_id="generate_bot",
        status=AgentStatus.ROUTING.value,
    )
    state.extensions = {"work_dir": str(Path(".").resolve())}
    board.put(state)
    return state


# ---------------------------------------------------------------------------
# parse_confirmation_message — verb-only acceptance
# ---------------------------------------------------------------------------

class TestParseVerbOnly:
    def test_verb_only_confirm_arabic(self):
        """تأكيد alone → ('confirm', '', '')  (was None before fix → loop bug)."""
        result = parse_confirmation_message("تأكيد")
        assert result is not None
        verb, action_id, token = result
        assert verb == "confirm"
        assert action_id == ""
        assert token == ""

    def test_verb_only_confirm_with_emoji(self):
        """تأكيد ✓ → ('confirm', '', '')  — emoji stripped."""
        result = parse_confirmation_message("تأكيد ✓")
        assert result is not None
        verb, action_id, token = result
        assert verb == "confirm"
        assert action_id == ""
        assert token == ""

    def test_verb_only_confirm_english(self):
        """confirm alone → ('confirm', '', '')."""
        result = parse_confirmation_message("confirm")
        assert result == ("confirm", "", "")

    def test_verb_only_confirm_thumbsup(self):
        """تأكيد 👍 → ('confirm', '', '')."""
        result = parse_confirmation_message("تأكيد 👍")
        assert result == ("confirm", "", "")

    def test_verb_only_reject_arabic(self):
        """رفض alone → ('reject', '', '')."""
        result = parse_confirmation_message("رفض")
        assert result == ("reject", "", "")

    def test_verb_only_reject_english(self):
        """reject alone → ('reject', '', '')."""
        result = parse_confirmation_message("reject")
        assert result == ("reject", "", "")

    def test_full_confirm_still_works(self):
        """تأكيد <action_id> <token> → ('confirm', action_id, token)."""
        result = parse_confirmation_message("تأكيد abc123 def456")
        assert result == ("confirm", "abc123", "def456")

    def test_random_text_returns_none(self):
        """Random generation request text → None (not treated as confirm)."""
        assert parse_confirmation_message("اعمل لي بوت يرسل اقتباسات يومية") is None
        assert parse_confirmation_message("build a bot please") is None
        assert parse_confirmation_message("") is None
        assert parse_confirmation_message("   ") is None

    def test_confirm_variants(self):
        """Various confirm synonyms → all recognized as confirm."""
        for word in ["موافق", "موافقة", "ok", "okay", "yes", "أوافق", "افق", "تاكيد"]:
            result = parse_confirmation_message(word)
            assert result is not None, f"{word!r} should be recognized as confirm"
            assert result[0] == "confirm", f"{word!r} verb should be 'confirm'"


# ---------------------------------------------------------------------------
# remember_hitl_pending — stores confirm_token
# ---------------------------------------------------------------------------

class TestRememberHitlPendingStoresToken:
    def test_confirm_token_stored(self, board):
        """remember_hitl_pending must store confirm_token so verb-only confirm works."""
        state = _make_state(board)
        pending = request_confirmation(state, tool="langgraph_plan_approve", board=board)
        user_data: dict = {}
        remember_hitl_pending(user_data, state)

        stored = user_data.get("multi_agent_pending")
        assert stored is not None, "multi_agent_pending should be stored"
        assert stored.get("confirm_token") == pending.confirm_token, (
            "confirm_token must be stored so a verb-only 'تأكيد' can be validated"
        )
        assert stored.get("action_id") == pending.action_id
        assert stored.get("state_id") == state.state_id


# ---------------------------------------------------------------------------
# try_handle_hitl_message — verb-only confirm is HANDLED (not treated as new request)
# ---------------------------------------------------------------------------

class TestTryHandleVerbOnly:
    def test_verb_only_confirm_handled_not_new_request(self, board):
        """The core regression test: 'تأكيد' must be handled=True.

        Before the fix, this returned (False, "") → message_router treated it
        as a NEW generation request → "استقبلت الطلب" → new plan → loop.
        """
        state = _make_state(board)
        request_confirmation(state, tool="langgraph_plan_approve", board=board)
        user_data: dict = {}
        remember_hitl_pending(user_data, state)

        handled, reply = try_handle_hitl_message("تأكيد", user_id=77, user_data=user_data)
        assert handled is True, (
            "Verb-only 'تأكيد' must be handled as a HITL confirm, not fall through "
            "to a new generation request (the infinite-loop root cause)."
        )

    def test_verb_only_confirm_with_emoji_handled(self, board):
        """'تأكيد ✓' must also be handled (emoji stripped)."""
        state = _make_state(board)
        request_confirmation(state, tool="langgraph_plan_approve", board=board)
        user_data: dict = {}
        remember_hitl_pending(user_data, state)

        handled, reply = try_handle_hitl_message("تأكيد ✓", user_id=77, user_data=user_data)
        assert handled is True

    def test_verb_only_confirm_token_resolved_from_user_data(self, board):
        """The HMAC token is resolved from user_data so confirm_action passes.

        Without storing confirm_token in remember_hitl_pending, confirm_action
        would fail with 'bad_token' even though the parser recognized the verb.
        """
        state = _make_state(board)
        pending = request_confirmation(state, tool="langgraph_plan_approve", board=board)
        user_data: dict = {}
        remember_hitl_pending(user_data, state)

        # Simulate the confirm path directly: verb-only, token resolved from user_data
        parsed = parse_confirmation_message("تأكيد")
        assert parsed == ("confirm", "", "")

        stored = user_data["multi_agent_pending"]
        action_id = stored["action_id"]
        token = stored["confirm_token"]
        assert token == pending.confirm_token

        ok, confirmed_state, reason = confirm_action(
            state.state_id, action_id, user_id=77, confirm_token=token, board=board
        )
        assert ok, f"confirm_action should succeed with resolved token, got reason={reason}"
        assert reason == "ok"

    def test_random_text_not_handled(self, board):
        """A normal generation request must NOT be treated as HITL confirm."""
        state = _make_state(board)
        request_confirmation(state, tool="langgraph_plan_approve", board=board)
        user_data: dict = {}
        remember_hitl_pending(user_data, state)

        handled, reply = try_handle_hitl_message(
            "اعمل لي بوت يرسل اقتباسات يومية", user_id=77, user_data=user_data
        )
        assert handled is False, "Normal generation request should not be handled as HITL"

    def test_verb_only_no_pending_handled_gracefully(self, board):
        """'تأكيد' with no pending action → handled=True with 'no pending' reply."""
        user_data: dict = {}  # no pending stored

        handled, reply = try_handle_hitl_message("تأكيد", user_id=77, user_data=user_data)
        assert handled is True, "Should still be handled (graceful), not a new request"
        assert "لا" in reply or "تأكيد" in reply.lower() or reply  # some reply given


# ---------------------------------------------------------------------------
# _resume_or_rerun final_message override (the third fix)
# ---------------------------------------------------------------------------

class TestResumeFailedMessageOverride:
    """When resume fails after confirm, the user must see the REAL error,
    not the stale '⚠️ إجراء حساس — بوابة تأكيد' approval prompt.

    Before the fix, ``state.final_message or "تعذّر..."`` kept the stale approval
    message because final_message was NOT empty (request_confirmation set it).
    The ``or`` fallback never took effect, so the user kept seeing the approval
    prompt and thought their confirmation did nothing — exactly the reported bug.
    """

    def test_resume_failed_overrides_stale_message(self, board, monkeypatch):
        from lumen.engine.services.multi_agent.orchestrator import _resume_or_rerun, Orchestrator

        state = _make_state(board)
        # Simulate the state AFTER request_confirmation: final_message has the
        # stale approval prompt, and a pending_action exists.
        request_confirmation(state, tool="langgraph_plan_approve", board=board)
        assert "إجراء حساس" in (state.final_message or ""), (
            "precondition: request_confirmation sets the stale approval prompt"
        )
        state.extensions["pending_action"] = {
            **(state.extensions.get("pending_action") or {}),
            "tool": "langgraph_plan_approve",
        }
        board.put(state)

        # Force resume_langgraph_hitl to raise (simulates missing checkpoint /
        # any resume failure). This is the exact path where the final_message
        # override bug manifested.
        import lumen.engine.services.multi_agent.langgraph_pipeline as lgp_mod

        def _boom(*a, **kw):
            raise RuntimeError("checkpoint_missing_for_thread: test_injected")

        monkeypatch.setattr(lgp_mod, "resume_langgraph_hitl", _boom)

        ctx = {"work_dir": Path(".")}
        orch = Orchestrator(board=board)
        result = _resume_or_rerun(state, ctx, board, orch, decision="approved")

        # The final_message must be the REAL resume-failed error, NOT the stale
        # "إجراء حساس — بوابة تأكيد" approval prompt.
        assert result.status in ("FAILED", AgentStatus.FAILED.value), (
            f"resume failure should set FAILED, got {result.status}"
        )
        assert "تعذّر" in (result.final_message or ""), (
            f"final_message must contain the real resume-failed Arabic error, "
            f"got: {result.final_message!r}"
        )
        assert "إجراء حساس" not in (result.final_message or ""), (
            "final_message must NOT keep the stale approval prompt — that was the bug"
        )

    def test_reject_failed_overrides_stale_message(self, board, monkeypatch):
        """Same bug for the reject path: final_message must be the reject-failed
        reason, not the stale approval prompt."""
        from lumen.engine.services.multi_agent.orchestrator import _resume_or_rerun, Orchestrator

        state = _make_state(board)
        request_confirmation(state, tool="langgraph_plan_approve", board=board)
        assert "إجراء حساس" in (state.final_message or "")
        state.extensions["pending_action"] = {
            **(state.extensions.get("pending_action") or {}),
            "tool": "langgraph_plan_approve",
        }
        board.put(state)

        import lumen.engine.services.multi_agent.langgraph_pipeline as lgp_mod

        def _boom(*a, **kw):
            raise RuntimeError("reject_resume_failed_test")

        monkeypatch.setattr(lgp_mod, "resume_langgraph_hitl", _boom)

        ctx = {"work_dir": Path(".")}
        orch = Orchestrator(board=board)
        result = _resume_or_rerun(state, ctx, board, orch, decision="rejected")

        assert result.status in ("FAILED", AgentStatus.FAILED.value)
        assert "HITL reject failed" in (result.final_message or ""), (
            f"reject-failed message should show, got: {result.final_message!r}"
        )
        assert "إجراء حساس" not in (result.final_message or ""), (
            "must not keep stale approval prompt"
        )
