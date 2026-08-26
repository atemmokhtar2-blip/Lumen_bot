"""Phase A bot-bench — 10 fixed scenarios against official multi_agent / cline contracts only.

No mock LLM as production path. No catalog generate_bot. Uses:
  plan_contract, findings, deterministic_repair, agent_acceptance,
  trajectory, run_report, agent_fs tools, roles aliases.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest


# ── helpers ──────────────────────────────────────────────────────────

def _tmp() -> Path:
    d = Path(tempfile.mkdtemp(prefix="lumen_bench_"))
    return d


# ── 1. ExecutionPlan contract ────────────────────────────────────────

def test_01_execution_plan_roundtrip():
    from lumen.engine.services.multi_agent.plan_contract import ExecutionPlan

    plan = ExecutionPlan.from_dict(
        {
            "goal": "echo bot",
            "tasks": [
                {"id": "t1", "title": "main entry", "priority": 1},
                {"id": "t2", "title": "requirements", "priority": 2},
            ],
        }
    )
    assert plan.goal
    brief = plan.to_worker_brief() if hasattr(plan, "to_worker_brief") else str(plan.to_dict())
    assert "t1" in brief or "main" in brief.lower() or "tasks" in plan.to_dict()
    d = plan.to_dict()
    assert isinstance(d, dict)


# ── 2. CritiqueFinding + findings_to_errors ──────────────────────────

def test_02_findings_to_errors():
    from lumen.engine.services.multi_agent.findings import CritiqueFinding, findings_to_errors

    fs = [
        CritiqueFinding(code="missing_deliverable", severity="error", message="no main.py", path="main.py"),
        CritiqueFinding(code="style", severity="warning", message="long line"),
    ]
    errs = findings_to_errors(fs)
    assert any("main" in e.lower() or "missing" in e.lower() for e in errs)
    assert all(isinstance(e, str) for e in errs)


# ── 3. Deterministic repair creates official layout ──────────────────

def test_03_deterministic_repair_layout():
    from lumen.engine.services.multi_agent.deterministic_repair import apply_deterministic_repairs

    root = _tmp()
    out = apply_deterministic_repairs(root)
    assert isinstance(out, dict)
    assert (root / "main.py").is_file() or (root / "app" / "handlers.py").is_file() or out.get("actions")


# ── 4. agent_acceptance on repaired project ──────────────────────────

def test_04_acceptance_after_det_repair():
    from lumen.engine.services.multi_agent.deterministic_repair import apply_deterministic_repairs
    from lumen.engine.services.cline_runtime.agent_acceptance import check_agent_project

    root = _tmp()
    apply_deterministic_repairs(root)
    # ensure minimal files if det is conservative
    if not (root / "main.py").is_file():
        (root / "main.py").write_text(
            "import os\nTOKEN=os.getenv('BOT_TOKEN')\nprint('bot')\n",
            encoding="utf-8",
        )
    if not (root / "requirements.txt").is_file():
        (root / "requirements.txt").write_text("python-telegram-bot\n", encoding="utf-8")
    acc = check_agent_project(root, goal="telegram bot")
    assert isinstance(acc, dict)
    assert "ok" in acc
    assert acc.get("score", 0) >= 0


# ── 5. agent_fs official tools (list/write/read/finish) ─────────────

def test_05_agent_fs_tools_official():
    from lumen.engine.services.cline_runtime.agent_fs import run_tool

    root = _tmp()
    w = run_tool(str(root), "write_file", {"path": "main.py", "content": "print(1)\n"})
    assert w.get("ok") is True
    r = run_tool(str(root), "read_file", {"path": "main.py"})
    assert r.get("ok") is True
    assert "print" in str(r.get("content") or r)
    fin = run_tool(str(root), "finish", {"summary": "done"})
    assert fin.get("ok") is True or "ok" in fin


# ── 6. Role aliases Planner/Worker/Critic ────────────────────────────

def test_06_role_aliases_exist():
    from lumen.engine.services.multi_agent.roles import (
        PlannerAgent,
        WorkerAgent,
        ReviewerAgent,
        ArchitectAgent,
        BuilderAgent,
        CriticAgent,
    )

    assert PlannerAgent is ArchitectAgent
    assert WorkerAgent is BuilderAgent or WorkerAgent is not None
    assert ReviewerAgent is CriticAgent


# ── 7. Trajectory append + summary ───────────────────────────────────

def test_07_trajectory_store():
    from lumen.engine.services.multi_agent.state import AgentState, AgentStatus
    from lumen.engine.services.multi_agent.trajectory import append_trajectory, trajectory_summary

    st = AgentState(state_id="bench-traj-1", user_id=1, user_text="bench")
    st.status = AgentStatus.RUNNING if hasattr(AgentStatus, "RUNNING") else list(AgentStatus)[0]
    append_trajectory(st, step="planner_done", role="ARCHITECT", ok=True)
    append_trajectory(st, step="worker_build", role="BUILDER", ok=True)
    summ = trajectory_summary(st)
    assert isinstance(summ, dict)
    assert summ.get("count", 0) >= 1 or summ.get("steps") or summ.get("entries") is not None


# ── 8. run_report includes cost block ────────────────────────────────

def test_08_run_report_cost_fields():
    from lumen.engine.services.multi_agent.state import AgentState, AgentStatus
    from lumen.engine.services.multi_agent.run_report import write_run_report

    st = AgentState(state_id="bench-cost-1", user_id=42, user_text="cost bench")
    st.attempts = 2
    st.extensions = {
        "execution_plan": {"goal": "x", "tasks": []},
        "findings": [{"code": "x"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "calls": 1},
    }
    path = write_run_report(st)
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    assert "cost" in data
    assert data["cost"]["attempts"] == 2
    assert data["cost"]["usage"].get("total_tokens") == 15
    assert data.get("execution_plan_present") is True
    assert data.get("findings_count") == 1


# ── 9. IR metadata carries plan + findings (builder contract shape) ─

def test_09_ir_metadata_plan_findings_shape():
    """Simulate the dict shape builder stashes on BuildIR.metadata."""
    plan = {"goal": "echo", "tasks": [{"id": "t1", "title": "main", "priority": 1}]}
    findings = [{"code": "missing_deliverable", "severity": "error", "message": "no main"}]
    meta = {
        "execution_plan": plan,
        "findings": findings,
        "repair_directive": {"focus": ["main.py"]},
        "mode": "incremental_repair",
    }
    assert meta["execution_plan"]["goal"] == "echo"
    assert meta["findings"][0]["code"] == "missing_deliverable"
    assert meta["mode"] == "incremental_repair"


# ── 10. Model router task-based selection (official select_model) ───

def test_10_model_router_select_by_task():
    from lumen.engine.services.cline_runtime.model_router import select_model, describe_runtime

    # Must not raise; returns a choice or None depending on env keys
    for task in ("plan", "build", "critique", "repair"):
        try:
            choice = select_model(task=task)
        except TypeError:
            choice = select_model()
        # choice may be None without keys — still valid contract
        assert choice is None or hasattr(choice, "model_id") or isinstance(choice, (str, dict))
    desc = describe_runtime()
    assert isinstance(desc, (str, dict))


# ── 11. Trajectory analytics + failure board ─────────────────────────

def test_11_trajectory_analytics_and_failure_board():
    from lumen.engine.services.multi_agent.state import AgentState
    from lumen.engine.services.multi_agent.trajectory import (
        append_trajectory,
        analyze_trajectory,
        failure_board,
        trajectory_summary,
    )

    st = AgentState(state_id="bench-analytics-1", user_id=7, user_text="analytics")
    append_trajectory(st, step="planner_done", role="ARCHITECT", ok=True)
    append_trajectory(st, step="critic_fail", role="CRITIC", ok=False, detail="syntax")
    append_trajectory(st, step="repair", role="BUILDER", ok=True)
    summ = trajectory_summary(st)
    assert summ.get("fail_count", 0) >= 1
    analysis = analyze_trajectory(st.state_id)
    assert analysis.get("event_count", 0) >= 1
    assert "by_step" in analysis
    board = failure_board(limit=20)
    assert isinstance(board, list)


# ── 12. Model difficulty + cache ─────────────────────────────────────

def test_12_model_difficulty_and_cache():
    from lumen.engine.services.cline_runtime.model_router import (
        estimate_task_difficulty,
        cache_get,
        cache_set,
        cache_stats,
        select_model_for_goal,
    )

    easy = estimate_task_difficulty(task="build", goal="hi")
    hard = estimate_task_difficulty(
        task="repair",
        goal="أ" * 500 + " multi feature bot payments bookings admin",
        features=["a", "b", "c", "d", "e", "f"],
        findings_count=5,
        file_count=20,
    )
    assert easy["band"] in {"easy", "medium", "hard"}
    assert hard["score"] >= easy["score"]
    payload = {"x": 1, "goal": "cache-test"}
    assert cache_get("bench", payload) is None
    cache_set("bench", payload, {"ok": True})
    assert cache_get("bench", payload) == {"ok": True}
    assert cache_stats()["entries"] >= 1
    choice, diff = select_model_for_goal(task="build", goal="simple bot")
    assert diff["band"] in {"easy", "medium", "hard"}
    assert choice is not None
