"""Unified engine turn — every natural-language message owned by agents.

Telegram (or any channel) must call ``handle_user_turn`` instead of a
standalone chat model. Flow:

  user text
    → RouterAgent (capability + tool selection)
    → execute_tool_gated  OR  signal generate/refine  OR  repo-bound understand
    → final_message + side-effects on user_data

No conversational LLM path. No fake success.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .roles.router import RouterAgent
from .state import AgentRole, AgentState, AgentStatus
from .tools import execute_tool_gated, select_tool

logger = logging.getLogger(__name__)


@dataclass
class EngineTurnResult:
    """Outcome of one agent-owned user turn."""

    ok: bool
    reply: str = ""
    action: str = ""  # "", "generate", "refine", "awaiting_confirm", "tool"
    state: Optional[AgentState] = None
    user_data_updates: dict[str, Any] = field(default_factory=dict)
    tool: str = ""
    capability_id: str = ""
    generate_request: str = ""
    needs_confirmation: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "reply": self.reply,
            "action": self.action,
            "tool": self.tool,
            "capability_id": self.capability_id,
            "generate_request": self.generate_request,
            "needs_confirmation": self.needs_confirmation,
            "state_id": getattr(self.state, "state_id", None) if self.state else None,
            "user_data_updates": dict(self.user_data_updates or {}),
        }


_GENERATE_CAPS = frozenset({"generate_bot", "refine_bot"})
_HOST_CAPS = frozenset({"host_start", "host_stop", "host_status", "host_diagnose"})
_GIT_CAPS = frozenset({"clone_repo", "create_repo", "git_push", "git_pull"})
_REPO_CAPS = frozenset({
    "repo_understand", "repo_inspect", "repo_modify",
    "static_analysis", "package_health", "upgrade_recommend", "upgrade_apply",
    "repo_develop",
})


def _active_repo_path(user_data: dict[str, Any] | None) -> str:
    if not isinstance(user_data, dict):
        return ""
    ar = user_data.get("active_repo")
    if not isinstance(ar, dict):
        return ""
    path = str(ar.get("path") or "").strip()
    if path and Path(path).is_dir():
        return path
    return ""


def _capabilities_help() -> str:
    try:
        from lumen.engine.services.chat_router import get_router
        router = get_router()
        caps = list(router.list_capabilities())
        if caps:
            lines = ["المحرك (الوكلاء) جاهز. اطلب تنفيذ أحد الإجراءات:"]
            for c in sorted(caps, key=lambda x: -int(getattr(x, "priority", 0) or 0))[:16]:
                title = getattr(c, "title_ar", None) or getattr(c, "id", "")
                desc = getattr(c, "description_ar", "") or ""
                if title:
                    lines.append(f"• {title}" + (f" — {desc}" if desc else ""))
            lines.append(
                "\nأمثلة:\n"
                "• عايز بوت فيه /start و /help\n"
                "• اسحب المستودع https://github.com/...\n"
                "• افهم المستودع / حالة الاستضافة"
            )
            return "\n".join(lines)
    except Exception:
        logger.exception("capabilities help failed")
    return (
        "المحرك جاهز. أرسل:\n"
        "• وصف بوت للتوليد (مثال: بوت فيه /start و /help)\n"
        "• اسحب مستودع / بوش / استضافة\n"
        "• أو سؤال عن المستودع النشط"
    )


def handle_user_turn(
    text: str,
    *,
    user_id: int = 0,
    user_data: dict[str, Any] | None = None,
) -> EngineTurnResult:
    """Run one full agent-owned turn. Always returns a result (never None)."""
    text = (text or "").strip()
    ud = dict(user_data or {})
    if not text:
        return EngineTurnResult(
            ok=False,
            reply="اكتب طلبك بوضوح (توليد بوت، سحب مستودع، فهم المشروع، استضافة…).",
            action="",
        )

    state = AgentState(
        user_id=int(user_id or 0),
        user_text=text[:8000],
        spec_request=text[:8000],
    )
    repo_path = _active_repo_path(ud)
    if repo_path:
        state.extensions["work_dir"] = repo_path
        state.extensions["active_repo"] = dict(ud.get("active_repo") or {})

    # 1) Router agent — sole intent authority for this turn
    try:
        state = RouterAgent().run(state, context={"user_data": ud, "user_id": int(user_id or 0)})
    except Exception as exc:
        logger.exception("RouterAgent failed")
        return EngineTurnResult(
            ok=False,
            reply=f"فشل توجيه الطلب داخل المحرك: {type(exc).__name__}",
            state=state,
        )

    cap = str(state.capability_id or state.user_intent or "").strip()
    tool = str(select_tool(state) or cap or "").strip()
    params = dict(state.route_params or {})
    params.setdefault("text", text)
    params.setdefault("raw_text", text)
    if repo_path:
        params.setdefault("path", repo_path)

    # 2) Generate / refine → signal caller to run multi-agent generation pipeline
    if cap in _GENERATE_CAPS or tool in _GENERATE_CAPS:
        action = "refine" if cap == "refine_bot" or tool == "refine_bot" else "generate"
        return EngineTurnResult(
            ok=True,
            reply="",
            action=action,
            state=state,
            tool=tool or cap,
            capability_id=cap,
            generate_request=text,
            user_data_updates={
                "force_generate_once": True,
                "translated_source": "engine_turn",
                "last_bot_request": text[:2000],
                "multi_agent_state_id": state.state_id,
            },
        )

    # 3) Bound repo + soft/unknown intent → agents measure the repo (not chat)
    if tool in {"chat_or_other", ""} and repo_path:
        tool = "repo_understand"
        cap = "repo_understand"
        params["path"] = repo_path
        state.capability_id = "repo_understand"
        state.user_intent = "repo_understand"

    # 4) No tool and no repo → capabilities from agent registry surface
    if tool in {"chat_or_other", ""}:
        help_text = _capabilities_help()
        state.final_message = help_text
        try:
            state.transition(AgentStatus.DELIVERED, role=AgentRole.ROUTER, force=True)
        except Exception:
            state.status = AgentStatus.DELIVERED.value
        return EngineTurnResult(
            ok=True,
            reply=help_text,
            action="help",
            state=state,
            tool="chat_or_other",
            capability_id=cap or "help",
        )

    # 5) Host / git / repo tools → execute_tool_gated (HITL when required)
    state.route_params = params
    state.capability_id = cap or tool
    try:
        # Pass user_data into extensions for tools that need active_repo
        state.extensions = dict(state.extensions or {})
        state.extensions["user_data"] = ud
        state = execute_tool_gated(state, tool, params)
    except Exception as exc:
        logger.exception("execute_tool_gated failed tool=%s", tool)
        return EngineTurnResult(
            ok=False,
            reply=f"فشل تنفيذ `{tool}`: {type(exc).__name__}",
            action="tool",
            state=state,
            tool=tool,
            capability_id=cap,
        )

    # HITL pause
    status_u = str(getattr(state, "status", "") or "").upper()
    pending = (state.extensions or {}).get("pending_action") or {}
    if status_u in {"AWAITING_CONFIRMATION", "WAITING_CONFIRM"} or (
        isinstance(pending, dict) and pending.get("action_id")
    ):
        msg = (state.final_message or "").strip() or (
            f"يتطلب تأكيد لتنفيذ `{tool}`. اكتب: تأكيد أو رفض."
        )
        updates: dict[str, Any] = {
            "multi_agent_state_id": state.state_id,
            "multi_agent_pending": {
                "action_id": pending.get("action_id"),
                "state_id": state.state_id,
                "tool": tool,
                "confirm_token": pending.get("confirm_token"),
            },
        }
        return EngineTurnResult(
            ok=True,
            reply=msg[:4000],
            action="awaiting_confirm",
            state=state,
            tool=tool,
            capability_id=cap,
            needs_confirmation=True,
            user_data_updates=updates,
        )

    tr = (state.extensions or {}).get("tool_result") or {}
    reply = (state.final_message or "").strip() or str(tr.get("message") or "")
    ok = bool(tr.get("ok", True)) if tr else bool(reply)

    updates = {"multi_agent_state_id": state.state_id}
    # Propagate active_repo if tool data includes path
    data = tr.get("data") if isinstance(tr, dict) else None
    if isinstance(data, dict) and data.get("path"):
        updates["active_repo"] = {
            "path": data["path"],
            "url": data.get("url") or "",
        }
        updates["last_project_path"] = data["path"]

    # repo_modify → refine via multi-agent (structural change owned by agents)
    if isinstance(tr, dict) and (tr.get("data") or {}).get("defer_refine"):
        change = str((tr.get("data") or {}).get("change") or text)
        path = str((tr.get("data") or {}).get("path") or repo_path or "")
        gen = f"تعديل البوت/المشروع في {path}: {change}" if path else change
        return EngineTurnResult(
            ok=True,
            reply=(reply or tr.get("message") or "جاري التعديل عبر المحرك…")[:4000],
            action="refine",
            state=state,
            tool=tool,
            capability_id=cap or "repo_modify",
            generate_request=gen,
            user_data_updates={
                **updates,
                "force_generate_once": True,
                "translated_source": "engine_turn_repo_modify",
                "last_bot_request": gen[:2000],
                "last_project_path": path or updates.get("last_project_path", ""),
            },
        )

    # Deferred generate signal from tool layer
    if isinstance(tr, dict) and tr.get("defer") and tool in _GENERATE_CAPS:
        return EngineTurnResult(
            ok=True,
            reply=reply,
            action="generate" if tool == "generate_bot" else "refine",
            state=state,
            tool=tool,
            capability_id=cap,
            generate_request=text,
            user_data_updates={
                **updates,
                "force_generate_once": True,
                "translated_source": "engine_turn",
                "last_bot_request": text[:2000],
            },
        )

    if not reply:
        reply = f"تم تنفيذ `{tool}`." if ok else f"فشل تنفيذ `{tool}`."

    return EngineTurnResult(
        ok=ok,
        reply=reply[:4000],
        action="tool",
        state=state,
        tool=tool,
        capability_id=cap,
        user_data_updates=updates,
    )


__all__ = ["EngineTurnResult", "handle_user_turn"]
