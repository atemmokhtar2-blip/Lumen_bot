"""Bridge: wire multi-agent HITL + health into the live Telegram bot path."""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def try_handle_hitl_message(
    text: str,
    *,
    user_id: int,
    user_data: dict[str, Any] | None,
) -> tuple[bool, str]:
    """
    If the user message is a multi-agent confirm/reject, process it.
    Returns (handled, reply_text).
    """
    try:
        from lumen.engine.services.multi_agent import (
            parse_confirmation_message,
            confirm_action,
            reject_action,
            continue_after_confirm,
            get_blackboard,
            latest_for_user,
        )
    except Exception:
        logger.exception("multi_agent HITL import failed")
        return False, ""

    parsed = parse_confirmation_message(text or "")
    if parsed is None:
        return False, ""

    verb, action_id, token = parsed
    # Resolve state_id: user_data pending → latest board for user
    state_id = ""
    if isinstance(user_data, dict):
        state_id = str(user_data.get("multi_agent_state_id") or "")
        pending = user_data.get("multi_agent_pending") or {}
        if not state_id and isinstance(pending, dict):
            state_id = str(pending.get("state_id") or "")
        if not action_id and isinstance(pending, dict):
            action_id = str(pending.get("action_id") or action_id)

    if not state_id:
        try:
            latest = latest_for_user(int(user_id or 0))
            if latest is not None:
                state_id = latest.state_id
        except Exception:
            logger.exception("latest_for_user failed")

    if not state_id:
        return True, "لا يوجد إجراء معلّق للتأكيد. اطلب العملية من جديد."

    if verb == "reject":
        ok, state, reason = reject_action(state_id, action_id, user_id=int(user_id or 0))
        if ok and state is not None:
            ext = getattr(state, "extensions", None) or {}
            pending = ext.get("pending_action") or {}
            if (
                ext.get("langgraph_interrupt")
                or pending.get("tool") == "langgraph_plan_approve"
                or ext.get("hitl_status") == "awaiting_approval"
            ):
                try:
                    from lumen.engine.services.multi_agent.langgraph_pipeline import resume_langgraph_hitl
                    state = resume_langgraph_hitl(state, "rejected")
                except Exception:
                    logger.exception("langgraph reject resume failed")
        if isinstance(user_data, dict):
            user_data.pop("multi_agent_pending", None)
            user_data.pop("multi_agent_state_id", None)
        if ok and state is not None:
            return True, (state.final_message or f"تم الرفض ({action_id}).")[:4000]
        return True, f"تعذر الرفض: {reason}"

    # confirm
    ok, state, reason = confirm_action(
        state_id, action_id, user_id=int(user_id or 0), confirm_token=token or "",
    )
    if not ok or state is None:
        return True, (
            f"تعذر التأكيد: {reason}\n"
            "الصيغة: تأكيد <id> <token>"
        )[:4000]

    try:
        state = continue_after_confirm(state_id, user_id=int(user_id or 0))
    except Exception:
        logger.exception("continue_after_confirm failed")
        state = get_blackboard().get(state_id)

    if isinstance(user_data, dict):
        user_data.pop("multi_agent_pending", None)
        user_data["multi_agent_state_id"] = state_id

    if state is None:
        return True, "تم التأكيد لكن تعذر استكمال التنفيذ."
    return True, (state.final_message or "تم التأكيد والتنفيذ.")[:4000]


def remember_hitl_pending(user_data: dict[str, Any] | None, state: Any) -> None:
    """Store pending HITL ids on telegram user_data for later confirm messages."""
    if not isinstance(user_data, dict) or state is None:
        return
    try:
        ext = getattr(state, "extensions", None) or {}
        pending = ext.get("pending_action") or {}
        if pending or ext.get("langgraph_interrupt"):
            user_data["multi_agent_pending"] = {
                "action_id": pending.get("action_id"),
                "state_id": getattr(state, "state_id", "") or pending.get("state_id"),
                "tool": pending.get("tool") or "langgraph_plan_approve",
                "langgraph_thread_id": ext.get("langgraph_thread_id"),
            }
            user_data["multi_agent_state_id"] = (
                getattr(state, "state_id", "") or pending.get("state_id")
            )
    except Exception:
        logger.exception("remember_hitl_pending failed")


def multi_agent_health_line() -> str:
    try:
        from lumen.engine.services.multi_agent import health_snapshot
        snap = health_snapshot(deep=False)
        ok = "OK" if snap.get("ok") else "DEGRADED"
        agents = ",".join((snap.get("checks") or {}).get("agents", {}).get("agents") or [])
        return f"multi_agent={ok} agents=[{agents}]"
    except Exception as exc:
        return f"multi_agent=ERR:{type(exc).__name__}"
