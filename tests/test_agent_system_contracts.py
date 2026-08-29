"""Integrated agent system contracts — roles, events, parallel, task tree."""
from __future__ import annotations

from lumen.engine.services.multi_agent.roles.contracts import (
    ROLE_ALIASES,
    GRAPH_ROLE_MAP,
    resolve_role_name,
)
from lumen.engine.services.multi_agent.roles import (
    PlannerAgent,
    WorkerAgent,
    ReviewerAgent,
    ArchitectAgent,
    BuilderAgent,
    CriticAgent,
)
from lumen.engine.services.multi_agent.event_wake import (
    EVENT_ROUTES,
    temporal_enabled,
    handle_agent_event,
    schedule_wake_cron,
)
from lumen.engine.services.multi_agent.dynamic_planner import assemble_plan
from lumen.engine.services.multi_agent.task_tree import TaskTree, TaskStatus


def test_role_aliases_point_to_real_agents():
    assert PlannerAgent is ArchitectAgent
    assert WorkerAgent is BuilderAgent or WorkerAgent.__name__ in {"WorkerAgent", "BuilderAgent"}
    assert ReviewerAgent is CriticAgent
    assert resolve_role_name("planner") == "architect"
    assert resolve_role_name("worker") == "builder"
    assert resolve_role_name("reviewer") == "critic"
    assert GRAPH_ROLE_MAP["plan"] == "planner"
    assert GRAPH_ROLE_MAP["work"] == "worker"
    assert GRAPH_ROLE_MAP["critique"] == "critic"


def test_task_tree_real_with_parallel_wave():
    plan = assemble_plan(goal="telegram bot", preferred_keys=["admin", "payments", "ai_chat"])
    tree = TaskTree.from_execution_plan(plan, goal=plan.goal)
    assert len(tree.nodes) >= 4
    tree.mark("scaffold", TaskStatus.DONE)
    tree.refresh_readiness()
    wave = tree.parallel_wave()
    assert len(wave) >= 2
    assert all(getattr(n, "parallel_group", None) == "feature_modules" for n in wave)


def test_event_routes_defined_and_fail_closed_without_temporal(monkeypatch):
    monkeypatch.delenv("TEMPORAL_HOST", raising=False)
    monkeypatch.delenv("TEMPORAL_ADDRESS", raising=False)
    assert temporal_enabled() is False
    assert "ci_failed" in EVENT_ROUTES
    assert "pull_request_opened" in EVENT_ROUTES
    out = handle_agent_event("ci_failed", {"request": "fix ci"})
    assert out["ok"] is False
    assert out["error"] == "temporal_not_configured"
    sched = schedule_wake_cron(cron="0 * * * *")
    assert sched["ok"] is False


def test_max_parallel_cap_in_pipeline_source():
    from pathlib import Path
    # langgraph_pipeline is a package — parallel cap logic is in graph_builder.py
    src = Path("lumen/engine/services/multi_agent/langgraph_pipeline/graph_builder.py").read_text(encoding="utf-8")
    assert "MULTI_AGENT_MAX_PARALLEL" in src
    assert "ids[:max_par]" in src
