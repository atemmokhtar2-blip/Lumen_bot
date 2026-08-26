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

        try:
            from lumen.engine.services.engine_router import build_ir_from_package, execute_ir

            package: dict[str, Any] = {
                "original_text": req,
                "spec_request": req,
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
            }
            ir = build_ir_from_package(package, user_id=user_id)
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
