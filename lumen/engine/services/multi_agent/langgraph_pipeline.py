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

from .state import AgentRole, AgentState, AgentStatus
from .task_tree import TaskStatus, TaskTree

logger = logging.getLogger(__name__)
_TREE_LOCK = threading.Lock()

# Process-wide checkpointer so interrupt → resume works across calls (official MemorySaver).
_SHARED_CHECKPOINTER = None


def _checkpoint_db_path() -> Path:
    raw = (os.getenv("LANGGRAPH_CHECKPOINT_PATH") or "").strip()
    if raw:
        return Path(raw)
    base = (os.getenv("OUTPUT_DIR") or os.getenv("LUMEN_OUTPUT_DIR") or "/tmp/lumen_output").strip()
    return Path(base) / "langgraph_checkpoints.sqlite"


def _shared_checkpointer():
    """Official durable checkpointer: SqliteSaver first, MemorySaver fallback.

    Sqlite is process+restart durable (same machine). Required for real HITL resume
    after worker restart — Memory alone is not world-class.
    """
    global _SHARED_CHECKPOINTER
    if _SHARED_CHECKPOINTER is not None:
        return _SHARED_CHECKPOINTER
    if (os.getenv("MULTI_AGENT_CHECKPOINT") or "1").strip().lower() in {"0", "false", "no", "off"}:
        return None
    # Prefer official SqliteSaver
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
        import sqlite3
        db = _checkpoint_db_path()
        db.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db), check_same_thread=False)
        if hasattr(SqliteSaver, "from_conn"):
            _SHARED_CHECKPOINTER = SqliteSaver.from_conn(conn)
        else:
            _SHARED_CHECKPOINTER = SqliteSaver(conn)
        logger.info("LangGraph SqliteSaver at %s", db)
        return _SHARED_CHECKPOINTER
    except Exception as exc:
        logger.warning("SqliteSaver unavailable (%s) — trying MemorySaver", exc)
    try:
        from langgraph.checkpoint.memory import MemorySaver
        _SHARED_CHECKPOINTER = MemorySaver()
        logger.warning("LangGraph using MemorySaver (not durable across process restart)")
        return _SHARED_CHECKPOINTER
    except Exception as exc:
        logger.warning("No checkpointer: %s", exc)
        return None


def hitl_deliver_enabled() -> bool:
    """Second HITL gate before deliver when QA passed (default off)."""
    import os
    return (os.getenv("MULTI_AGENT_HITL_DELIVER") or "0").strip().lower() in {"1", "true", "yes", "on"}


def hitl_interrupt_enabled() -> bool:

    """Official LangGraph interrupt after plan. Default ON when langgraph available."""
    flag = (os.getenv("MULTI_AGENT_LANGGRAPH_HITL") or "1").strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return False
    return langgraph_available()


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



def _merge_agent_state(left: AgentState | None, right: AgentState | None) -> AgentState:
    """Reducer for parallel LangGraph Send — merge task trees without dropping DONE marks."""
    if left is None:
        return right  # type: ignore
    if right is None:
        return left
    try:
        lext = dict(left.extensions or {})
        rext = dict(right.extensions or {})
        lt = TaskTree.from_dict(lext.get("task_tree") or {})
        rt = TaskTree.from_dict(rext.get("task_tree") or {})
        # Prefer terminal statuses from either side
        for nid, node in rt.nodes.items():
            if nid not in lt.nodes:
                lt.nodes[nid] = node
                continue
            cur = lt.nodes[nid]
            # DONE/FAILED from right wins; RUNNING only if left still pending
            if node.status in {TaskStatus.DONE.value, TaskStatus.FAILED.value, TaskStatus.SKIPPED.value}:
                lt.nodes[nid] = node
            elif cur.status in {TaskStatus.PENDING.value, TaskStatus.READY.value} and node.status == TaskStatus.RUNNING.value:
                lt.nodes[nid] = node
        lext["task_tree"] = lt.to_dict()
        lext["task_tree_summary"] = lt.summary()
        # merge notes-like extension keys
        for k in ("last_worker_notes", "plan_intent"):
            lv = lext.get(k)
            rv = rext.get(k)
            if isinstance(lv, list) and isinstance(rv, list):
                lext[k] = list(lv) + [x for x in rv if x not in lv]
            elif rv and not lv:
                lext[k] = rv
        left.extensions = lext
        if right.generated_path:
            left.generated_path = right.generated_path
        if right.build_success:
            left.build_success = True
        if right.build_errors:
            left.build_errors = list(left.build_errors or []) + list(right.build_errors or [])
        if right.qa_passed:
            left.qa_passed = True
        if right.qa_report:
            left.qa_report = right.qa_report
        # prefer more advanced status
        order = ["pending", "planning", "building", "awaiting_confirmation", "passed", "delivered", "failed"]
        try:
            if order.index(str(right.status).lower()) >= order.index(str(left.status).lower()):
                left.status = right.status
        except ValueError:
            if right.status:
                left.status = right.status
        return left
    except Exception:
        logger.exception("merge_agent_state failed — preferring right")
        return right


def _merge_context(left: dict | None, right: dict | None) -> dict:
    out = dict(left or {})
    out.update(dict(right or {}))
    return out


class GraphState(TypedDict, total=False):
    agent: Annotated[AgentState, _merge_agent_state]
    context: Annotated[dict[str, Any], _merge_context]
    last_node: str
    active_task_ids: list[str]
    wave: int
    done: bool
    notes: Annotated[list[str], operator.add]
    hitl_decision: str  # approved | rejected | ""
    isolate: bool  # parallel worktree isolation for this wave


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
                from .dynamic_planner import assemble_plan
                from .plan_contract import ExecutionPlan
                work = str(ctx.get("work_dir") or (state.extensions or {}).get("work_dir") or "")
                feats = list(state.preferred_keys or []) or list((state.strict_spec or {}).get("features") or [])
                plan_raw = (state.extensions or {}).get("execution_plan")
                # Prefer architect-produced plan only if it has real multi-task structure
                if isinstance(plan_raw, dict) and len(list(plan_raw.get("tasks") or [])) >= 2:
                    plan = ExecutionPlan.from_dict(plan_raw)
                    if not plan.goal:
                        plan.goal = (state.user_text or state.spec_request or "")[:2000]
                else:
                    plan = assemble_plan(
                        goal=state.user_text or state.spec_request or "",
                        preferred_keys=feats,
                        constraints=list((state.strict_spec or {}).get("constraints") or []) if isinstance(state.strict_spec, dict) else [],
                        language=str((state.strict_spec or {}).get("language") or "ar") if isinstance(state.strict_spec, dict) else "ar",
                        work_dir=work or None,
                    )
                state.extensions = dict(state.extensions or {})
                state.extensions["execution_plan"] = plan.to_dict()
                state.extensions["plan_intent"] = [
                    c for c in (plan.constraints or []) if str(c).startswith("intent:") or str(c).startswith("platform:")
                ]
                tree = TaskTree.from_execution_plan(plan, goal=plan.goal)
            except Exception as exc:
                logger.exception("plan tree failed")
                state.record(AgentRole.ORCHESTRATOR, "task_tree_error", str(exc)[:200])
                tree = TaskTree.default_bot_tree(goal=state.user_text or "bot", work_dir=str(ctx.get("work_dir") or ""))
        _save_tree(state, tree)
        state.record(AgentRole.ORCHESTRATOR, "plan_tree", f"nodes={len(tree.nodes)-1}")
        try:
            board.put(state)
        except Exception:
            pass
        return {"agent": state, "last_node": "plan", "active_task_ids": [], "notes": []}

    def node_schedule(gs: GraphState) -> dict[str, Any]:
        """Select next wave with ownership exclusivity (Cursor worktree rule).

        Only tasks scheduled THIS turn are marked RUNNING. Contested-file tasks
        stay ready for a later serial turn — never stuck RUNNING without a worker.
        """
        state: AgentState = gs["agent"]
        ctx = dict(gs.get("context") or {})
        tree = _load_tree(state)
        tree.refresh_readiness()
        wave = tree.parallel_wave()
        try:
            from .production_policy import max_parallel_workers
            max_par = max_parallel_workers()
        except Exception:
            try:
                max_par = max(1, min(32, int(os.getenv("MULTI_AGENT_MAX_PARALLEL") or "8")))
            except ValueError:
                max_par = 8

        isolate = False
        ids: list[str] = []
        if not wave:
            ids = []
        elif len(wave) == 1:
            ids = [wave[0].id]
            tree.mark(wave[0].id, TaskStatus.RUNNING)
            isolate = bool(getattr(wave[0], "parallel_group", "") or "")
        else:
            from .worktree_isolation import partition_wave_by_ownership, snapshot_base_commit
            safe, serial = partition_wave_by_ownership(wave)
            batch = list(safe)[:max_par] if safe else list(serial)[:1]
            for n in batch:
                tree.mark(n.id, TaskStatus.RUNNING)
            ids = [n.id for n in batch]
            isolate = len(batch) > 1 or bool(safe)
            try:
                work = _work_dir(state, ctx)
                snapshot_base_commit(work)
            except Exception:
                pass

        _save_tree(state, tree)
        state.record(
            AgentRole.ORCHESTRATOR,
            "schedule",
            f"wave={ids} isolate={isolate} ready_left={len(tree.ready_tasks())}",
        )
        try:
            board.put(state)
        except Exception:
            pass
        if isolate:
            ctx["isolate"] = True
            ctx["parallel_wave"] = True
        return {
            "agent": state,
            "context": ctx,
            "last_node": "schedule",
            "active_task_ids": ids,
            "wave": int(gs.get("wave") or 0) + 1,
            "isolate": isolate,
        }

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
            # Reload tree under lock so parallel Send workers see latest marks
            with _TREE_LOCK:
                tree = _load_tree(state)
                task = tree.get(tid)
                if task is None:
                    continue
                brief = tree.worker_brief(tid)
                _acc = list(getattr(task, "acceptance", None) or [])
                _files = list(getattr(task, "files", None) or [])
            state.extensions = dict(state.extensions or {})
            state.extensions["active_task_id"] = tid
            # Isolate when schedule/Send marked isolate OR task in parallel_group
            use_iso = bool(
                gs.get("isolate")
                or ctx.get("isolate")
                or ctx.get("parallel_wave")
                or getattr(task, "parallel_group", "")
            )
            session_dir = work
            _wt_session = None
            if use_iso:
                from .worktree_isolation import (
                    acquire_task_workspace,
                    prune_worktrees,
                )
                # Base snapshot is done once in node_schedule — not per Send worker
                _wt_session = acquire_task_workspace(work, tid, use_isolation=True)
                if _wt_session.errors or _wt_session.kind not in {"worktree", "copy"}:
                    # Isolation required but unavailable — fail task (no silent main writes)
                    with _TREE_LOCK:
                        tree = _load_tree(state)
                        tree.mark(
                            tid,
                            TaskStatus.FAILED,
                            error=";".join(_wt_session.errors or ["isolation_unavailable"]),
                        )
                        _save_tree(state, tree)
                    notes.append(f"{tid}:failed:isolation")
                    continue
                session_dir = _wt_session.path
            _constraints = list(((state.extensions or {}).get("execution_plan") or {}).get("constraints") or [])[:12]
            result = run_coding_session(
                acceptance=_acc,
                target_files=_files,
                work_dir=session_dir,
                goal=base_goal,
                task_brief=brief,
                ir_hint=ir_hint,
                repair=bool((state.extensions or {}).get("repair_mode")),
                constraints=_constraints,
            )
            # Merge isolation → work for declared task files (worktree or copy)
            if use_iso and _wt_session is not None:
                from .worktree_isolation import merge_task_workspace, release_task_workspace
                merge_rep = merge_task_workspace(
                    _wt_session, owned_files=list(_files or []), strict=True
                )
                result["merge_conflicts"] = list(merge_rep.get("conflicts") or [])
                result["merge_missing"] = list(merge_rep.get("missing") or [])
                result["isolation_kind"] = merge_rep.get("kind")
                if not merge_rep.get("ok"):
                    result["ok"] = False
                    result.setdefault("errors", []).append(
                        "merge_incomplete:" + ",".join(merge_rep.get("missing") or [])[:200]
                    )
                try:
                    release_task_workspace(_wt_session)
                except Exception:
                    pass
                try:
                    prune_worktrees(work)
                except Exception:
                    pass
                from .acceptance_check import evaluate_task
                acc_merged = evaluate_task(work, files=_files, acceptance=_acc, strict=True)
                result["acceptance_report"] = acc_merged
                if not acc_merged.get("ok"):
                    result["ok"] = False
                if not result.get("ok"):
                    result["ok"] = False
            # Professional gate: NEVER trust worker self-reported acceptance alone
            from .acceptance_check import evaluate_task
            acc_rep = evaluate_task(work, files=_files, acceptance=_acc, strict=True)
            result["acceptance_report"] = acc_rep
            # session ok requires real acceptance on work_dir (ignore worker lie)
            session_ok = bool(acc_rep.get("ok"))
            with _TREE_LOCK:
                tree = _load_tree(state)
                if session_ok:
                    tree.mark(tid, TaskStatus.DONE, result={
                        "files": result.get("files_written"),
                        "steps": result.get("steps"),
                        "stop": result.get("stop_reason"),
                        "acceptance": acc_rep,
                    })
                    state.generated_path = str(work)
                    state.build_success = True
                    notes.append(f"{tid}:done:steps={result.get('steps')}")
                else:
                    fails = [f.get("id") or f.get("detail") for f in (acc_rep.get("failed") or [])][:8]
                    err = "; ".join(
                        list(result.get("errors") or []) + [f"acceptance:{x}" for x in fails] or ["build_or_acceptance_failed"]
                    )[:500]
                    tree.mark(tid, TaskStatus.FAILED, error=err, result={"acceptance": acc_rep})
                    state.build_errors = list(state.build_errors or []) + list(result.get("errors") or []) + fails
                    state.build_success = False
                    notes.append(f"{tid}:failed:{err[:80]}")
                _save_tree(state, tree)
                try:
                    board.put(state)
                except Exception:
                    pass

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
        # Ensure acceptance layer ran (even if critic role is thin)
        if not (state.extensions or {}).get("acceptance_report"):
            try:
                from .acceptance_check import evaluate_tree
                from .task_tree import TaskTree
                work = _work_dir(state, ctx)
                tree = _load_tree(state)
                acc = evaluate_tree(work, tree)
                state.extensions = dict(state.extensions or {})
                state.extensions["acceptance_report"] = acc
                if not acc.get("ok"):
                    state.qa_passed = False
            except Exception:
                logger.exception("acceptance in critique node failed")


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
            # Require real acceptance — files_written alone is not success
            try:
                from .acceptance_check import evaluate_task
                _rep = evaluate_task(work, files=["main.py"], acceptance=["main.py exists", "compileall passes"], strict=True)
                result["acceptance_report"] = _rep
                if _rep.get("ok"):
                    state.generated_path = str(work)
                    state.build_success = True
                else:
                    state.build_success = False
            except Exception:
                if result.get("ok"):
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

    
    def node_human_deliver_gate(gs: GraphState) -> dict[str, Any]:
        """Optional HITL before deliver — approve generated project."""
        from langgraph.types import interrupt
        state: AgentState = gs["agent"]
        payload = {
            "type": "approve_deliver",
            "state_id": state.state_id,
            "goal": (state.user_text or "")[:500],
            "path": state.generated_path or "",
            "qa_passed": bool(state.qa_passed),
            "message": "Approve delivery of the generated project?",
        }
        state.extensions = dict(state.extensions or {})
        state.extensions["hitl_pending"] = payload
        state.extensions["hitl_status"] = "awaiting_deliver_approval"
        decision = interrupt(payload)
        decision_s = str(decision or "").strip().lower()
        if isinstance(decision, dict):
            decision_s = str(decision.get("decision") or decision.get("value") or decision).strip().lower()
        approved = decision_s in {"1", "true", "yes", "y", "approve", "approved", "ok"}
        state.extensions["hitl_status"] = "deliver_approved" if approved else "deliver_rejected"
        state.extensions["hitl_decision"] = "approved" if approved else "rejected"
        return {
            "agent": state,
            "last_node": "human_deliver_gate",
            "hitl_decision": "approved" if approved else "rejected",
            "notes": [f"hitl_deliver:{'approved' if approved else 'rejected'}"],
        }

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

    def after_schedule(gs: GraphState):
        """Fan-out parallel_group / disjoint tasks via official LangGraph Send."""
        ids = list(gs.get("active_task_ids") or [])
        tree = _load_tree(gs["agent"])
        if not ids:
            if tree.is_complete():
                return "critique"
            wave = tree.parallel_wave()
            if not wave:
                ready = tree.ready_tasks()
                if not ready:
                    return "critique"
                ids = [ready[0].id]
            else:
                ids = [n.id for n in wave]
                # ensure schedule marked them running
                for n in wave:
                    if n.status != "running":
                        tree.mark(n.id, "running")
                _save_tree(gs["agent"], tree)

        parallel = (os.getenv("MULTI_AGENT_PARALLEL") or "1").strip().lower() not in {"0", "false", "no", "off"}
        try:
            from .production_policy import max_parallel_workers
            max_par = max_parallel_workers()
        except Exception:
            try:
                max_par = max(1, min(32, int(os.getenv("MULTI_AGENT_MAX_PARALLEL") or "8")))
            except ValueError:
                max_par = 8
        if parallel and len(ids) > 1:
            ids = ids[:max_par]
            try:
                from langgraph.types import Send
                base_ctx = dict(gs.get("context") or {})
                base_ctx["isolate"] = True
                base_ctx["parallel_wave"] = True
                return [
                    Send(
                        "work",
                        {
                            "agent": gs["agent"],
                            "context": dict(base_ctx),
                            "last_node": "schedule",
                            "active_task_ids": [tid],
                            "wave": int(gs.get("wave") or 0),
                            "done": False,
                            "notes": [],
                            "hitl_decision": str(gs.get("hitl_decision") or ""),
                            "isolate": True,
                        },
                    )
                    for tid in ids
                ]
            except Exception as exc:
                logger.warning("Send fan-out failed (%s) — sequential work", exc)
        return "work"

    def after_work(gs: GraphState) -> Literal["schedule", "critique"]:
        tree = _load_tree(gs["agent"])
        tree.refresh_readiness()
        return "schedule" if tree.ready_tasks() else "critique"

    def after_critique(gs: GraphState) -> Literal["deliver", "human_deliver_gate", "repair", "schedule", "fail"]:
        state: AgentState = gs["agent"]
        tree = _load_tree(state)
        max_att = _max_attempts(state)
        if state.qa_passed and tree.is_complete():
            try:
                state.transition(AgentStatus.PASSED, role=AgentRole.ORCHESTRATOR, force=True)
            except Exception:
                state.status = AgentStatus.PASSED.value
            # Real deliver HITL — was dead (always returned "deliver")
            if hitl_deliver_enabled():
                return "human_deliver_gate"
            return "deliver"
        if tree.ready_tasks() and int(state.attempts or 0) < max_att:
            return "schedule"
        if int(state.attempts or 0) < max_att and (tree.failed_tasks() or not state.qa_passed):
            return "repair"
        return "fail"

    def node_human_gate(gs: GraphState) -> dict[str, Any]:
        """Official LangGraph interrupt — pause for human plan approval."""
        from langgraph.types import interrupt

        state: AgentState = gs["agent"]
        tree = _load_tree(state)
        payload = {
            "type": "approve_plan",
            "state_id": state.state_id,
            "goal": (state.user_text or state.spec_request or "")[:500],
            "task_tree": tree.summary() if hasattr(tree, "summary") else {},
            "attempts": int(state.attempts or 0),
            "message": "Approve the execution plan to continue building?",
        }
        state.extensions = dict(state.extensions or {})
        state.extensions["hitl_pending"] = payload
        state.extensions["hitl_status"] = "awaiting_approval"
        try:
            state.transition(AgentStatus.AWAITING_CONFIRMATION, role=AgentRole.ORCHESTRATOR, force=True)
        except Exception:
            try:
                state.status = AgentStatus.AWAITING_CONFIRMATION.value
            except Exception:
                state.status = AgentStatus.AWAITING_CONFIRMATION.value
        # interrupt pauses here; resume value becomes decision
        decision = interrupt(payload)
        decision_s = str(decision or "").strip().lower()
        if isinstance(decision, dict):
            decision_s = str(decision.get("decision") or decision.get("value") or decision).strip().lower()
        approved = decision_s in {"1", "true", "yes", "y", "approve", "approved", "ok", "confirm"}
        state.extensions["hitl_status"] = "approved" if approved else "rejected"
        state.extensions["hitl_decision"] = decision_s
        state.record(
            AgentRole.ORCHESTRATOR,
            "hitl_decision",
            "approved" if approved else f"rejected:{decision_s[:40]}",
        )
        if not approved:
            state.final_message = state.final_message or "تم رفض الخطة من المستخدم (HITL)"
            try:
                state.transition(AgentStatus.FAILED, role=AgentRole.ORCHESTRATOR, force=True)
            except Exception:
                state.status = AgentStatus.FAILED.value
        else:
            try:
                state.transition(AgentStatus.BUILDING, role=AgentRole.ORCHESTRATOR, force=True)
            except Exception:
                pass
        return {
            "agent": state,
            "last_node": "human_gate",
            "hitl_decision": "approved" if approved else "rejected",
            "notes": [f"hitl:{'approved' if approved else 'rejected'}"],
        }

    def after_plan(gs: GraphState) -> Literal["human_gate", "schedule"]:
        if hitl_interrupt_enabled():
            return "human_gate"
        return "schedule"

    def after_human_gate(gs: GraphState) -> Literal["schedule", "fail"]:
        d = str(gs.get("hitl_decision") or "").lower()
        if d == "approved":
            return "schedule"
        # also check state
        st: AgentState = gs["agent"]
        status = str((st.extensions or {}).get("hitl_status") or "")
        if status in {"approved", "deliver_approved"}:
            return "schedule"
        return "fail"

    g = StateGraph(GraphState)
    g.add_node("plan", node_plan)
    g.add_node("human_gate", node_human_gate)
    g.add_node("schedule", node_schedule)
    g.add_node("work", node_work)
    g.add_node("critique", node_critique)
    g.add_node("repair", node_repair)
    g.add_node("human_deliver_gate", node_human_deliver_gate)
    g.add_node("deliver", node_deliver)
    g.add_node("fail", node_fail)
    g.add_edge(START, "plan")
    g.add_conditional_edges("plan", after_plan, {"human_gate": "human_gate", "schedule": "schedule"})
    g.add_conditional_edges("human_gate", after_human_gate, {"schedule": "schedule", "fail": "fail"})
    g.add_conditional_edges("schedule", after_schedule, {"work": "work", "critique": "critique"})
    g.add_conditional_edges("work", after_work, {"schedule": "schedule", "critique": "critique"})
    g.add_conditional_edges(
        "critique", after_critique,
        {"deliver": "deliver", "human_deliver_gate": "human_deliver_gate", "repair": "repair", "schedule": "schedule", "fail": "fail"},
    )
    g.add_edge("repair", "schedule")
    g.add_conditional_edges(
        "human_deliver_gate",
        lambda gs: "deliver" if str(gs.get("hitl_decision") or "").lower() in {"approved", "approve", "yes", "1"} else "fail",
        {"deliver": "deliver", "fail": "fail"},
    )
    g.add_edge("deliver", END)
    g.add_edge("fail", END)
    return g


def build_lumen_graph(registry: Any, board: Any):
    return _make_builder(registry, board).compile()


def _compile_graph(registry: Any, board: Any):
    builder = _make_builder(registry, board)
    cp = _shared_checkpointer()
    if cp is not None:
        return builder.compile(checkpointer=cp), cp
    return builder.compile(), None


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
            from .hitl import request_confirmation
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
            out.final_message = (
                f"{header}\n"
                f"الهدف: {(out.user_text or '')[:180]}\n"
                f"المعرّف: `{pending.action_id}`\n"
                f"للتأكيد: `تأكيد {pending.action_id} {pending.confirm_token}`\n"
                f"للرفض: `رفض {pending.action_id}`\n"
                f"thread: `{tid}`"
            )
        except Exception as _hitl_exc:
            logger.warning("attach pending_action failed: %s", _hitl_exc)
            out.final_message = out.final_message or "بانتظار موافقة HITL (LangGraph)"
    try:
        bd.put(out)
    except Exception:
        pass
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
    """
    if not langgraph_available():
        raise RuntimeError("langgraph_not_installed")
    from langgraph.types import Command
    from .blackboard import get_blackboard
    from .registry import get_registry

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
    result = graph.invoke(Command(resume=resume_val), config=cfg)
    out = result.get("agent") if isinstance(result, dict) else state
    if out is None:
        out = state
    out.extensions = dict(out.extensions or {})
    out.extensions["langgraph_thread_id"] = tid
    out.extensions["langgraph_interrupt"] = bool(result.get("__interrupt__")) if isinstance(result, dict) else False
    if isinstance(result, dict) and result.get("__interrupt__"):
        out.extensions["hitl_status"] = "awaiting_approval"
    else:
        out.extensions["hitl_status"] = out.extensions.get("hitl_status") or "resumed"
        out.extensions["langgraph_interrupt"] = False
    try:
        bd.put(out)
    except Exception:
        pass
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
