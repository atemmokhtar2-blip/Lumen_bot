"""Hardened explicit tool layer — validation, risk, HITL grant, executor."""
from __future__ import annotations

import logging
from typing import Any, Optional

from .hitl import (
    consume_execute_grant,
    request_confirmation,
    tool_requires_confirmation,
    tool_risk,
)
from .state import AgentRole, AgentState, AgentStatus

logger = logging.getLogger(__name__)


def list_tools() -> list[str]:
    try:
        from lumen.engine.services.tool_runtime.registry import list_tool_names
        return list(list_tool_names())
    except Exception:
        return [
            "generate_bot", "refine_bot", "clone_repo", "create_repo",
            "git_push", "git_pull", "host_start", "host_stop", "host_status",
            "repo_inspect", "repo_understand", "repo_modify",
        ]


def get_tool_spec(name: str) -> dict[str, Any]:
    try:
        from lumen.engine.services.tool_runtime.registry import get_tool_spec, TOOL_SPECS
        spec = get_tool_spec(name)
        if spec:
            return dict(spec)
        return dict(TOOL_SPECS.get(name) or {})
    except Exception:
        return {}


def select_tool(state: AgentState) -> str:
    tool = (state.capability_id or state.user_intent or "").strip()
    known = set(list_tools()) | {"chat_or_other"}
    if tool in known:
        return tool
    return tool or "chat_or_other"


def _validate(tool: str, params: dict[str, Any]) -> tuple[bool, list[str]]:
    try:
        from lumen.engine.services.tool_runtime.registry import validate_tool_params
        return validate_tool_params(tool, params)
    except Exception:
        return True, []


def execute_tool_gated(
    state: AgentState,
    tool: str,
    params: dict[str, Any] | None = None,
    *,
    skip_hitl: bool = False,
) -> AgentState:
    """
    Execute with hard gates:
    1) tool must be known (or chat_or_other)
    2) required params validated
    3) high/critical risk → HITL unless single-use grant present
    4) skip_hitl only honored when grant is consumed successfully
    """
    params = dict(params or state.route_params or {})
    tool = (tool or select_tool(state)).strip()
    state.extensions["selected_tool"] = tool
    risk = tool_risk(tool)
    state.extensions["tool_risk"] = risk
    try:
        from lumen.engine.services.progress_bus import report_progress
        report_progress({
            "phase": "orchestrator_tool",
            "tool": str(tool),
            "detail": f"تنفيذ أداة المنسّق: {tool}",
        })
    except Exception:
        pass

    # Unknown tools fail closed
    if tool not in set(list_tools()) | {"chat_or_other", "generate_bot", "refine_bot"}:
        state.extensions["tool_result"] = {"ok": False, "tool": tool, "message": "unknown_tool"}
        state.final_message = f"أداة غير معروفة: {tool}"
        try:
            state.transition(AgentStatus.FAILED, role=AgentRole.TOOL, force=True)
        except Exception:
            state.status = AgentStatus.FAILED.value
        state.record(AgentRole.TOOL, "unknown_tool", tool)
        return state

    ok_params, missing = _validate(tool, params)
    if not ok_params:
        state.extensions["tool_result"] = {
            "ok": False, "tool": tool, "message": "missing_params", "missing": missing,
        }
        state.final_message = f"معاملات ناقصة لـ `{tool}`: {', '.join(missing)}"
        try:
            state.transition(AgentStatus.FAILED, role=AgentRole.TOOL, force=True)
        except Exception:
            state.status = AgentStatus.FAILED.value
        state.record(AgentRole.TOOL, "missing_params", ",".join(missing))
        return state

    needs_hitl = tool_requires_confirmation(tool)

    if needs_hitl:
        # Only proceed if we can consume a grant (from successful confirm)
        if skip_hitl or (state.extensions or {}).get("hitl_confirmed"):
            if not consume_execute_grant(state, tool):
                # No valid grant — re-request confirmation
                request_confirmation(
                    state, tool, params,
                    reason=f"لا يوجد تفويض ساري — أعد التأكيد (مخاطر {risk})",
                    raw_params=params,
                )
                return state
        else:
            request_confirmation(
                state, tool, params,
                reason=f"الأداة `{tool}` مستوى {risk} تتطلب موافقة صريحة",
                raw_params=params,
            )
            return state

    # Safe / granted path
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
        from lumen.engine.services.tool_runtime.executor import execute_tool, run_tools_parallel
        _ud = (state.extensions or {}).get("user_data")
        if not isinstance(_ud, dict):
            _ud = {}
        # Keep active_repo available for repo_* tools
        if state.extensions.get("active_repo") and "active_repo" not in _ud:
            _ud = dict(_ud)
            _ud["active_repo"] = state.extensions["active_repo"]
        uid = int(state.user_id or 0)
        # Phase-3: repo inspect + host_status are independent — run together
        if tool in {"repo_inspect", "repo_understand"}:
            par = run_tools_parallel(
                [
                    {"tool": tool, "params": params},
                    {"tool": "host_status", "params": {}},
                ],
                user_id=uid,
                user_data=_ud,
                max_parallel=3,
            )
            result = par[0] if par else execute_tool(tool, params, user_id=uid, user_data=_ud)
            state.extensions["parallel_tools"] = [
                {
                    "tool": getattr(r, "tool", ""),
                    "ok": bool(getattr(r, "ok", False)),
                }
                for r in (par or [])
            ]
        else:
            result = execute_tool(
                tool,
                params,
                user_id=uid,
                user_data=_ud,
            )
        data = result.to_dict() if hasattr(result, "to_dict") else {
            "ok": bool(getattr(result, "ok", False)),
            "tool": tool,
            "message": str(getattr(result, "message", "")),
        }
        state.extensions["tool_result"] = data
        state.record(AgentRole.TOOL, "executed", f"{tool}:ok={data.get('ok')}:risk={risk}")
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
