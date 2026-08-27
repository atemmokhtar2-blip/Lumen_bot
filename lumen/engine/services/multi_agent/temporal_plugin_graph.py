"""Official Temporal LangGraph Plugin graph — aligned with temporalio samples 2026.

Pattern (from temporalio/samples-python langgraph_plugin):
  - Nodes are async callables
  - metadata execute_in=activity on every non-deterministic node
  - Worker: LangGraphPlugin(graphs={...}) — plugin owns Activity registration
  - Workflow: temporal_graph(name).compile(checkpointer=InMemorySaver()).ainvoke(...)
  - HITL: interrupt() + workflow.wait_condition(signal) + Command(resume=...)

Requires: pip install "temporalio[langgraph]>=1.27" langgraph>=1.0
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any, TypedDict

logger = logging.getLogger(__name__)

def _hb(payload: dict[str, Any] | None = None) -> None:
    """Heartbeat when running inside a Temporal Activity (no-op outside).

    Uses the sync heartbeat API so it is safe from threads (asyncio.to_thread).
    """
    try:
        from temporalio import activity
        if not activity.in_activity():
            return
        # Prefer sync path; ignore if runtime returns a coroutine unexpectedly
        result = activity.heartbeat(payload or {})
        if hasattr(result, "send") or hasattr(result, "__await__"):
            pass  # never await from sync worker thread
    except Exception:
        pass



class LumenTGState(TypedDict, total=False):
    request: str
    work_dir: str
    user_id: int
    preferred_keys: list
    state_id: str
    agent: dict
    status: str
    ok: bool
    error: str
    attempts: int
    max_attempts: int
    plan_summary: str


GRAPH_NAME = "lumen-generate"


def plugin_available() -> bool:
    try:
        from temporalio.contrib.langgraph import LangGraphPlugin, graph  # noqa: F401
        from langgraph.graph import StateGraph  # noqa: F401
        return True
    except Exception:
        return False


def _node_meta(*, hours: float, attempts: int = 3) -> dict[str, Any]:
    """Official node metadata — Temporal RetryPolicy only (never LangGraph retry_policy)."""
    from temporalio.common import RetryPolicy

    return {
        "execute_in": "activity",
        "start_to_close_timeout": timedelta(hours=float(hours)),
        "heartbeat_timeout": timedelta(
            minutes=int(os.getenv("TEMPORAL_HEARTBEAT_MINUTES") or "10")
        ),
        "retry_policy": RetryPolicy(
            initial_interval=timedelta(seconds=2),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(seconds=90),
            maximum_attempts=max(1, int(attempts)),
        ),
    }


def _load_agent(state: LumenTGState):
    from .state import AgentState

    raw = state.get("agent")
    if isinstance(raw, dict) and raw:
        try:
            return AgentState.from_dict(raw)
        except Exception:
            pass
    st = AgentState(
        state_id=str(state.get("state_id") or uuid.uuid4().hex[:16]),
        user_id=int(state.get("user_id") or 0),
        user_text=str(state.get("request") or ""),
        spec_request=str(state.get("request") or ""),
        preferred_keys=list(state.get("preferred_keys") or []),
    )
    st.extensions = {
        "work_dir": str(state.get("work_dir") or ""),
        "orchestration": "temporal_plugin+langgraph+cline",
        "durable_shell": "temporal",
    }
    return st


def _plan_sync(state: LumenTGState) -> dict[str, Any]:
    _hb({"phase": "plan_start", "state_id": str(state.get("state_id") or "")})
    from .state import AgentRole, AgentStatus
    from .registry import get_registry
    from .dynamic_planner import assemble_plan
    from .task_tree import TaskTree

    work = str(state.get("work_dir") or ".")
    Path(work).mkdir(parents=True, exist_ok=True)
    agent = _load_agent(state)
    try:
        agent.transition(AgentStatus.PLANNING, role=AgentRole.ORCHESTRATOR, force=True)
    except Exception:
        agent.status = AgentStatus.PLANNING.value

    reg = get_registry()
    architect = reg.get("architect") if hasattr(reg, "get") else None
    if architect is not None:
        agent = architect.run(agent, context={"work_dir": work})

    plan = assemble_plan(
        goal=agent.user_text or agent.spec_request or state.get("request") or "",
        preferred_keys=list(agent.preferred_keys or state.get("preferred_keys") or []),
        constraints=(
            list((agent.strict_spec or {}).get("constraints") or [])
            if isinstance(agent.strict_spec, dict)
            else []
        ),
        language=(
            str((agent.strict_spec or {}).get("language") or "ar")
            if isinstance(agent.strict_spec, dict)
            else "ar"
        ),
        work_dir=work,
    )
    agent.extensions = dict(agent.extensions or {})
    agent.extensions["execution_plan"] = plan.to_dict()
    agent.extensions["work_dir"] = work
    tree = TaskTree.from_execution_plan(plan, goal=plan.goal)
    agent.extensions["task_tree"] = tree.to_dict()
    agent.extensions["task_tree_summary"] = tree.summary()
    agent.record(AgentRole.ORCHESTRATOR, "plugin_plan", f"tasks={len(plan.tasks)}")
    summary = tree.summary() if hasattr(tree, "summary") else {"tasks": len(plan.tasks)}
    return {
        "agent": agent.to_dict(),
        "status": agent.status,
        "attempts": int(agent.attempts or 0),
        "ok": True,
        "error": "",
        "plan_summary": str(summary)[:800],
    }


def _work_sync(state: LumenTGState) -> dict[str, Any]:
    _hb({"phase": "work_start", "state_id": str(state.get("state_id") or "")})
    from .state import AgentRole, AgentStatus
    from .coding_agent import run_coding_session
    from .task_tree import TaskTree, TaskStatus
    from .acceptance_check import evaluate_task

    work = Path(str(state.get("work_dir") or "."))
    work.mkdir(parents=True, exist_ok=True)
    agent = _load_agent(state)
    try:
        agent.transition(AgentStatus.BUILDING, role=AgentRole.ORCHESTRATOR, force=True)
    except Exception:
        agent.status = AgentStatus.BUILDING.value
    agent.attempts = int(agent.attempts or 0) + 1

    tree_raw = (agent.extensions or {}).get("task_tree") or {}
    tree = TaskTree.from_dict(tree_raw) if tree_raw else TaskTree(goal=agent.user_text or "")
    tree.refresh_readiness()
    ready = tree.ready_tasks()
    notes: list[str] = []
    all_ok = True

    if not ready:
        result = run_coding_session(
            work_dir=work,
            goal=agent.spec_request or agent.user_text or state.get("request") or "",
            ir_hint={
                "spec_request": agent.spec_request,
                "preferred_keys": agent.preferred_keys,
            },
        )
        agent.generated_path = str(work)
        agent.build_success = bool(result.get("ok"))
        if not agent.build_success:
            agent.build_errors = list(result.get("errors") or ["work_failed"])[:20]
        all_ok = agent.build_success
        notes.append("full_goal:" + ("ok" if all_ok else "fail"))
    else:
        cap = max(1, min(8, int(os.getenv("MULTI_AGENT_MAX_PARALLEL") or "8")))
        for task in ready[:cap]:
            _hb({"phase": "work_task", "task_id": str(task.id), "attempts": int(agent.attempts or 0)})
            tree.mark(task.id, TaskStatus.RUNNING)
            brief = tree.worker_brief(task.id)
            acc = list(getattr(task, "acceptance", None) or [])
            files = list(getattr(task, "files", None) or [])
            result = run_coding_session(
                work_dir=work,
                goal=agent.spec_request or agent.user_text or "",
                task_brief=brief,
                acceptance=acc,
                target_files=files,
                ir_hint={
                    "spec_request": agent.spec_request,
                    "preferred_keys": agent.preferred_keys,
                },
                constraints=list(
                    ((agent.extensions or {}).get("execution_plan") or {}).get("constraints")
                    or []
                )[:12],
            )
            acc_rep = evaluate_task(work, files=files, acceptance=acc, strict=True)
            if acc_rep.get("ok"):
                tree.mark(
                    task.id,
                    TaskStatus.DONE,
                    result={"acceptance": acc_rep, "steps": result.get("steps")},
                )
                notes.append(f"{task.id}:done")
            else:
                all_ok = False
                fails = [
                    str(f.get("id") or f.get("detail") or "")
                    for f in (acc_rep.get("failed") or [])
                ][:8]
                err = "; ".join(list(result.get("errors") or []) + fails)[:400]
                tree.mark(task.id, TaskStatus.FAILED, error=err, result={"acceptance": acc_rep})
                agent.build_errors = list(agent.build_errors or []) + fails
                notes.append(f"{task.id}:failed")
            agent.extensions["task_tree"] = tree.to_dict()
            agent.extensions["task_tree_summary"] = tree.summary()
            _hb({"phase": "work_task_done", "task_id": str(task.id), "ok": bool(acc_rep.get("ok"))})

    agent.generated_path = str(work)
    agent.build_success = all_ok or any(n.endswith(":done") for n in notes)
    agent.extensions["last_worker_notes"] = notes
    agent.record(AgentRole.BUILDER, "plugin_work", f"notes={len(notes)}")
    return {
        "agent": agent.to_dict(),
        "status": agent.status,
        "attempts": agent.attempts,
        "ok": bool(agent.build_success),
        "error": "" if agent.build_success else ";".join(agent.build_errors or [])[:300],
    }


def _critique_sync(state: LumenTGState) -> dict[str, Any]:
    _hb({"phase": "critique_start", "state_id": str(state.get("state_id") or "")})
    from .state import AgentRole, AgentStatus
    from .registry import get_registry

    work = str(state.get("work_dir") or ".")
    agent = _load_agent(state)
    try:
        agent.transition(AgentStatus.QA, role=AgentRole.ORCHESTRATOR, force=True)
    except Exception:
        agent.status = AgentStatus.QA.value

    reg = get_registry()
    critic = reg.get("critic") if hasattr(reg, "get") else None
    if critic is not None:
        agent = critic.run(agent, context={"work_dir": work})
    else:
        agent.qa_passed = bool(agent.build_success and agent.generated_path)
        agent.qa_report = {"ok": agent.qa_passed, "engine": "plugin_fallback"}

    agent.record(AgentRole.CRITIC, "plugin_critique", f"qa={agent.qa_passed}")
    return {
        "agent": agent.to_dict(),
        "status": agent.status,
        "attempts": int(agent.attempts or 0),
        "ok": bool(agent.qa_passed),
        "error": (
            ""
            if agent.qa_passed
            else str((agent.qa_report or {}).get("errors") or agent.build_errors or "")[:300]
        ),
    }


def _repair_sync(state: LumenTGState) -> dict[str, Any]:
    _hb({"phase": "repair_start", "state_id": str(state.get("state_id") or "")})
    from .state import AgentRole, AgentStatus
    from .repair import build_repair_directive
    from .repair_worker import should_incremental_repair, run_incremental_repair

    work = Path(str(state.get("work_dir") or "."))
    agent = _load_agent(state)
    try:
        agent.transition(AgentStatus.PLANNING, role=AgentRole.ORCHESTRATOR, force=True)
    except Exception:
        agent.status = AgentStatus.PLANNING.value

    try:
        directive = build_repair_directive(agent)
        agent.extensions = dict(agent.extensions or {})
        agent.extensions["last_repair"] = (
            directive.to_dict() if hasattr(directive, "to_dict") else dict(directive or {})
        )
        agent.extensions["repair_mode"] = True
    except Exception as exc:
        agent.extensions = dict(agent.extensions or {})
        agent.extensions["repair_error"] = type(exc).__name__

    if should_incremental_repair(agent):
        agent = run_incremental_repair(agent, work_dir=work)

    agent.record(AgentRole.ORCHESTRATOR, "plugin_repair", f"attempts={agent.attempts}")
    return {
        "agent": agent.to_dict(),
        "status": agent.status,
        "attempts": int(agent.attempts or 0),
        "ok": bool(agent.build_success),
        "error": "",
    }


def _deliver_sync(state: LumenTGState) -> dict[str, Any]:
    from .state import AgentRole, AgentStatus
    from .registry import get_registry

    agent = _load_agent(state)
    if agent.qa_passed:
        try:
            agent.transition(AgentStatus.PASSED, role=AgentRole.ORCHESTRATOR, force=True)
            agent.transition(AgentStatus.DELIVERED, role=AgentRole.ORCHESTRATOR, force=True)
        except Exception:
            agent.status = AgentStatus.DELIVERED.value
    else:
        try:
            agent.transition(AgentStatus.FAILED, role=AgentRole.ORCHESTRATOR, force=True)
        except Exception:
            agent.status = AgentStatus.FAILED.value

    reg = get_registry()
    deliver = reg.get("deliver") if hasattr(reg, "get") else None
    if deliver is not None:
        try:
            agent = deliver.run(agent, context={"work_dir": state.get("work_dir")})
        except Exception:
            pass

    agent.record(AgentRole.ORCHESTRATOR, "plugin_deliver", agent.status)
    return {
        "agent": agent.to_dict(),
        "status": agent.status,
        "attempts": int(agent.attempts or 0),
        "ok": bool(agent.qa_passed)
        or str(agent.status).upper() in {"PASSED", "DELIVERED"},
        "error": "" if agent.qa_passed else (agent.final_message or "")[:300],
    }


# ---- Official async Activity nodes (samples use async def) ----


async def node_plan(state: LumenTGState) -> dict[str, Any]:
    return await asyncio.to_thread(_plan_sync, state)


async def node_work(state: LumenTGState) -> dict[str, Any]:
    return await asyncio.to_thread(_work_sync, state)


async def node_critique(state: LumenTGState) -> dict[str, Any]:
    return await asyncio.to_thread(_critique_sync, state)


async def node_repair(state: LumenTGState) -> dict[str, Any]:
    return await asyncio.to_thread(_repair_sync, state)


async def node_deliver(state: LumenTGState) -> dict[str, Any]:
    return await asyncio.to_thread(_deliver_sync, state)


async def node_plan_gate(state: LumenTGState) -> dict[str, Any]:
    """HITL gate after plan — official interrupt(); Temporal wait_condition resumes it."""
    from langgraph.types import interrupt

    summary = str(state.get("plan_summary") or state.get("request") or "")[:600]
    decision = interrupt(
        {
            "type": "approve_plan",
            "state_id": state.get("state_id"),
            "plan_summary": summary,
            "message": "Approve execution plan to continue building?",
        }
    )
    decision_s = str(decision or "").strip().lower()
    if isinstance(decision, dict):
        decision_s = str(
            decision.get("decision") or decision.get("value") or decision
        ).strip().lower()
    approved = decision_s in {
        "1", "true", "yes", "y", "approve", "approved", "ok", "confirm",
    }
    if not approved:
        return {
            "ok": False,
            "status": "FAILED",
            "error": f"plan_rejected:{decision_s[:40]}",
        }
    return {"ok": True, "status": "BUILDING", "error": ""}


def _route_after_critique(state: LumenTGState) -> str:
    agent = state.get("agent") or {}
    qa = bool(agent.get("qa_passed")) if isinstance(agent, dict) else bool(state.get("ok"))
    attempts = (
        int(state.get("attempts") or agent.get("attempts") or 0)
        if isinstance(agent, dict)
        else int(state.get("attempts") or 0)
    )
    max_att = int(state.get("max_attempts") or 4)
    if qa:
        return "deliver"
    if attempts < max_att:
        return "repair"
    return "deliver"


def _route_after_plan_gate(state: LumenTGState) -> str:
    if state.get("ok") is False or str(state.get("status") or "").upper() == "FAILED":
        return "deliver"
    return "work"


def _hitl_enabled() -> bool:
    """HITL is opt-in only. Default OFF so generate does not hang waiting for a signal."""
    return (os.getenv("MULTI_AGENT_LANGGRAPH_HITL") or "0").strip().lower() in {
        "1", "true", "yes", "on",
    }


def make_lumen_generate_graph():
    """Factory matching temporal samples: make_*_graph() -> StateGraph."""
    from langgraph.graph import END, START, StateGraph

    g = StateGraph(LumenTGState)
    plan_h = float(os.getenv("TEMPORAL_PLAN_HOURS") or "1")
    work_h = float(os.getenv("TEMPORAL_WORK_HOURS") or "6")
    crit_h = float(os.getenv("TEMPORAL_CRITIQUE_HOURS") or "1")

    g.add_node("plan", node_plan, metadata=_node_meta(hours=plan_h, attempts=2))
    g.add_node("work", node_work, metadata=_node_meta(hours=work_h, attempts=3))
    g.add_node("critique", node_critique, metadata=_node_meta(hours=crit_h, attempts=2))
    g.add_node("repair", node_repair, metadata=_node_meta(hours=plan_h, attempts=2))
    g.add_node("deliver", node_deliver, metadata=_node_meta(hours=0.5, attempts=2))

    g.add_edge(START, "plan")
    if _hitl_enabled():
        # plan_gate only when HITL opt-in (never register unreachable nodes)
        g.add_node("plan_gate", node_plan_gate, metadata=_node_meta(hours=0.25, attempts=1))
        g.add_edge("plan", "plan_gate")
        g.add_conditional_edges(
            "plan_gate", _route_after_plan_gate, {"work": "work", "deliver": "deliver"}
        )
    else:
        g.add_edge("plan", "work")
    g.add_edge("work", "critique")
    g.add_conditional_edges(
        "critique", _route_after_critique, {"repair": "repair", "deliver": "deliver"}
    )
    g.add_edge("repair", "work")
    g.add_edge("deliver", END)
    return g


# Back-compat alias
build_lumen_plugin_graph = make_lumen_generate_graph


def build_plugin() -> Any:
    from temporalio.contrib.langgraph import LangGraphPlugin
    from temporalio.common import RetryPolicy

    return LangGraphPlugin(
        graphs={GRAPH_NAME: make_lumen_generate_graph()},
        default_activity_options={
            "start_to_close_timeout": timedelta(hours=2),
            "retry_policy": RetryPolicy(maximum_attempts=3),
        },
    )


__all__ = [
    "LumenTGState",
    "GRAPH_NAME",
    "plugin_available",
    "make_lumen_generate_graph",
    "build_lumen_plugin_graph",
    "build_plugin",
]
