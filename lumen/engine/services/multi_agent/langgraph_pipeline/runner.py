"""Official LangGraph multi-agent pipeline — sole generate orchestration path.

  START → plan → schedule ⇄ work → critique → (repair|deliver|fail) → END

Worker nodes call ``coding_agent.run_coding_session`` (official Cline agent_loop),
not a shallow template path.
"""
from __future__ import annotations

import logging
import threading
import operator
import os
from pathlib import Path
from typing import Annotated, Any, Literal, Optional, TypedDict

from ..state import AgentRole, AgentState, AgentStatus
from ..task_tree import TaskStatus, TaskTree

logger = logging.getLogger(__name__)
_TREE_LOCK = threading.Lock()

# Process-wide checkpointer so interrupt → resume works across calls (official MemorySaver).
_SHARED_CHECKPOINTER = None



from .flags import (
    hitl_deliver_enabled,
    hitl_interrupt_enabled,
    langgraph_available,
    use_langgraph_pipeline,
    _shared_checkpointer,
)
from .graph_builder import build_lumen_graph, _compile_graph, GraphState, _make_builder, _max_attempts

def run_langgraph_pipeline(
    state: AgentState,
    *,
    context: Optional[dict[str, Any]] = None,
    registry: Any = None,
    board: Any = None,
    thread_id: str | None = None,
) -> AgentState:
    if not langgraph_available():
        raise RuntimeError("langgraph_not_installed: pip install langgraph langchain-core")
    from ..blackboard import get_blackboard
    from ..registry import get_registry

    reg = registry or get_registry()
    bd = board or get_blackboard()
    graph, checkpointer = _compile_graph(reg, bd)
    max_att = _max_attempts(state)
    state.max_attempts = max_att
    state.extensions = dict(state.extensions or {})
    tid = thread_id or state.state_id or "lumen-default"
    state.extensions["langgraph_thread_id"] = tid
    state.extensions["orchestration"] = "langgraph+cline"
    state.record(AgentRole.ORCHESTRATOR, "langgraph_start", f"max_attempts={max_att};hitl={hitl_interrupt_enabled()}")
    # Official LangGraph concurrency throttle (forum best practice 2025+):
    # max_concurrency bounds parallel Send workers to host + provider limits.
    try:
        max_par = max(1, min(32, int(os.getenv("MULTI_AGENT_MAX_PARALLEL") or "8")))
    except ValueError:
        max_par = 8
    cfg: dict[str, Any] = {
        "recursion_limit": max(40, max_att * 12),
        "max_concurrency": max_par,
    }
    if checkpointer is not None:
        cfg["configurable"] = {"thread_id": tid}
    state.extensions["swarm"] = {
        "max_concurrency": max_par,
        "parallel_enabled": (os.getenv("MULTI_AGENT_PARALLEL") or "1").strip().lower()
        not in {"0", "false", "no", "off"},
        "engine": "langgraph_send",
    }
    result = graph.invoke(
        {
            "agent": state,
            "context": dict(context or {}),
            "last_node": "",
            "active_task_ids": [],
            "wave": 0,
            "done": False,
            "notes": [],
            "hitl_decision": "",
        },
        config=cfg,
    )
    out = result.get("agent") if isinstance(result, dict) else state
    if out is None:
        out = state
    out.extensions = dict(out.extensions or {})
    out.extensions["orchestration"] = "langgraph+cline"
    out.extensions["langgraph_thread_id"] = tid
    out.extensions["langgraph_last_node"] = result.get("last_node") if isinstance(result, dict) else ""
    # Official interrupt payload
    inter = None
    if isinstance(result, dict):
        inter = result.get("__interrupt__")
    if inter:
        out.extensions["hitl_status"] = "awaiting_approval"
        out.extensions["langgraph_interrupt"] = True
        # normalize interrupt value
        try:
            first = inter[0] if isinstance(inter, (list, tuple)) else inter
            val = getattr(first, "value", first)
            out.extensions["hitl_pending"] = val if isinstance(val, dict) else {"raw": str(val)[:500]}
        except Exception:
            out.extensions["hitl_pending"] = {"raw": str(inter)[:500]}
        try:
            out.transition(AgentStatus.AWAITING_CONFIRMATION, role=AgentRole.ORCHESTRATOR, force=True)
        except Exception:
            try:
                out.status = AgentStatus.AWAITING_CONFIRMATION.value
            except Exception:
                out.status = "waiting_confirm"
        # Wire Telegram HITL token path to the same interrupt (official dual surface)
        try:
            from ..hitl import request_confirmation
            pending_payload = out.extensions.get("hitl_pending") or {}
            hitl_type = str(pending_payload.get("type") or "approve_plan")
            if hitl_type == "approve_deliver":
                tool = "langgraph_deliver_approve"
                reason = "موافقة تسليم المشروع (LangGraph HITL deliver)"
                status = "awaiting_deliver_approval"
                header = "📦 المشروع جاهز — موافقة التسليم مطلوبة (HITL)"
            else:
                tool = "langgraph_plan_approve"
                reason = "موافقة خطة LangGraph قبل البناء"
                status = "awaiting_approval"
                header = "📋 الخطة جاهزة — موافقة مطلوبة (LangGraph HITL)"
            pending = request_confirmation(
                out,
                tool,
                params={"thread_id": tid, "goal": (out.user_text or "")[:200], "hitl_type": hitl_type},
                reason=reason,
                board=bd,
            )
            out.extensions["langgraph_interrupt"] = True
            out.extensions["hitl_status"] = status
            # Tokens stay on blackboard + Telegram user_data; UI shows buttons.
            goal = (out.user_text or "")[:180]
            out.final_message = (
                f"{header}\n"
                + (f"الطلب: {goal}\n" if goal else "")
                + "اضغط تأكيد للمتابعة أو رفض للإلغاء.\n"
                "أو اكتب: تأكيد  /  رفض"
            )
        except Exception as _hitl_exc:
            logger.warning("attach pending_action failed: %s", _hitl_exc)
            out.final_message = out.final_message or "بانتظار موافقة HITL (LangGraph)"
    try:
        bd.put(out)
    except Exception:
        pass

    try:
        from lumen.engine.services.presentation import decide_and_attach
        decide_and_attach(out)
    except Exception:
        logger.exception("runner presentation attach failed")

    return out


def resume_langgraph_hitl(
    state: AgentState,
    decision: str | dict[str, Any] = "approved",
    *,
    context: Optional[dict[str, Any]] = None,
    registry: Any = None,
    board: Any = None,
    thread_id: str | None = None,
) -> AgentState:
    """Resume after official interrupt via Command(resume=...).

    Requires SqliteSaver/MemorySaver + same thread_id from the paused run.

    Raises ``RuntimeError`` when the checkpointer has no saved checkpoint for the
    given ``thread_id`` (e.g. the initial run happened in a different process with
    a process-local MemorySaver). In that case LangGraph would silently restart the
    graph from START and re-interrupt — producing an infinite "confirm the plan"
    loop. We detect this and fail loudly instead.
    """
    if not langgraph_available():
        raise RuntimeError("langgraph_not_installed")
    from langgraph.types import Command
    from ..blackboard import get_blackboard
    from ..registry import get_registry

    reg = registry or get_registry()
    bd = board or get_blackboard()
    graph, checkpointer = _compile_graph(reg, bd)
    if checkpointer is None:
        raise RuntimeError("checkpointer_required_for_hitl_resume")
    tid = (
        thread_id
        or (state.extensions or {}).get("langgraph_thread_id")
        or state.state_id
        or "lumen-default"
    )
    cfg: dict[str, Any] = {
        "recursion_limit": max(40, _max_attempts(state) * 12),
        "configurable": {"thread_id": tid},
    }
    resume_val = decision
    if isinstance(decision, str):
        resume_val = decision.strip().lower() or "approved"

    # Guard against cross-process checkpoint loss: if there is no checkpoint for
    # this thread_id, graph.invoke(Command(resume=...)) silently restarts from
    # START and re-interrupts — causing an infinite HITL loop with no generation.
    # We detect the missing checkpoint up front and raise a clear, actionable error.
    _has_checkpoint = False
    try:
        import langgraph
        from langgraph.checkpoint.base import BaseCheckpointSaver
        if isinstance(checkpointer, BaseCheckpointSaver):
            # aget / aget_tuple — try async-capable API then sync fallback
            tup = None
            try:
                import asyncio
                tup = asyncio.get_event_loop().run_until_complete(
                    checkpointer.aget_tuple({"configurable": {"thread_id": tid}})
                )
            except Exception:
                pass
            if tup is None:
                try:
                    tup = checkpointer.get_tuple({"configurable": {"thread_id": tid}})
                except Exception:
                    tup = None
            _has_checkpoint = bool(tup)
    except Exception:
        # If we cannot probe, proceed and rely on the post-invoke re-interrupt guard.
        _has_checkpoint = True

    result = graph.invoke(Command(resume=resume_val), config=cfg)
    out = result.get("agent") if isinstance(result, dict) else state
    if out is None:
        out = state
    out.extensions = dict(out.extensions or {})
    out.extensions["langgraph_thread_id"] = tid
    re_interrupted = bool(result.get("__interrupt__")) if isinstance(result, dict) else False
    out.extensions["langgraph_interrupt"] = re_interrupted
    if re_interrupted:
        out.extensions["hitl_status"] = "awaiting_approval"
    else:
        out.extensions["hitl_status"] = out.extensions.get("hitl_status") or "resumed"
        out.extensions["langgraph_interrupt"] = False

    # Re-interrupt guard: a successful resume of an "approved" plan must NOT pause
    # again at the plan gate. If it does, the checkpoint was missing and the graph
    # restarted from scratch — surface a clear error instead of an infinite loop.
    if (
        re_interrupted
        and str(resume_val).lower() in {"approved", "approve", "yes", "1", "confirm"}
        and not _has_checkpoint
    ):
        out.extensions["hitl_resume_error"] = (
            "checkpoint_missing_for_thread: the LangGraph checkpoint for this thread was not "
            "found (likely created in a different process). Install langgraph-checkpoint-sqlite "
            "and ensure LANGGRAPH_CHECKPOINT_PATH points to a shared durable location."
        )
        raise RuntimeError(out.extensions["hitl_resume_error"])

    try:
        bd.put(out)
    except Exception:
        pass

    try:
        from lumen.engine.services.presentation import decide_and_attach
        decide_and_attach(out)
    except Exception:
        logger.exception("runner presentation attach failed")

    return out


__all__ = [
    "build_lumen_graph",
    "langgraph_available",
    "run_langgraph_pipeline",
    "resume_langgraph_hitl",
    "hitl_interrupt_enabled",
    "use_langgraph_pipeline",
    "GraphState",
]
