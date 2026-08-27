"""Single source of truth for durable agent stages (Temporal Activities).

Used by LumenSequentialGenerateWorkflow activities.
In-process langgraph_pipeline remains separate for non-Temporal runs;
these stage functions are the durable production implementations.
"""
from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def heartbeat(payload: dict[str, Any] | None = None) -> None:
    """Deprecated no-op from sync stage threads.

    Heartbeats must be issued from the async Activity coroutine
    (see temporal_defs lumen_stage_*), never from asyncio.to_thread workers.
    """
    return


def load_agent(state: dict[str, Any]):
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
        "orchestration": "temporal_sequential+cline",
        "durable_shell": "temporal",
    }
    return st


def stage_plan(state: dict[str, Any]) -> dict[str, Any]:
    from .state import AgentRole, AgentStatus
    from .registry import get_registry
    from .dynamic_planner import assemble_plan
    from .task_tree import TaskTree

    heartbeat({"phase": "plan_start", "state_id": str(state.get("state_id") or "")})
    work = str(state.get("work_dir") or ".")
    Path(work).mkdir(parents=True, exist_ok=True)
    agent = load_agent(state)
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
    agent.record(AgentRole.ORCHESTRATOR, "stage_plan", f"tasks={len(plan.tasks)}")
    summary = tree.summary() if hasattr(tree, "summary") else {"tasks": len(plan.tasks)}
    heartbeat({"phase": "plan_done", "tasks": len(plan.tasks)})
    return {
        "agent": agent.to_dict(),
        "status": agent.status,
        "attempts": int(agent.attempts or 0),
        "ok": True,
        "error": "",
        "plan_summary": str(summary)[:800],
    }


def stage_work(state: dict[str, Any]) -> dict[str, Any]:
    from .state import AgentRole, AgentStatus
    from .coding_agent import run_coding_session
    from .task_tree import TaskTree, TaskStatus
    from .acceptance_check import evaluate_task

    heartbeat({"phase": "work_start", "state_id": str(state.get("state_id") or "")})
    work = Path(str(state.get("work_dir") or "."))
    work.mkdir(parents=True, exist_ok=True)
    agent = load_agent(state)
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
    try:
        from .production_policy import max_parallel_workers
        cap = max_parallel_workers()
    except Exception:
        cap = max(1, min(8, int(os.getenv("MULTI_AGENT_MAX_PARALLEL") or "8")))

    if not ready:
        from .worktree_isolation import acquire_task_workspace, merge_task_workspace, release_task_workspace
        session = acquire_task_workspace(work, "full_goal", use_isolation=False)
        result = run_coding_session(
            work_dir=session.path,
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
        from .worktree_isolation import (
            acquire_task_workspace,
            merge_task_workspace,
            release_task_workspace,
            write_task_tree_disk,
            run_tasks_in_parallel,
        )
        wave = ready[:cap]
        # Isolate when parallel wave OR any parallel_group task
        multi = len(wave) > 1 or any(getattr(t, "parallel_group", "") for t in wave)

        def _runner(task, session):
            brief = tree.worker_brief(task.id)
            # Prefer on-disk task tree brief if present (planner → worker contract)
            try:
                from .worktree_isolation import read_task_tree_disk
                from .task_tree import TaskTree as _TT
                disk = read_task_tree_disk(work)
                if disk:
                    brief = _TT.from_dict(disk).worker_brief(task.id) or brief
            except Exception:
                pass
            from .context_views import worker_task_view
            acc = list(getattr(task, "acceptance", None) or [])
            files = list(getattr(task, "files", None) or [])
            wview = worker_task_view(
                goal=agent.spec_request or agent.user_text or "",
                task_brief=brief,
                target_files=files,
                constraints=list(
                    ((agent.extensions or {}).get("execution_plan") or {}).get("constraints")
                    or []
                )[:12],
            )
            brief = (wview.get("task_brief") or brief)
            result = run_coding_session(
                work_dir=session.path,
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
            if session.isolated:
                merge_task_workspace(session, owned_files=files)
            acc_rep = evaluate_task(work, files=files, acceptance=acc, strict=True)
            return {
                "ok": bool(acc_rep.get("ok")),
                "task_id": str(task.id),
                "acceptance": acc_rep,
                "steps": result.get("steps"),
                "errors": list(result.get("errors") or []),
                "files": files,
                "isolation": session.kind,
            }

        if multi:
            # Disjoint ownership → parallel; overlapping files → serial (Cursor rule)
            from .worktree_isolation import partition_wave_by_ownership, prune_worktrees
            parallel_safe, serial = partition_wave_by_ownership(wave)
            batch = []
            if parallel_safe:
                for t in parallel_safe:
                    tree.mark(t.id, TaskStatus.RUNNING)
                batch.extend(
                    run_tasks_in_parallel(work, parallel_safe, _runner, max_workers=cap)
                )
            for t in serial:
                tree.mark(t.id, TaskStatus.RUNNING)
                session = acquire_task_workspace(work, str(t.id), use_isolation=True)
                try:
                    batch.append(_runner(t, session))
                finally:
                    try:
                        release_task_workspace(session)
                    except Exception:
                        pass
            try:
                prune_worktrees(work)
            except Exception:
                pass
            for item in batch:
                tid = str(item.get("task_id") or "")
                if item.get("ok"):
                    tree.mark(
                        tid,
                        TaskStatus.DONE,
                        result={
                            "acceptance": item.get("acceptance"),
                            "steps": item.get("steps"),
                            "isolation": item.get("isolation"),
                        },
                    )
                    notes.append(f"{tid}:done:{item.get('isolation')}")
                else:
                    all_ok = False
                    fails = [
                        str(f.get("id") or f.get("detail") or "")
                        for f in ((item.get("acceptance") or {}).get("failed") or [])
                    ][:8]
                    err = "; ".join(list(item.get("errors") or []) + fails)[:400]
                    tree.mark(tid, TaskStatus.FAILED, error=err, result={"acceptance": item.get("acceptance")})
                    agent.build_errors = list(agent.build_errors or []) + fails
                    notes.append(f"{tid}:failed")
        else:
            task = wave[0]
            tree.mark(task.id, TaskStatus.RUNNING)
            session = acquire_task_workspace(
                work, str(task.id),
                use_isolation=bool(getattr(task, "parallel_group", "")),
            )
            out = _runner(task, session)
            try:
                release_task_workspace(session)
            except Exception:
                pass
            if out.get("ok"):
                tree.mark(
                    task.id,
                    TaskStatus.DONE,
                    result={
                        "acceptance": out.get("acceptance"),
                        "steps": out.get("steps"),
                        "isolation": out.get("isolation"),
                    },
                )
                notes.append(f"{task.id}:done:{out.get('isolation')}")
            else:
                all_ok = False
                fails = [
                    str(f.get("id") or f.get("detail") or "")
                    for f in ((out.get("acceptance") or {}).get("failed") or [])
                ][:8]
                err = "; ".join(list(out.get("errors") or []) + fails)[:400]
                tree.mark(task.id, TaskStatus.FAILED, error=err, result={"acceptance": out.get("acceptance")})
                agent.build_errors = list(agent.build_errors or []) + fails
                notes.append(f"{task.id}:failed")

        agent.extensions["task_tree"] = tree.to_dict()
        agent.extensions["task_tree_summary"] = tree.summary()
        try:
            write_task_tree_disk(work, tree.to_dict())
        except Exception:
            pass

    agent.generated_path = str(work)
    agent.build_success = all_ok or any(n.endswith(":done") for n in notes)
    agent.extensions["last_worker_notes"] = notes
    agent.record(AgentRole.BUILDER, "stage_work", f"notes={len(notes)}")
    heartbeat({"phase": "work_done", "ok": bool(agent.build_success)})
    return {
        "agent": agent.to_dict(),
        "status": agent.status,
        "attempts": agent.attempts,
        "ok": bool(agent.build_success),
        "error": "" if agent.build_success else ";".join(agent.build_errors or [])[:300],
    }


def stage_critique(state: dict[str, Any]) -> dict[str, Any]:
    from .state import AgentRole, AgentStatus
    from .registry import get_registry

    heartbeat({"phase": "critique_start", "state_id": str(state.get("state_id") or "")})
    work = str(state.get("work_dir") or ".")
    agent = load_agent(state)
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
        agent.qa_report = {"ok": agent.qa_passed, "engine": "stage_fallback"}

    agent.record(AgentRole.CRITIC, "stage_critique", f"qa={agent.qa_passed}")
    heartbeat({"phase": "critique_done", "qa": bool(agent.qa_passed)})
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


def stage_repair(state: dict[str, Any]) -> dict[str, Any]:
    from .state import AgentRole, AgentStatus
    from .repair import build_repair_directive
    from .repair_worker import should_incremental_repair, run_incremental_repair

    heartbeat({"phase": "repair_start", "state_id": str(state.get("state_id") or "")})
    work = Path(str(state.get("work_dir") or "."))
    agent = load_agent(state)
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

    agent.record(AgentRole.ORCHESTRATOR, "stage_repair", f"attempts={agent.attempts}")
    return {
        "agent": agent.to_dict(),
        "status": agent.status,
        "attempts": int(agent.attempts or 0),
        "ok": bool(agent.build_success),
        "error": "",
    }


def stage_deliver(state: dict[str, Any]) -> dict[str, Any]:
    from .state import AgentRole, AgentStatus
    from .registry import get_registry
    agent = load_agent(state)
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

    agent.record(AgentRole.ORCHESTRATOR, "stage_deliver", agent.status)
    return {
        "agent": agent.to_dict(),
        "status": agent.status,
        "attempts": int(agent.attempts or 0),
        "ok": bool(agent.qa_passed)
        or str(agent.status).upper() in {"PASSED", "DELIVERED"},
        "error": "" if agent.qa_passed else (agent.final_message or "")[:300],
    }


__all__ = [
    "heartbeat",
    "load_agent",
    "stage_plan",
    "stage_work",
    "stage_critique",
    "stage_repair",
    "stage_deliver",
]
