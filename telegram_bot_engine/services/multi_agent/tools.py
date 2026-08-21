"""Explicit tool layer for multi-agent — catalog + gated execution."""
from __future__ import annotations

import logging
from typing import Any, Optional

from .hitl import request_confirmation, tool_requires_confirmation
from .state import AgentRole, AgentState, AgentStatus

logger = logging.getLogger(__name__)


def list_tools() -> list[str]:
    try:
        from telegram_bot_engine.services.tool_runtime.registry import list_tool_names
        return list(list_tool_names())
    except Exception:
        return [
            "generate_bot", "refine_bot", "clone_repo", "create_repo",
            "git_push", "git_pull", "host_start", "host_stop", "host_status",
            "repo_inspect", "repo_understand", "repo_modify",
        ]


def get_tool_spec(name: str) -> dict[str, Any]:
    try:
        from telegram_bot_engine.services.tool_runtime.registry import get_tool_spec, TOOL_SPECS
        if "get_tool_spec" in dir() and callable(get_tool_spec):
            spec = get_tool_spec(name)
            if spec:
                return dict(spec)
        return dict(TOOL_SPECS.get(name) or {})
    except Exception:
        return {}


def select_tool(state: AgentState) -> str:
    """Resolve tool name from router intent / capability_id."""
    tool = (state.capability_id or state.user_intent or "").strip()
    if tool in list_tools() or tool in {
        "generate_bot", "refine_bot", "chat_or_other",
    }:
        return tool
    return tool or "chat_or_other"


def execute_tool_gated(
    state: AgentState,
    tool: str,
    params: dict[str, Any] | None = None,
    *,
    skip_hitl: bool = False,
) -> AgentState:
    """
    Execute tool with HITL gate.
    - If requires confirmation and not yet confirmed → park AWAITING_CONFIRMATION
    - If confirmed or safe tool → dispatch executor
    """
    params = dict(params or state.route_params or {})
    tool = (tool or select_tool(state)).strip()
    state.extensions["selected_tool"] = tool

    pending = (state.extensions or {}).get("pending_action") or {}
    already_confirmed = (
        bool((state.extensions or {}).get("hitl_confirmed"))
        and str(pending.get("tool") or "") == tool
        and str(pending.get("status") or "") == "confirmed"
    )

    if tool_requires_confirmation(tool) and not skip_hitl and not already_confirmed:
        request_confirmation(state, tool, params, reason=f"الأداة `{tool}` تتطلب موافقة صريحة")
        return state

    # generate_bot / refine_bot are handled by the build pipeline — signal only
    if tool in {"generate_bot", "refine_bot"}:
        state.extensions["tool_result"] = {
            "ok": True, "tool": tool, "defer": True, "message": "defer_to_builder",
        }
        state.record(AgentRole.TOOL, "defer_generate", tool)
        return state

    if tool in {"chat_or_other", ""}:
        state.extensions["tool_result"] = {
            "ok": True, "tool": tool, "defer": True, "message": "chat_path",
        }
        return state

    try:
        from telegram_bot_engine.services.tool_runtime.executor import execute_tool
        result = execute_tool(tool, params, user_id=int(state.user_id or 0))
        data = result.to_dict() if hasattr(result, "to_dict") else {
            "ok": bool(getattr(result, "ok", False)),
            "tool": tool,
            "message": str(getattr(result, "message", "")),
        }
        state.extensions["tool_result"] = data
        state.record(AgentRole.TOOL, "executed", f"{tool}:ok={data.get('ok')}")
        if data.get("ok"):
            state.final_message = str(data.get("message") or f"تم تنفيذ {tool}")
            try:
                state.transition(AgentStatus.DELIVERED, role=AgentRole.TOOL, force=True)
            except Exception:
                state.status = AgentStatus.DELIVERED.value
        else:
            state.final_message = str(data.get("message") or f"فشل {tool}")
            try:
                state.transition(AgentStatus.FAILED, role=AgentRole.TOOL, force=True)
            except Exception:
                state.status = AgentStatus.FAILED.value
    except Exception as exc:
        logger.exception("tool %s failed", tool)
        state.extensions["tool_result"] = {"ok": False, "tool": tool, "message": type(exc).__name__}
        state.record(AgentRole.TOOL, "tool_error", type(exc).__name__)
        try:
            state.transition(AgentStatus.FAILED, role=AgentRole.TOOL, force=True)
        except Exception:
            state.status = AgentStatus.FAILED.value
    return state
