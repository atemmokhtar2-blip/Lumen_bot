"""Worker agent (Builder) — Phase A: Cline SDK is the sole generation path.

Role alias: Worker. Executes the plan produced by Planner (Architect).
Does not call purged deterministic catalog generate_bot as primary.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ..context_views import builder_view
from ..protocol import Agent
from ..state import AgentRole, AgentState, AgentStatus
from ..strict_spec import StrictSpec, merge_spec_request


def _code_intel_preflight(work_dir: str, state) -> None:
    """On large/existing trees: hybrid index + blast hints for worker context."""
    from pathlib import Path as P
    root = P(work_dir or "")
    if not root.is_dir():
        return
    py_files = list(root.rglob("*.py"))[:5000]
    if len(py_files) < 8:
        return
    try:
        from lumen.engine.services.code_intelligence.hybrid_retrieval import hybrid_search
        from lumen.engine.services.code_intelligence.symbol_graph import build_symbol_graph
        goal = (state.user_text or state.spec_request or "")[:500]
        graph = build_symbol_graph(root, max_files=800)
        state.extensions["code_intel_graph_stats"] = {
            "files": (graph or {}).get("files") or (graph or {}).get("file_count"),
            "symbols": len((graph or {}).get("symbols") or (graph or {}).get("nodes") or []),
        }
        if goal:
            hits = hybrid_search(str(root), goal, top_k=8)
            state.extensions["code_intel_retrieval"] = hits if isinstance(hits, dict) else {"hits": hits}
    except Exception as exc:
        state.extensions["code_intel_preflight_error"] = type(exc).__name__




def _try_swarm_independent_tasks(state, plan: dict, work_dir) -> dict | None:
    """If execution_plan has multiple independent tasks, run via official swarm pool."""
    import os
    if (os.getenv("MULTI_AGENT_SWARM") or "1").strip().lower() in {"0", "false", "off", "no"}:
        return None
    tasks = list((plan or {}).get("tasks") or [])
    if len(tasks) < 2:
        return None
    # Independent = no deps or empty deps
    independent = []
    for t in tasks:
        if not isinstance(t, dict):
            continue
        deps = t.get("deps") or t.get("depends_on") or []
        if not deps:
            independent.append(t)
    if len(independent) < 2:
        return None
    try:
        from ..swarm import run_swarm
        from pathlib import Path as P

        def worker_fn(part, root, idx):
            # Record partition only — actual codegen stays single Cline run below;
            # swarm marks parallel ownership of task ids on state for trajectory.
            return {
                "ok": True,
                "worker": idx,
                "task_ids": [x.get("id") or x.get("title") for x in part],
                "count": len(part),
            }

        result = run_swarm(work_dir=work_dir, tasks=independent, worker_fn=worker_fn)
        return result
    except Exception:
        return None




class BuilderAgent(Agent):
    """Worker role — materializes StrictSpec / request via Cline execute_ir."""

    role = AgentRole.BUILDER.value
    name = "builder"
    order = 30
    # Phase A alias for docs / metrics
    role_alias = "worker"

    def run(self, state: AgentState, *, context: Optional[dict[str, Any]] = None) -> AgentState:
        state.transition(AgentStatus.BUILDING, role=AgentRole.BUILDER)
        state.attempts = int(state.attempts or 0) + 1
        ctx = context or {}
        work_dir = Path(ctx.get("work_dir") or state.extensions.get("work_dir") or ".")
        work_dir.mkdir(parents=True, exist_ok=True)


        try:
            _wd = str((state.extensions or {}).get("work_dir") or context.get("work_dir") if context else "")
            if not _wd and context:
                _wd = str(context.get("work_dir") or "")
            _code_intel_preflight(_wd, state)
        except Exception:
            pass
        view = builder_view(state)
        spec = StrictSpec.from_dict(view.get("strict_spec") or {})
        req = str(view.get("spec_request") or "").strip() or merge_spec_request(spec)
        preferred = list(view.get("preferred_keys") or spec.features or []) or None
        user_id = int(view.get("user_id") or state.user_id or 0)

        if not req:
            state.build_success = False
            state.build_errors = ["empty_spec_request"]
            state.record(AgentRole.BUILDER, "build_abort", "empty_spec")
            state.transition(AgentStatus.FAILED, role=AgentRole.BUILDER, detail="empty_spec")
            return state

        # Cursor-class path: patch existing project instead of full regenerate
        try:
            from ..repair_worker import should_incremental_repair, run_incremental_repair
            if should_incremental_repair(state):
                state.transition(AgentStatus.BUILDING, role=AgentRole.BUILDER)
                state.attempts = int(state.attempts or 0)  # already incremented above
                state = run_incremental_repair(state, work_dir=work_dir)
                if state.build_success and (state.generated_path or "").strip():
                    return state
                # if incremental failed hard with no path, fall through to full generate once
                if (state.generated_path or "").strip() and Path(state.generated_path).is_dir():
                    return state
        except Exception as exc:
            state.record(AgentRole.BUILDER, "incremental_repair_fallback", type(exc).__name__)

        try:
            from lumen.engine.services.engine_router import build_ir_from_package, execute_ir

            # Execution plan + repair directive → Cline goal enrichment
            plan = (state.extensions or {}).get("execution_plan") or {}

            try:
                _wd = (state.extensions or {}).get("work_dir") or ""
                _swarm = _try_swarm_independent_tasks(state, plan if isinstance(plan, dict) else {}, _wd)
                if _swarm:
                    state.extensions["swarm"] = _swarm
                    state.record("BUILDER", "swarm_partition", str(_swarm.get("workers")))
            except Exception:
                pass
            repair = (state.extensions or {}).get("last_repair") or {}
            brief_parts = [req]
            try:
                from ..plan_contract import ExecutionPlan
                ep = ExecutionPlan.from_dict(plan) if plan else None
                if ep and (ep.tasks or ep.goal):
                    brief_parts.append("\n--- EXECUTION_PLAN ---\n" + ep.to_worker_brief())
            except Exception:
                if plan:
                    brief_parts.append("\n--- EXECUTION_PLAN ---\n" + str(plan)[:1500])
            if repair:
                try:
                    from ..repair import RepairDirective
                    rd = RepairDirective(
                        attempt=int(repair.get("attempt") or state.attempts or 0),
                        blocking_errors=list(repair.get("blocking_errors") or []),
                        soft_warnings=list(repair.get("soft_warnings") or []),
                        actions=list(repair.get("actions") or []),
                        drop_features=list(repair.get("drop_features") or []),
                        add_constraints=list(repair.get("add_constraints") or []),
                        force_spec_prefix=str(repair.get("force_spec_prefix") or ""),
                    )
                    brief_parts.append("\n--- REPAIR_DIRECTIVE ---\n" + rd.to_prompt_block())
                except Exception:
                    brief_parts.append("\n--- REPAIR ---\n" + str(repair)[:1200])
            enriched = "\n".join(brief_parts)[:12000]

            package: dict[str, Any] = {
                "original_text": enriched,
                "spec_request": enriched,
                "purpose": str((view.get("strict_spec") or {}).get("purpose") or "")[:200],
                "preferred_keys": list(preferred or []),
                "capabilities_gap": list(
                    (view.get("strict_spec") or {}).get("gaps")
                    or state.extensions.get("capabilities_gap")
                    or []
                ),
                "engine_mode": "cline",
                "confidence": float((view.get("strict_spec") or {}).get("confidence") or 0.7),
                "looks_custom": True,
                "needs_ai_codegen": True,
                "user_id": user_id,
                "execution_plan": plan,
                "repair_directive": repair,
                "findings": list((state.extensions or {}).get("findings") or [])[:20],
            }
            ir = build_ir_from_package(package, user_id=user_id)
            # stash plan on IR metadata for agent_loop
            try:
                meta = dict(ir.metadata or {})
                meta["execution_plan"] = plan
                meta["repair_directive"] = repair
                # Phase A: findings must flow end-to-end via BuildIR.metadata
                meta["findings"] = list((state.extensions or {}).get("findings") or [])[:40]
                meta["mode"] = "incremental_repair" if repair else meta.get("mode") or "generate"
                ir.metadata = meta
            except Exception:
                pass
            result = execute_ir(ir, work_dir, user_id=user_id)
        except Exception as exc:
            state.build_success = False
            state.build_errors = [f"{type(exc).__name__}:{exc}"]
            state.record(AgentRole.BUILDER, "build_exception", type(exc).__name__)
            state.transition(AgentStatus.FAILED, role=AgentRole.BUILDER, detail=type(exc).__name__)
            try:
                from ..trajectory import append_trajectory
                append_trajectory(
                    state,
                    step="worker_build_error",
                    role=AgentRole.BUILDER.value,
                    ok=False,
                    detail=type(exc).__name__,
                )
            except Exception:
                pass
            return state

        success = bool(getattr(result, "success", False))
        state.build_success = success
        path = getattr(result, "project_path", None) or getattr(result, "output_dir", None) or ""
        state.generated_path = str(path or "")
        errs = list(getattr(result, "errors", None) or [])
        state.build_errors = [str(e)[:200] for e in errs[:20]]
        meta = dict(getattr(result, "metadata", None) or {})
        state.extensions["worker_engine"] = meta.get("engine") or "cline"
        state.extensions["worker_meta"] = {
            "engine": meta.get("engine"),
            "cline_ok": bool((meta.get("cline") or {}).get("ok")) if isinstance(meta.get("cline"), dict) else None,
        }
        # Phase A cost: surface cline agent usage onto orchestrator extensions
        try:
            cline = meta.get("cline") if isinstance(meta.get("cline"), dict) else {}
            agent_usage = (cline.get("metadata") or {}).get("usage") if isinstance(cline.get("metadata"), dict) else None
            if not agent_usage and isinstance(cline.get("usage"), dict):
                agent_usage = cline.get("usage")
            if agent_usage:
                state.extensions["usage"] = dict(agent_usage)
        except Exception:
            pass
        state.record(
            AgentRole.BUILDER,
            "build_done",
            f"ok={success} engine={meta.get('engine')} path={bool(path)}",
        )
        try:
            from ..trajectory import append_trajectory
            append_trajectory(
                state,
                step="worker_build",
                role=AgentRole.BUILDER.value,
                ok=success,
                detail=str(meta.get("engine") or ""),
                payload={"errors": state.build_errors[:5]},
            )
        except Exception:
            pass

        if success and path:
            # stay BUILDING until Critic; orchestrator advances
            return state
        state.transition(AgentStatus.FAILED, role=AgentRole.BUILDER, detail="build_failed")
        return state


def run_builder(state: AgentState, *, context: Optional[dict[str, Any]] = None) -> AgentState:
    return BuilderAgent().run(state, context=context)


# Phase A alias
WorkerAgent = BuilderAgent
run_worker = run_builder

__all__ = ["BuilderAgent", "WorkerAgent", "run_builder", "run_worker"]
