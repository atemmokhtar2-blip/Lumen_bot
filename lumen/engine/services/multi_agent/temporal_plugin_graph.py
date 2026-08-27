"""Official Temporal + LangGraph Plugin graph for Lumen generate (Phase A).

World-class 2026 pattern (Temporal docs):
  - Each heavy node runs as a Temporal **Activity** (execute_in=activity)
  - Workflow is deterministic; durability/retries owned by Temporal
  - InMemorySaver for interrupts — Temporal owns process-crash durability

This replaces the weak "wrap entire graph in one activity" path.
Requires: pip install "temporalio[langgraph]>=1.27"
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any, Optional, TypedDict

logger = logging.getLogger(__name__)


class LumenTGState(TypedDict, total=False):
    """Serializable graph state crossing Temporal Activity boundaries."""

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
    hitl_decision: str


def plugin_available() -> bool:
    try:
        from temporalio.contrib.langgraph import LangGraphPlugin, graph  # noqa: F401
        from langgraph.graph import StateGraph  # noqa: F401
        return True
    except Exception:
        return False


def _activity_meta(*, hours: float = 2.0, attempts: int = 3) -> dict[str, Any]:
    """Temporal Activity options via official node metadata (not LangGraph retry_policy)."""
    try:
        from temporalio.common import RetryPolicy
        retry = RetryPolicy(
            initial_interval=timedelta(seconds=2),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(seconds=60),
            maximum_attempts=max(1, attempts),
        )
    except Exception:
        retry = None
    meta: dict[str, Any] = {
        "execute_in": "activity",
        "start_to_close_timeout": timedelta(hours=float(hours)),
        "heartbeat_timeout": timedelta(minutes=int(os.getenv("TEMPORAL_HEARTBEAT_MINUTES") or "10")),
    }
    if retry is not None:
        meta["retry_policy"] = retry
    return meta


def _load_state(raw: dict[str, Any] | None, *, fallback: LumenTGState) -> Any:
    from .state import AgentState

    if isinstance(raw, dict) and raw:
        try:
            return AgentState.from_dict(raw)
        except Exception:
            pass
    st = AgentState(
        state_id=str(fallback.get("state_id") or uuid.uuid4().hex[:16]),
        user_id=int(fallback.get("user_id") or 0),
        user_text=str(fallback.get("request") or ""),
        spec_request=str(fallback.get("request") or ""),
        preferred_keys=list(fallback.get("preferred_keys") or []),
    )
    st.extensions = {"work_dir": str(fallback.get("work_dir") or ""), "orchestration": "temporal_plugin+langgraph+cline"}
    return st


def _node_plan(state: LumenTGState) -> dict[str, Any]:
    """Planner node — StrictSpec + TaskTree (Activity)."""
    from .state import AgentRole, AgentStatus
    from .registry import get_registry
    from .dynamic_planner import assemble_plan
    from .task_tree import TaskTree

    work = str(state.get("work_dir") or ".")
    Path(work).mkdir(parents=True, exist_ok=True)
    agent = _load_state(state.get("agent"), fallback=state)
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
        constraints=list((agent.strict_spec or {}).get("constraints") or []) if isinstance(agent.strict_spec, dict) else [],
        language=str((agent.strict_spec or {}).get("language") or "ar") if isinstance(agent.strict_spec, dict) else "ar",
        work_dir=work,
    )
    agent.extensions = dict(agent.extensions or {})
    agent.extensions["execution_plan"] = plan.to_dict()
    agent.extensions["work_dir"] = work
    tree = TaskTree.from_execution_plan(plan, goal=plan.goal)
    agent.extensions["task_tree"] = tree.to_dict()
    agent.extensions["task_tree_summary"] = tree.summary()
    agent.record(AgentRole.ORCHESTRATOR, "plugin_plan", f"tasks={len(plan.tasks)}")
    return {
        "agent": agent.to_dict(),
        "status": agent.status,
        "attempts": int(agent.attempts or 0),
        "ok": True,
        "error": "",
    }


def _node_work(state: LumenTGState) -> dict[str, Any]:
    """Worker node — Cline coding session via coding_agent (Activity)."""
    from .state import AgentRole, AgentStatus
    from .coding_agent import run_coding_session
    from .task_tree import TaskTree, TaskStatus
    from .acceptance_check import evaluate_task

    work = Path(str(state.get("work_dir") or "."))
    work.mkdir(parents=True, exist_ok=True)
    agent = _load_state(state.get("agent"), fallback=state)
    try:
        agent.transition(AgentStatus.BUILDING, role=AgentRole.ORCHESTRATOR, force=True)
    except Exception:
        agent.status = AgentStatus.BUILDING.value
    agent.attempts = int(agent.attempts or 0) + 1

    tree_raw = (agent.extensions or {}).get("task_tree") or {}
    tree = TaskTree.from_dict(tree_raw) if tree_raw else TaskTree(goal=agent.user_text or "")
    tree.refresh_readiness()
    ready = tree.ready_tasks()
    if not ready:
        # single-shot full goal if tree empty
        result = run_coding_session(
            work_dir=work,
            goal=agent.spec_request or agent.user_text or state.get("request") or "",
            ir_hint={"spec_request": agent.spec_request, "preferred_keys": agent.preferred_keys},
        )
        agent.generated_path = str(work)
        agent.build_success = bool(result.get("ok"))
        if not agent.build_success:
            agent.build_errors = list(result.get("errors") or ["work_failed"])[:20]
        agent.extensions["task_tree"] = tree.to_dict()
        return {
            "agent": agent.to_dict(),
            "status": agent.status,
            "attempts": agent.attempts,
            "ok": bool(agent.build_success),
            "error": "" if agent.build_success else ";".join(agent.build_errors or [])[:300],
        }

    # Execute ready wave sequentially inside this activity (Send fan-out stays in-process path)
    notes: list[str] = []
    all_ok = True
    for task in ready[: max(1, min(8, int(os.getenv("MULTI_AGENT_MAX_PARALLEL") or "8")))]:
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
            ir_hint={"spec_request": agent.spec_request, "preferred_keys": agent.preferred_keys},
            constraints=list(((agent.extensions or {}).get("execution_plan") or {}).get("constraints") or [])[:12],
        )
        acc_rep = evaluate_task(work, files=files, acceptance=acc, strict=True)
        session_ok = bool(acc_rep.get("ok"))
        if session_ok:
            tree.mark(task.id, TaskStatus.DONE, result={"acceptance": acc_rep, "steps": result.get("steps")})
            notes.append(f"{task.id}:done")
        else:
            all_ok = False
            fails = [str(f.get("id") or f.get("detail") or "") for f in (acc_rep.get("failed") or [])][:8]
            err = "; ".join(list(result.get("errors") or []) + fails)[:400]
            tree.mark(task.id, TaskStatus.FAILED, error=err, result={"acceptance": acc_rep})
            agent.build_errors = list(agent.build_errors or []) + fails
            notes.append(f"{task.id}:failed")
        agent.extensions["task_tree"] = tree.to_dict()
        agent.extensions["task_tree_summary"] = tree.summary()

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


def _node_critique(state: LumenTGState) -> dict[str, Any]:
    """Critic node — QA + execution feedback (Activity)."""
    from .state import AgentRole, AgentStatus
    from .registry import get_registry

    work = str(state.get("work_dir") or ".")
    agent = _load_state(state.get("agent"), fallback=state)
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
        "error": "" if agent.qa_passed else str((agent.qa_report or {}).get("errors") or agent.build_errors or "")[:300],
    }


def _node_repair(state: LumenTGState) -> dict[str, Any]:
    """Repair node — directive + optional incremental repair (Activity)."""
    from .state import AgentRole, AgentStatus
    from .repair import build_repair_directive
    from .repair_worker import should_incremental_repair, run_incremental_repair

    work = Path(str(state.get("work_dir") or "."))
    agent = _load_state(state.get("agent"), fallback=state)
    try:
        agent.transition(AgentStatus.PLANNING, role=AgentRole.ORCHESTRATOR, force=True)
    except Exception:
        agent.status = AgentStatus.PLANNING.value

    try:
        directive = build_repair_directive(agent)
        agent.extensions = dict(agent.extensions or {})
        agent.extensions["last_repair"] = directive.to_dict() if hasattr(directive, "to_dict") else dict(directive or {})
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


def _node_deliver(state: LumenTGState) -> dict[str, Any]:
    """Deliver node — finalize status (Activity)."""
    from .state import AgentRole, AgentStatus
    from .registry import get_registry

    agent = _load_state(state.get("agent"), fallback=state)
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
        "ok": bool(agent.qa_passed) or str(agent.status).upper() in {"PASSED", "DELIVERED"},
        "error": "" if agent.qa_passed else (agent.final_message or "")[:300],
    }


def _route_after_critique(state: LumenTGState) -> str:
    agent = state.get("agent") or {}
    qa = bool(agent.get("qa_passed")) if isinstance(agent, dict) else bool(state.get("ok"))
    attempts = int(state.get("attempts") or agent.get("attempts") or 0) if isinstance(agent, dict) else int(state.get("attempts") or 0)
    max_att = int(state.get("max_attempts") or 4)
    if qa:
        return "deliver"
    if attempts < max_att:
        return "repair"
    return "deliver"


def build_lumen_plugin_graph():
    """Build StateGraph with official Temporal Activity metadata on every heavy node."""
    from langgraph.graph import END, START, StateGraph

    g = StateGraph(LumenTGState)
    work_h = float(os.getenv("TEMPORAL_WORK_HOURS") or "6")
    plan_h = float(os.getenv("TEMPORAL_PLAN_HOURS") or "1")
    crit_h = float(os.getenv("TEMPORAL_CRITIQUE_HOURS") or "1")

    g.add_node("plan", _node_plan, metadata=_activity_meta(hours=plan_h, attempts=2))
    g.add_node("work", _node_work, metadata=_activity_meta(hours=work_h, attempts=3))
    g.add_node("critique", _node_critique, metadata=_activity_meta(hours=crit_h, attempts=2))
    g.add_node("repair", _node_repair, metadata=_activity_meta(hours=plan_h, attempts=2))
    g.add_node("deliver", _node_deliver, metadata=_activity_meta(hours=0.5, attempts=2))

    g.add_edge(START, "plan")
    g.add_edge("plan", "work")
    g.add_edge("work", "critique")
    g.add_conditional_edges("critique", _route_after_critique, {"repair": "repair", "deliver": "deliver"})
    g.add_edge("repair", "work")
    g.add_edge("deliver", END)
    return g


def build_plugin() -> Any:
    """LangGraphPlugin instance for Worker registration."""
    from temporalio.contrib.langgraph import LangGraphPlugin
    from temporalio.common import RetryPolicy

    return LangGraphPlugin(
        graphs={"lumen-generate": build_lumen_plugin_graph()},
        default_activity_options={
            "start_to_close_timeout": timedelta(hours=2),
            "retry_policy": RetryPolicy(maximum_attempts=3),
        },
    )


GRAPH_NAME = "lumen-generate"

__all__ = [
    "LumenTGState",
    "plugin_available",
    "build_lumen_plugin_graph",
    "build_plugin",
    "GRAPH_NAME",
]
