"""Official LangGraph pipeline wrapping existing multi_agent roles.

Does NOT re-architect: nodes call the same Architect/Builder/Critic agents
and the same repair helpers. Temporal / blackboard stay outside.

Requires: pip install langgraph langchain-core
"""
from __future__ import annotations

import logging
import os
from typing import Any, Literal, Optional, TypedDict

from .state import AgentRole, AgentState, AgentStatus

logger = logging.getLogger(__name__)


def langgraph_available() -> bool:
    try:
        import langgraph  # noqa: F401
        from langgraph.graph import StateGraph  # noqa: F401
        return True
    except Exception:
        return False


def use_langgraph_pipeline() -> bool:
    """LangGraph is the orchestration source of truth when available.

    Production (see production_policy): required — missing package is a hard error upstream.
    """
    try:
        from .production_policy import require_langgraph, is_production
        if require_langgraph():
            return langgraph_available() or is_production()  # True in prod even if missing → upstream fails hard
    except Exception:
        pass
    flag = (os.getenv("MULTI_AGENT_LANGGRAPH") or "auto").strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return False
    return langgraph_available()


class GraphState(TypedDict, total=False):
    """LangGraph state — holds AgentState + control flags."""
    agent: AgentState
    context: dict[str, Any]
    last_node: str
    done: bool


def _max_attempts(state: AgentState) -> int:
    try:
        env = int(os.environ.get("MULTI_AGENT_MAX_ATTEMPTS") or state.max_attempts or 4)
    except ValueError:
        env = 4
    return max(1, min(env, 8))


def _run_named(registry, name: str, state: AgentState, ctx: dict) -> AgentState:
    agent = registry.get(name) if hasattr(registry, "get") else None
    if agent is None:
        # fall back to registry.names lookup
        for a in getattr(registry, "agents", []) or []:
            if getattr(a, "name", "") == name or getattr(a, "role", "") == name:
                agent = a
                break
    if agent is None:
        try:
            from .registry import get_registry
            agent = get_registry().get(name)
        except Exception:
            agent = None
    if agent is None:
        logger.warning("langgraph node missing agent %s", name)
        return state
    return agent.run(state, context=ctx)


def build_lumen_graph(registry: Any, board: Any):
    """Compile StateGraph: plan → build → critique → (repair|deliver|fail)."""
    from langgraph.graph import END, StateGraph

    def node_plan(gs: GraphState) -> GraphState:
        state = gs["agent"]
        ctx = dict(gs.get("context") or {})
        try:
            state.transition(AgentStatus.PLANNING, role=AgentRole.ORCHESTRATOR, force=True)
        except Exception:
            state.status = AgentStatus.PLANNING.value
        state = _run_named(registry, "architect", state, ctx)
        try:
            from .trajectory import append_trajectory
            append_trajectory(state, step="planner_done", role="ARCHITECT", ok=True)
        except Exception:
            pass
        try:
            board.put(state)
        except Exception:
            pass
        return {"agent": state, "context": ctx, "last_node": "plan", "done": False}

    def node_build(gs: GraphState) -> GraphState:
        state = gs["agent"]
        ctx = dict(gs.get("context") or {})
        # Prefer builder with gate via Orchestrator helpers if available
        try:
            from .orchestrator import Orchestrator
            orch = Orchestrator(registry=registry, board=board)
            state = orch._builder_with_gate(state, ctx)
        except Exception:
            logger.exception("builder_with_gate failed; plain builder")
            state = _run_named(registry, "builder", state, ctx)
        try:
            from .trajectory import append_trajectory
            append_trajectory(
                state,
                step="worker_done",
                role="BUILDER",
                ok=bool(state.build_success),
                detail=(state.generated_path or "")[:120],
            )
        except Exception:
            pass
        try:
            board.put(state)
        except Exception:
            pass
        return {"agent": state, "context": ctx, "last_node": "build", "done": False}

    def node_critique(gs: GraphState) -> GraphState:
        state = gs["agent"]
        ctx = dict(gs.get("context") or {})
        if state.build_success and (state.generated_path or "").strip():
            state = _run_named(registry, "critic", state, ctx)
            try:
                from .trajectory import append_trajectory
                append_trajectory(
                    state,
                    step="critic_done",
                    role="CRITIC",
                    ok=bool(state.qa_passed),
                    payload={"errors": list((state.qa_report or {}).get("errors") or [])[:6]},
                )
            except Exception:
                pass
        else:
            state.qa_passed = False
            if not state.qa_report:
                state.qa_report = {
                    "ok": False,
                    "errors": list(state.build_errors or ["build_failed"]),
                    "attempt": state.attempts,
                }
        try:
            board.put(state)
        except Exception:
            pass
        return {"agent": state, "context": ctx, "last_node": "critique", "done": False}

    def node_repair(gs: GraphState) -> GraphState:
        state = gs["agent"]
        ctx = dict(gs.get("context") or {})
        from .repair import build_repair_directive, record_repair_history, spec_hash

        directive = build_repair_directive(state)
        hist = list((state.extensions or {}).get("repair_history") or [])
        cur_h = spec_hash(directive)
        state.extensions["last_repair"] = directive.to_dict()
        try:
            record_repair_history(state, directive, cur_h)
        except Exception:
            hist.append({"hash": cur_h})
            state.extensions["repair_history"] = hist[-20:]
        state.attempts = int(state.attempts or 0) + 1
        state.record(
            AgentRole.ORCHESTRATOR,
            "langgraph_repair",
            f"attempt={state.attempts} hash={cur_h[:12]}",
        )
        try:
            from .trajectory import append_trajectory
            append_trajectory(
                state,
                step="repair_scheduled",
                role="ORCHESTRATOR",
                ok=True,
                payload={"attempt": state.attempts},
            )
        except Exception:
            pass
        try:
            board.put(state)
        except Exception:
            pass
        return {"agent": state, "context": ctx, "last_node": "repair", "done": False}

    def node_deliver(gs: GraphState) -> GraphState:
        state = gs["agent"]
        try:
            from .orchestrator import Orchestrator
            orch = Orchestrator(registry=registry, board=board)
            state = orch._deliver(state)
        except Exception:
            logger.exception("deliver failed")
            try:
                state.transition(AgentStatus.DELIVERED, role=AgentRole.ORCHESTRATOR, force=True)
            except Exception:
                state.status = AgentStatus.DELIVERED.value
        return {"agent": state, "context": gs.get("context") or {}, "last_node": "deliver", "done": True}

    def node_fail(gs: GraphState) -> GraphState:
        state = gs["agent"]
        try:
            state.transition(AgentStatus.FAILED, role=AgentRole.ORCHESTRATOR, force=True)
        except Exception:
            state.status = AgentStatus.FAILED.value
        state.record(AgentRole.ORCHESTRATOR, "langgraph_fail", f"attempts={state.attempts}")
        try:
            from .orchestrator import Orchestrator
            orch = Orchestrator(registry=registry, board=board)
            state = orch._deliver(state)
        except Exception:
            pass
        return {"agent": state, "context": gs.get("context") or {}, "last_node": "fail", "done": True}

    def after_critique(gs: GraphState) -> Literal["deliver", "repair", "fail"]:
        state = gs["agent"]
        if state.qa_passed:
            return "deliver"
        max_att = _max_attempts(state)
        # attempts counted on repair; if already at limit, fail
        if int(state.attempts or 0) >= max_att:
            return "fail"
        # production: no silent verified template — repair or fail only
        strict = (os.getenv("MULTI_AGENT_STRICT") or os.getenv("ENVIRONMENT") or "").strip().lower()
        if strict in {"production", "prod", "1", "true", "strict"}:
            if int(state.attempts or 0) >= max_att - 0:
                # still allow repair until max
                pass
        return "repair"

    g = StateGraph(GraphState)
    g.add_node("plan", node_plan)
    g.add_node("build", node_build)
    g.add_node("critique", node_critique)
    g.add_node("repair", node_repair)
    g.add_node("deliver", node_deliver)
    g.add_node("fail", node_fail)

    g.set_entry_point("plan")
    g.add_edge("plan", "build")
    g.add_edge("build", "critique")
    g.add_conditional_edges(
        "critique",
        after_critique,
        {"deliver": "deliver", "repair": "repair", "fail": "fail"},
    )
    g.add_edge("repair", "plan")  # closed loop: re-plan with repair context
    g.add_edge("deliver", END)
    g.add_edge("fail", END)

    return g.compile()


def run_langgraph_pipeline(
    state: AgentState,
    *,
    context: Optional[dict[str, Any]] = None,
    registry: Any = None,
    board: Any = None,
) -> AgentState:
    """Execute official LangGraph pipeline; returns updated AgentState."""
    if not langgraph_available():
        raise RuntimeError("langgraph_not_installed: pip install langgraph langchain-core")

    from .registry import get_registry
    from .blackboard import get_blackboard

    reg = registry or get_registry()
    bd = board or get_blackboard()
    graph = build_lumen_graph(reg, bd)
    max_att = _max_attempts(state)
    state.max_attempts = max_att
    state.extensions = dict(state.extensions or {})
    state.extensions["orchestration"] = "langgraph"
    state.record(
        AgentRole.ORCHESTRATOR,
        "langgraph_start",
        f"max_attempts={max_att}",
    )
    result = graph.invoke(
        {
            "agent": state,
            "context": dict(context or {}),
            "last_node": "",
            "done": False,
        },
        config={"recursion_limit": max(20, max_att * 6)},
    )
    out = result.get("agent") if isinstance(result, dict) else state
    if out is None:
        out = state
    out.extensions = dict(out.extensions or {})
    out.extensions["orchestration"] = "langgraph"
    out.extensions["langgraph_last_node"] = (
        result.get("last_node") if isinstance(result, dict) else ""
    )
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
]
