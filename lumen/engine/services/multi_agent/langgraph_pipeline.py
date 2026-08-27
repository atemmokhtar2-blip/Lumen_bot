"""Official LangGraph multi-agent pipeline — sole generate orchestration path.

  START → plan → schedule ⇄ work → critique → (repair|deliver|fail) → END

Worker nodes call ``coding_agent.run_coding_session`` (official Cline agent_loop),
not a shallow template path.
"""
from __future__ import annotations

import logging
import operator
import os
from pathlib import Path
from typing import Annotated, Any, Literal, Optional, TypedDict

from .state import AgentRole, AgentState, AgentStatus
from .task_tree import TaskStatus, TaskTree

logger = logging.getLogger(__name__)


def langgraph_available() -> bool:
    try:
        import langgraph  # noqa: F401
        from langgraph.graph import StateGraph  # noqa: F401
        return True
    except Exception:
        return False


def use_langgraph_pipeline() -> bool:
    try:
        from .production_policy import is_production
        if is_production():
            return True
    except Exception:
        pass
    flag = (os.getenv("MULTI_AGENT_LANGGRAPH") or "1").strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return False
    return langgraph_available()


def _max_attempts(state: AgentState) -> int:
    try:
        return max(1, min(8, int(os.environ.get("MULTI_AGENT_MAX_ATTEMPTS") or state.max_attempts or 4)))
    except ValueError:
        return 4


def _work_dir(state: AgentState, ctx: dict[str, Any]) -> Path:
    raw = ctx.get("work_dir") or (state.extensions or {}).get("work_dir") or state.generated_path or ""
    p = Path(str(raw) or ".")
    p.mkdir(parents=True, exist_ok=True)
    return p


def _load_tree(state: AgentState) -> TaskTree:
    raw = (state.extensions or {}).get("task_tree")
    if isinstance(raw, dict) and raw.get("nodes"):
        return TaskTree.from_dict(raw)
    return TaskTree(goal=(state.user_text or state.spec_request or "")[:2000])


def _save_tree(state: AgentState, tree: TaskTree) -> None:
    state.extensions = dict(state.extensions or {})
    state.extensions["task_tree"] = tree.to_dict()
    state.extensions["task_tree_summary"] = tree.summary()


def _run_named(registry: Any, name: str, state: AgentState, ctx: dict) -> AgentState:
    agent = None
    if registry is not None and hasattr(registry, "get"):
        agent = registry.get(name)
    if agent is None:
        try:
            from .registry import get_registry
            agent = get_registry().get(name)
        except Exception:
            agent = None
    if agent is None:
        logger.warning("missing agent %s", name)
        return state
    return agent.run(state, context=ctx)


class GraphState(TypedDict, total=False):
    agent: AgentState
    context: dict[str, Any]
    last_node: str
    active_task_ids: list[str]
    wave: int
    done: bool
    notes: Annotated[list[str], operator.add]


def _make_builder(registry: Any, board: Any):
    from langgraph.graph import END, START, StateGraph

    def node_plan(gs: GraphState) -> dict[str, Any]:
        state: AgentState = gs["agent"]
        ctx = dict(gs.get("context") or {})
        try:
            state.transition(AgentStatus.PLANNING, role=AgentRole.ORCHESTRATOR, force=True)
        except Exception:
            state.status = AgentStatus.PLANNING.value
        # Architect produces StrictSpec
        state = _run_named(registry, "architect", state, ctx)
        tree = _load_tree(state)
        if not tree.nodes or len(tree.nodes) <= 1:
            try:
                from .plan_contract import ExecutionPlan, build_plan_from_spec
                plan_raw = (state.extensions or {}).get("execution_plan") or state.strict_spec or {}
                feats = list(state.preferred_keys or []) or list((state.strict_spec or {}).get("features") or [])
                if isinstance(plan_raw, dict) and plan_raw.get("tasks"):
                    plan = ExecutionPlan(
                        goal=str(plan_raw.get("goal") or state.user_text or "")[:2000],
                        language=str(plan_raw.get("language") or "ar"),
                        tasks=list(plan_raw.get("tasks") or []),
                        constraints=list(plan_raw.get("constraints") or []),
                        features=list(plan_raw.get("features") or feats),
                    )
                    tree = TaskTree.from_execution_plan(plan, goal=plan.goal)
                else:
                    tree = TaskTree.default_bot_tree(
                        goal=state.user_text or state.spec_request or "telegram bot",
                        features=feats,
                    )
                    ep = build_plan_from_spec(
                        goal=state.user_text or state.spec_request or "",
                        features=feats,
                        language=str((state.strict_spec or {}).get("language") or "ar"),
                    )
                    state.extensions = dict(state.extensions or {})
                    if hasattr(ep, "to_dict"):
                        state.extensions["execution_plan"] = ep.to_dict()
            except Exception as exc:
                logger.exception("plan tree failed")
                state.record(AgentRole.ORCHESTRATOR, "task_tree_error", str(exc)[:200])
                tree = TaskTree.default_bot_tree(goal=state.user_text or "bot")
        _save_tree(state, tree)
        state.record(AgentRole.ORCHESTRATOR, "plan_tree", f"nodes={len(tree.nodes)-1}")
        try:
            board.put(state)
        except Exception:
            pass
        return {"agent": state, "last_node": "plan", "active_task_ids": [], "notes": []}

    def node_schedule(gs: GraphState) -> dict[str, Any]:
        state: AgentState = gs["agent"]
        tree = _load_tree(state)
        tree.refresh_readiness()
        wave = tree.parallel_wave()
        ids = [n.id for n in wave]
        for n in wave:
            tree.mark(n.id, TaskStatus.RUNNING)
        _save_tree(state, tree)
        state.record(AgentRole.ORCHESTRATOR, "schedule", f"wave={ids}")
        try:
            board.put(state)
        except Exception:
            pass
        return {"agent": state, "last_node": "schedule", "active_task_ids": ids, "wave": int(gs.get("wave") or 0) + 1}

    def node_work(gs: GraphState) -> dict[str, Any]:
        """Real Cline agent_loop per active task — Cursor-class coding session."""
        state: AgentState = gs["agent"]
        ctx = dict(gs.get("context") or {})
        tree = _load_tree(state)
        active = list(gs.get("active_task_ids") or [])
        if not active:
            ready = tree.ready_tasks()
            active = [ready[0].id] if ready else []
        try:
            state.transition(AgentStatus.BUILDING, role=AgentRole.ORCHESTRATOR, force=True)
        except Exception:
            state.status = AgentStatus.BUILDING.value

        work = _work_dir(state, ctx)
        notes: list[str] = []
        from .coding_agent import run_coding_session

        base_goal = (state.spec_request or state.user_text or "")[:4000]
        ir_hint = {
            "spec_request": base_goal,
            "preferred_keys": list(state.preferred_keys or []),
            "user_request": state.user_text,
            "metadata": dict(state.strict_spec or {}),
        }

        for tid in active:
            if tree.get(tid) is None:
                continue
            brief = tree.worker_brief(tid)
            state.extensions = dict(state.extensions or {})
            state.extensions["active_task_id"] = tid
            result = run_coding_session(
                work_dir=work,
                goal=base_goal,
                task_brief=brief,
                ir_hint=ir_hint,
                repair=bool((state.extensions or {}).get("repair_mode")),
            )
            if result.get("ok") or result.get("files_written"):
                tree.mark(tid, TaskStatus.DONE, result={
                    "files": result.get("files_written"),
                    "steps": result.get("steps"),
                    "stop": result.get("stop_reason"),
                })
                state.generated_path = str(work)
                state.build_success = True
                notes.append(f"{tid}:done:steps={result.get('steps')}")
            else:
                err = "; ".join(result.get("errors") or ["build_failed"])[:500]
                tree.mark(tid, TaskStatus.FAILED, error=err)
                state.build_errors = list(state.build_errors or []) + list(result.get("errors") or [])
                state.build_success = False
                notes.append(f"{tid}:failed")

        _save_tree(state, tree)
        ctx["work_dir"] = str(work)
        state.extensions["last_worker_notes"] = notes
        try:
            board.put(state)
        except Exception:
            pass
        return {"agent": state, "context": ctx, "last_node": "work", "active_task_ids": [], "notes": notes}

    def node_critique(gs: GraphState) -> dict[str, Any]:
        state: AgentState = gs["agent"]
        ctx = dict(gs.get("context") or {})
        tree = _load_tree(state)
        try:
            state.transition(AgentStatus.QA, role=AgentRole.ORCHESTRATOR, force=True)
        except Exception:
            state.status = AgentStatus.QA.value

        # Role critic (AST/static)
        state = _run_named(registry, "critic", state, ctx)

        # Official execution feedback (compile + import + pytest)
        try:
            from .execution_feedback import run_execution_feedback
            root = Path(state.generated_path) if state.generated_path else _work_dir(state, ctx)
            fb = run_execution_feedback(root)
            state.extensions = dict(state.extensions or {})
            state.extensions["execution_feedback"] = fb
            if not fb.get("ok"):
                state.qa_passed = False
                report = dict(state.qa_report or {})
                errs = list(report.get("errors") or [])
                for c in fb.get("checks") or []:
                    if not c.get("ok"):
                        errs.append(f"{c.get('name')}:{c.get('stderr') or c.get('error') or 'fail'}"[:300])
                report["errors"] = errs[:30]
                report["execution_feedback_ok"] = False
                state.qa_report = report
        except Exception:
            logger.exception("execution_feedback failed")

        # Anti-hallucination gate when available
        try:
            from lumen.engine.services.anti_hallucination.gate import analyze_project
            root = Path(state.generated_path) if state.generated_path else _work_dir(state, ctx)
            ah = analyze_project(root)
            state.extensions["anti_hallucination"] = {
                "ok": getattr(ah, "ok", None) if not isinstance(ah, dict) else ah.get("ok"),
            }
            if isinstance(ah, dict) and ah.get("ok") is False:
                state.qa_passed = False
            elif hasattr(ah, "ok") and not ah.ok:
                state.qa_passed = False
        except Exception:
            pass

        if not tree.is_complete() and not tree.has_unrecoverable_failures():
            state.qa_passed = False
            state.extensions["critique_reason"] = "task_tree_incomplete"
        elif tree.has_unrecoverable_failures():
            state.qa_passed = False
            state.extensions["critique_reason"] = "task_tree_unrecoverable"

        _save_tree(state, tree)
        try:
            board.put(state)
        except Exception:
            pass
        return {"agent": state, "last_node": "critique"}

    def node_repair(gs: GraphState) -> dict[str, Any]:
        state: AgentState = gs["agent"]
        ctx = dict(gs.get("context") or {})
        tree = _load_tree(state)
        state.attempts = int(state.attempts or 0) + 1
        reopened = tree.reopen_failed()
        state.extensions = dict(state.extensions or {})
        state.extensions["repair_mode"] = True
        state.record(AgentRole.ORCHESTRATOR, "repair", f"attempt={state.attempts} reopened={reopened}")

        # Full coding repair session on work dir
        try:
            from .coding_agent import run_coding_session
            work = Path(state.generated_path) if state.generated_path else _work_dir(state, ctx)
            findings = (state.qa_report or {}).get("errors") or state.build_errors or []
            brief = "Fix these errors:\n" + "\n".join(f"- {e}" for e in findings[:15])
            result = run_coding_session(
                work_dir=work,
                goal=state.user_text or state.spec_request or "",
                task_brief=brief,
                repair=True,
            )
            state.extensions["last_repair_session"] = {
                "ok": result.get("ok"),
                "steps": result.get("steps"),
                "errors": result.get("errors"),
            }
            if result.get("ok") or result.get("files_written"):
                state.generated_path = str(work)
                state.build_success = True
        except Exception:
            logger.exception("repair coding session failed")

        try:
            from .deterministic_repair import apply_deterministic_repairs
            root = Path(state.generated_path) if state.generated_path else _work_dir(state, ctx)
            apply_deterministic_repairs(root, extensions={"user_text": state.user_text})
        except Exception:
            pass

        try:
            state.transition(AgentStatus.PLANNING, role=AgentRole.ORCHESTRATOR, force=True)
        except Exception:
            state.status = AgentStatus.PLANNING.value
        state.qa_passed = False
        state.build_success = False
        _save_tree(state, tree)
        try:
            board.put(state)
        except Exception:
            pass
        return {"agent": state, "last_node": "repair", "active_task_ids": []}

    def node_deliver(gs: GraphState) -> dict[str, Any]:
        state: AgentState = gs["agent"]
        ctx = dict(gs.get("context") or {})
        state = _run_named(registry, "deliver", state, ctx)
        try:
            state.transition(AgentStatus.DELIVERED, role=AgentRole.ORCHESTRATOR, force=True)
        except Exception:
            state.status = AgentStatus.DELIVERED.value
        try:
            board.put(state)
        except Exception:
            pass
        return {"agent": state, "last_node": "deliver", "done": True}

    def node_fail(gs: GraphState) -> dict[str, Any]:
        state: AgentState = gs["agent"]
        ctx = dict(gs.get("context") or {})
        try:
            state.transition(AgentStatus.FAILED, role=AgentRole.ORCHESTRATOR, force=True)
        except Exception:
            state.status = AgentStatus.FAILED.value
        try:
            state = _run_named(registry, "deliver", state, ctx)
        except Exception:
            pass
        try:
            board.put(state)
        except Exception:
            pass
        return {"agent": state, "last_node": "fail", "done": True}

    def after_schedule(gs: GraphState) -> Literal["work", "critique"]:
        if list(gs.get("active_task_ids") or []):
            return "work"
        tree = _load_tree(gs["agent"])
        if tree.is_complete():
            return "critique"
        if tree.ready_tasks():
            return "work"
        return "critique"

    def after_work(gs: GraphState) -> Literal["schedule", "critique"]:
        tree = _load_tree(gs["agent"])
        tree.refresh_readiness()
        return "schedule" if tree.ready_tasks() else "critique"

    def after_critique(gs: GraphState) -> Literal["deliver", "repair", "schedule", "fail"]:
        state: AgentState = gs["agent"]
        tree = _load_tree(state)
        max_att = _max_attempts(state)
        if state.qa_passed and tree.is_complete():
            try:
                state.transition(AgentStatus.PASSED, role=AgentRole.ORCHESTRATOR, force=True)
            except Exception:
                state.status = AgentStatus.PASSED.value
            return "deliver"
        if tree.ready_tasks() and int(state.attempts or 0) < max_att:
            return "schedule"
        if int(state.attempts or 0) < max_att and (tree.failed_tasks() or not state.qa_passed):
            return "repair"
        return "fail"

    g = StateGraph(GraphState)
    g.add_node("plan", node_plan)
    g.add_node("schedule", node_schedule)
    g.add_node("work", node_work)
    g.add_node("critique", node_critique)
    g.add_node("repair", node_repair)
    g.add_node("deliver", node_deliver)
    g.add_node("fail", node_fail)
    g.add_edge(START, "plan")
    g.add_edge("plan", "schedule")
    g.add_conditional_edges("schedule", after_schedule, {"work": "work", "critique": "critique"})
    g.add_conditional_edges("work", after_work, {"schedule": "schedule", "critique": "critique"})
    g.add_conditional_edges(
        "critique", after_critique,
        {"deliver": "deliver", "repair": "repair", "schedule": "schedule", "fail": "fail"},
    )
    g.add_edge("repair", "schedule")
    g.add_edge("deliver", END)
    g.add_edge("fail", END)
    return g


def build_lumen_graph(registry: Any, board: Any):
    return _make_builder(registry, board).compile()


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
    from .blackboard import get_blackboard
    from .registry import get_registry

    reg = registry or get_registry()
    bd = board or get_blackboard()
    checkpointer = None
    if (os.getenv("MULTI_AGENT_CHECKPOINT") or "1").strip().lower() not in {"0", "false", "no", "off"}:
        try:
            from langgraph.checkpoint.memory import MemorySaver
            checkpointer = MemorySaver()
        except Exception:
            checkpointer = None
    builder = _make_builder(reg, bd)
    graph = builder.compile(checkpointer=checkpointer) if checkpointer else builder.compile()
    max_att = _max_attempts(state)
    state.max_attempts = max_att
    state.extensions = dict(state.extensions or {})
    state.extensions["orchestration"] = "langgraph+cline"
    state.record(AgentRole.ORCHESTRATOR, "langgraph_start", f"max_attempts={max_att}")
    cfg: dict[str, Any] = {"recursion_limit": max(40, max_att * 12)}
    if checkpointer:
        cfg["configurable"] = {"thread_id": thread_id or state.state_id or "lumen-default"}
    result = graph.invoke(
        {"agent": state, "context": dict(context or {}), "last_node": "", "active_task_ids": [], "wave": 0, "done": False, "notes": []},
        config=cfg,
    )
    out = result.get("agent") if isinstance(result, dict) else state
    if out is None:
        out = state
    out.extensions = dict(out.extensions or {})
    out.extensions["orchestration"] = "langgraph+cline"
    out.extensions["langgraph_last_node"] = result.get("last_node") if isinstance(result, dict) else ""
    try:
        bd.put(out)
    except Exception:
        pass
    return out


__all__ = [
    "build_lumen_graph",
    "langgraph_available",
    "run_langgraph_pipeline",
    "use_langgraph_pipeline",
    "GraphState",
]
