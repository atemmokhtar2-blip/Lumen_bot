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
    """If the user message is a multi-agent confirm/reject, process it.

    Returns (handled, reply_text). Verb-only messages resolve action_id/token
    from Telegram user_data or the durable blackboard.
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
    state_id = ""
    pending: dict = {}
    if isinstance(user_data, dict):
        state_id = str(user_data.get("multi_agent_state_id") or "")
        pending = user_data.get("multi_agent_pending") or {}
        if not isinstance(pending, dict):
            pending = {}
        if not state_id:
            state_id = str(pending.get("state_id") or "")
        if not action_id:
            action_id = str(pending.get("action_id") or "")
        if not token:
            token = str(pending.get("confirm_token") or "")

    # Recover from durable blackboard (restart / multi-worker / empty user_data)
    board_state = None
    try:
        if not state_id:
            latest = latest_for_user(int(user_id or 0))
            if latest is not None:
                state_id = str(getattr(latest, "state_id", "") or "")
                board_state = latest
        if state_id and (not action_id or (verb == "confirm" and not token)):
            board_state = board_state or get_blackboard().get(state_id)
            if board_state is not None:
                ext = getattr(board_state, "extensions", None) or {}
                bp = ext.get("pending_action") or {}
                if isinstance(bp, dict):
                    if not action_id:
                        action_id = str(bp.get("action_id") or "")
                    if not token:
                        token = str(bp.get("confirm_token") or "")
                    if isinstance(user_data, dict):
                        user_data["multi_agent_pending"] = {
                            "action_id": action_id,
                            "state_id": state_id,
                            "tool": bp.get("tool") or pending.get("tool") or "langgraph_plan_approve",
                            "confirm_token": token,
                            "langgraph_thread_id": ext.get("langgraph_thread_id"),
                        }
                        user_data["multi_agent_state_id"] = state_id
    except Exception:
        logger.exception("HITL pending recovery failed")

    if not state_id:
        return True, "لا يوجد إجراء معلّق. اطلب التوليد من جديد ثم أكّد أو ارفض."

    if verb == "reject":
        ok, state, reason = reject_action(state_id, action_id, user_id=int(user_id or 0))
        if ok and state is not None:
            ext = getattr(state, "extensions", None) or {}
            pend = ext.get("pending_action") or {}
            tool = str(pend.get("tool") or "")
            if (
                ext.get("langgraph_interrupt")
                or tool in {"langgraph_plan_approve", "langgraph_deliver_approve"}
                or ext.get("hitl_status") in {"awaiting_approval", "awaiting_deliver_approval"}
            ):
                try:
                    from lumen.engine.services.multi_agent.langgraph_pipeline import resume_langgraph_hitl
                    state = resume_langgraph_hitl(state, "rejected")
                except Exception as exc:
                    logger.exception("langgraph reject resume failed")
                    if state is not None and not (state.final_message or "").strip():
                        state.final_message = f"تم الرفض."
        if isinstance(user_data, dict):
            user_data.pop("multi_agent_pending", None)
            user_data.pop("multi_agent_state_id", None)
        if ok and state is not None:
            return True, (state.final_message or "✅ تم رفض الخطة. يمكنك طلب توليد جديد.").strip()[:4000]
        reason_ar = {
            "state_not_found": "لم يُعثر على الجلسة",
            "user_mismatch": "هذا الطلب ليس لحسابك",
            "action_mismatch": "لا يوجد إجراء معلّق للرفض",
        }.get(str(reason), str(reason))
        return True, f"تعذر الرفض: {reason_ar}"

    # confirm
    if not action_id or not token:
        return True, (
            "تعذر التأكيد: بيانات الموافقة ناقصة.\n"
            "أعد طلب التوليد ثم اضغط ✅ تأكيد مباشرة."
        )

    ok, state, reason = confirm_action(
        state_id, action_id, user_id=int(user_id or 0), confirm_token=token or "",
    )
    if not ok or state is None:
        reason_ar = {
            "state_not_found": "لم يُعثر على الجلسة — أعد التوليد",
            "user_mismatch": "هذا الطلب ليس لحسابك",
            "action_mismatch": "لا يوجد إجراء معلّق — أعد التوليد",
            "bad_token": "انتهت صلاحية رمز التأكيد — أعد التوليد",
            "token_reused": "تم استخدام التأكيد مسبقاً",
            "expired": "انتهت صلاحية الموافقة — أعد التوليد",
        }.get(str(reason), str(reason))
        if str(reason).startswith("already_"):
            reason_ar = "تم التعامل مع هذا الإجراء مسبقاً"
        return True, f"تعذر التأكيد: {reason_ar}"[:4000]

    try:
        state = continue_after_confirm(state_id, user_id=int(user_id or 0))
    except Exception as exc:
        logger.exception("continue_after_confirm failed")
        state = get_blackboard().get(state_id)
        if state is not None:
            extra = f"\n\n⚠️ التأكيد نجح لكن الاستئناف واجه: {type(exc).__name__}"
            state.final_message = ((state.final_message or "تم التأكيد") + extra)[:4000]

    if isinstance(user_data, dict):
        user_data.pop("multi_agent_pending", None)
        user_data["multi_agent_state_id"] = state_id

    if state is None:
        return True, "تم التأكيد لكن تعذر استكمال التنفيذ. أعد التوليد."
    msg = (state.final_message or "").strip()
    if not msg:
        msg = "✅ تم التأكيد — جاري متابعة البناء."
    return True, msg[:4000]



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
                "tool": pending.get("tool") or ("langgraph_deliver_approve" if (ext.get("hitl_pending") or {}).get("type") == "approve_deliver" else "langgraph_plan_approve"),
                "langgraph_thread_id": ext.get("langgraph_thread_id"),
                # Store the HMAC token so a verb-only "تأكيد" confirm (without the
                # user typing the long token) can be validated by confirm_action.
                "confirm_token": pending.get("confirm_token") or "",
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


def format_hitl_user_message(state: Any) -> str:
    """Clean Arabic HITL prompt — no token dumps (tokens live in user_data + buttons)."""
    if state is None:
        return "بانتظار موافقتك للمتابعة."
    ext = getattr(state, "extensions", None) or {}
    pending = ext.get("pending_action") or {}
    tool = str(pending.get("tool") or ext.get("hitl_pending", {}).get("type") or "plan")
    goal = (getattr(state, "user_text", None) or "")[:160]
    if "deliver" in tool:
        title = "📦 المشروع جاهز — يلزم موافقتك للتسليم"
    else:
        title = "📋 الخطة جاهزة — يلزم موافقتك قبل البناء"
    lines = [title, ""]
    if goal:
        lines.append(f"الطلب: {goal}")
    lines.append("")
    lines.append("اضغط **تأكيد** للمتابعة أو **رفض** للإلغاء.")
    lines.append("أو اكتب: تأكيد   /   رفض")
    return "\n".join(lines)[:3500]


def build_hitl_keyboard(*, user_id: int = 0):
    """Inline buttons for HITL — labels only; secrets stay in user_data pending."""
    try:
        from lumen.engine.services.ui_state.models import UiButton
        from lumen.bot.ui.keyboards import build_inline_keyboard
        rows = [
            [
                UiButton(text="✅ تأكيد", action="hitl_confirm", arg=""),
                UiButton(text="❌ رفض", action="hitl_reject", arg=""),
            ]
        ]
        return build_inline_keyboard(rows, user_id=int(user_id or 0))
    except Exception:
        logger.exception("build_hitl_keyboard failed")
        return None
