"""
Extensible Multi-Agent Orchestrator — Phase A closed loop.

Roles: Planner (architect) → Worker (builder/Cline) → Critic (observe+QA)
       → Repair → repeat until PASSED or max_attempts.
Trajectory events are persisted for failed-path audit.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

from .blackboard import BlackboardStore, get_blackboard
from .registry import AgentRegistry, get_registry
from .state import AgentRole, AgentState, AgentStatus

def _safe_user_text(request: str) -> str:
    try:
        from lumen.engine.services.prompt_fence import sanitize_user_text
        return sanitize_user_text(request or "", max_len=8000)
    except Exception:
        return (request or "")[:8000]


logger = logging.getLogger(__name__)


def _phase_d_e_finalize(state: AgentState) -> None:
    """Production evaluation record + platform events (Phases D/E)."""
    try:
        from lumen.engine.services.evaluation.live_bridge import persist_state_evaluation
        persist_state_evaluation(state)
    except Exception:
        logger.exception("persist_state_evaluation failed")
    try:
        from lumen.engine.services.events import emit
        status = getattr(state, "status", None)
        status_v = getattr(status, "value", status)
        success = bool(getattr(state, "qa_passed", False)) or str(status_v).upper() in {"PASSED", "DELIVERED"}
        emit(
            "generation.finished" if success else "generation.failed",
            {
                "state_id": getattr(state, "state_id", None) or getattr(state, "id", None),
                "user_id": getattr(state, "user_id", 0),
                "status": str(status_v),
                "attempts": getattr(state, "attempts", 0),
                "path": getattr(state, "generated_path", None),
            },
            source="multi_agent",
        )
    except Exception:
        logger.exception("generation event emit failed")



def orchestrator_enabled() -> bool:
    return (os.environ.get("MULTI_AGENT_ORCHESTRATOR") or "1").strip().lower() not in {
        "0", "false", "no", "off",
    }


def _max_attempts(state: AgentState) -> int:
    """Hard cap: dynamic agent attempts only (template path is dead)."""
    try:
        env = int(os.environ.get("MULTI_AGENT_MAX_ATTEMPTS") or state.max_attempts or 4)
    except ValueError:
        env = 2
    return max(1, min(env, 8))


class Orchestrator:
    def __init__(
        self,
        registry: AgentRegistry | None = None,
        board: BlackboardStore | None = None,
    ) -> None:
        self.registry = registry or get_registry()
        self.board = board or get_blackboard()

    def _agent(self, name: str):
        for a in self.registry.pipeline():
            if a.name == name:
                return a
        return None

    def _run_agent(self, name: str, state: AgentState, ctx: dict[str, Any]) -> AgentState:
        from .metrics import get_metrics
        metrics = get_metrics()
        agent = self._agent(name)
        if agent is None:
            state.record(AgentRole.ORCHESTRATOR, "missing_agent", name)
            return state
        if not agent.can_run(state) and name != "architect":
            if name == "critic" and state.build_success:
                pass
            elif name != "architect":
                state.record(AgentRole.ORCHESTRATOR, "can_run_false", name)
                return state
        try:
            from .tracing import start_span, end_span
            start_span(state, name)
            with metrics.timer("agent_latency_s", agent=name):
                state = agent.run(state, context=ctx)
            if state.status != AgentStatus.FAILED.value:
                metrics.incr("agent_success", agent=name)
                end_span(state, name, ok=True)
            else:
                metrics.incr("agent_failure", agent=name)
                end_span(state, name, ok=False, detail=state.status)
        except Exception as exc:
            logger.exception("agent %s crashed", name)
            metrics.incr("agent_crash", agent=name)
            try:
                from .tracing import end_span
                end_span(state, name, ok=False, detail=type(exc).__name__)
            except Exception:
                pass
            state.record(AgentRole.ORCHESTRATOR, "agent_crash", f"{name}:{type(exc).__name__}")
            try:
                state.transition(AgentStatus.FAILED, role=AgentRole.ORCHESTRATOR, detail=name, force=True)
            except Exception:
                state.status = AgentStatus.FAILED.value
        self.board.put(state)
        return state

    def run(
        self,
        state: AgentState,
        *,
        context: Optional[dict[str, Any]] = None,
    ) -> AgentState:
        from .metrics import get_metrics
        metrics = get_metrics()
        metrics.incr("orchestrator_start")
        with metrics.timer("orchestrator_total_s"):
            return self._run_inner(state, context=context)

    def _run_inner(
        self,
        state: AgentState,
        *,
        context: Optional[dict[str, Any]] = None,
    ) -> AgentState:
        from .metrics import get_metrics
        metrics = get_metrics()
        from .tracing import ensure_trace
        ensure_trace(state)
        ctx = dict(context or {})
        self.board.put(state)
        # Official LangGraph path (no re-architecture: same roles inside nodes)
        try:
            from .langgraph_pipeline import (
                langgraph_available,
                use_langgraph_pipeline,
                run_langgraph_pipeline,
            )
            from .production_policy import (
                allow_imperative_fallback,
                is_production,
                policy_snapshot,
            )
            state.extensions = dict(state.extensions or {})
            state.extensions["production_policy"] = policy_snapshot()
            if use_langgraph_pipeline() or is_production():
                if not langgraph_available():
                    metrics.incr("orchestrator_langgraph_missing")
                    state.final_message = "LangGraph required (production source of truth) — pip install langgraph"
                    try:
                        state.transition(AgentStatus.FAILED, role=AgentRole.ORCHESTRATOR, detail="langgraph_required", force=True)
                    except Exception:
                        state.status = AgentStatus.FAILED.value
                    self.board.put(state)
                    return state
                metrics.incr("orchestrator_langgraph")
                _resume_statuses = {
                    AgentStatus.PLANNING.value,
                    AgentStatus.BUILDING.value,
                    AgentStatus.QA.value,
                    AgentStatus.FAILED.value,
                }
                skip_router = (
                    state.status in _resume_statuses
                    and bool(state.capability_id or (state.extensions or {}).get("selected_tool") or state.user_text)
                )
                if not skip_router:
                    state = self._run_agent("router", state, ctx)
                if state.status == AgentStatus.CANCELLED.value:
                    return self._deliver(state)
                tool = str((state.extensions or {}).get("selected_tool") or state.capability_id or "")
                if tool and tool not in {"generate_bot", "refine_bot", "cline", ""}:
                    pass  # non-generate: legacy tool path below
                else:
                    state = run_langgraph_pipeline(
                        state, context=ctx, registry=self.registry, board=self.board
                    )
                    return state
        except Exception as _lg_exc:
            logger.exception("langgraph pipeline failed")
            try:
                from .production_policy import allow_imperative_fallback
                if not allow_imperative_fallback():
                    metrics.incr("orchestrator_langgraph_hard_fail")
                    state.final_message = f"LangGraph failed (no imperative fallback): {type(_lg_exc).__name__}"
                    try:
                        state.transition(AgentStatus.FAILED, role=AgentRole.ORCHESTRATOR, detail="langgraph_hard_fail", force=True)
                    except Exception:
                        state.status = AgentStatus.FAILED.value
                    self.board.put(state)
                    return state
            except Exception:
                pass
            logger.exception("langgraph pipeline failed — falling back to imperative loop (dev only)")
        max_att = _max_attempts(state)
        state.max_attempts = max_att
        state.record(
            AgentRole.ORCHESTRATOR,
            "pipeline_start",
            f"agents={self.registry.names()} max_attempts={max_att} status={state.status}",
        )

        _resume_statuses = {
            AgentStatus.PLANNING.value,
            AgentStatus.BUILDING.value,
            AgentStatus.QA.value,
            AgentStatus.FAILED.value,
        }
        skip_router = (
            state.status in _resume_statuses
            and bool(state.capability_id or (state.extensions or {}).get("selected_tool") or state.user_text)
        )
        if skip_router:
            state.record(AgentRole.ORCHESTRATOR, "resume_checkpoint", state.status)
            self.board.put(state)
        else:
            state = self._run_agent("router", state, ctx)
        if state.status == AgentStatus.CANCELLED.value:
            return self._deliver(state)

        # Phase D: non-generate tools go through explicit tool + HITL gate
        tool = str((state.extensions or {}).get("selected_tool") or state.capability_id or "")
        if tool and tool not in {"generate_bot", "refine_bot", "chat_or_other", ""}:
            from .tools import execute_tool_gated
            # If resuming after confirm, skip HITL
            skip = bool((state.extensions or {}).get("hitl_confirmed"))
            state = execute_tool_gated(state, tool, state.route_params, skip_hitl=skip)
            self.board.put(state)
            if state.status == AgentStatus.AWAITING_CONFIRMATION.value:
                return state  # parked for human — do not deliver as finished build
            return self._deliver(state)

        # chat_or_other: no build pipeline
        if tool == "chat_or_other":
            state.final_message = state.final_message or "لم يُطلب توليد بوت. اكتب وصف البوت للبدء."
            try:
                state.transition(AgentStatus.DELIVERED, role=AgentRole.ORCHESTRATOR, force=True)
            except Exception:
                state.status = AgentStatus.DELIVERED.value
            return self._deliver(state)

        # Generate must use LangGraph + Cline only — no imperative loop.
        from .metrics import get_metrics as _gm
        _gm().incr("orchestrator_langgraph_required")
        state.final_message = (
            "LangGraph + Cline agent_loop required for generate. "
            "pip install langgraph langchain-core"
        )
        try:
            state.transition(AgentStatus.FAILED, role=AgentRole.ORCHESTRATOR, detail="langgraph_required", force=True)
        except Exception:
            state.status = AgentStatus.FAILED.value
        self.board.put(state)
        return self._deliver(state)




def save_state(state: AgentState) -> AgentState:
    return get_blackboard().put(state)


def get_state(state_id: str) -> Optional[AgentState]:
    return get_blackboard().get(state_id)


def latest_for_user(user_id: int) -> Optional[AgentState]:
    return get_blackboard().latest_for_user(int(user_id or 0))


def orchestrate_generate(
    request: str,
    work_dir: str | Path,
    *,
    user_id: int = 0,
    preferred_keys: Optional[list[str]] = None,
    spec_request: Optional[str] = None,
    registry: AgentRegistry | None = None,
    board: BlackboardStore | None = None,
) -> Any:
    """Temporal (optional) → official LangGraph + Cline agent_loop. No dual path."""
    import os
    from lumen.engine.core.result import GenerationResult

    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    try:
        from lumen.engine.services.progress_bus import report_progress
        report_progress({
            "phase": "orchestrate",
            "detail": "بدء مسار الوكلاء المتعددين",
            "step": 0,
        })
    except Exception:
        pass

    try:
        from lumen.platform.queue_backpressure import check_enqueue_allowed
        ok_bp, reason_bp = check_enqueue_allowed(f"tg:{int(user_id or 0)}", kind="generate")
        if not ok_bp:
            return GenerationResult(success=False, errors=[f"backpressure:{reason_bp}"], metadata={"backpressure": True})
    except Exception as _bp:
        if (os.getenv("ENVIRONMENT") or "").strip().lower() in {"production", "prod", "staging"}:
            return GenerationResult(success=False, errors=[f"backpressure_error:{type(_bp).__name__}"], metadata={"backpressure": True})

    # Fail-closed: suspended or zero-balance tenants cannot start new generations
    try:
        from lumen.platform.balance_lifecycle import get_balance_lifecycle
        _tid = f"tg:{int(user_id or 0)}" if int(user_id or 0) else ""
        if not _tid:
            return GenerationResult(
                success=False,
                errors=["insufficient_credits:no_tenant"],
                metadata={"insufficient_credits": True, "reason": "no_tenant"},
            )
        ok_gen, reason_gen = get_balance_lifecycle().is_generation_allowed(_tid)
        if not ok_gen:
            return GenerationResult(
                success=False,
                errors=[f"insufficient_credits:{reason_gen}"],
                metadata={"insufficient_credits": True, "reason": reason_gen, "tenant_id": _tid},
            )
    except Exception as _gate_exc:
        logger.error("generation balance gate failed closed: %s", type(_gate_exc).__name__)
        return GenerationResult(
            success=False,
            errors=[f"insufficient_credits:gate_unavailable:{type(_gate_exc).__name__}"],
            metadata={"insufficient_credits": True, "reason": "gate_unavailable"},
        )

    inside = (os.environ.get("LUMEN_INSIDE_TEMPORAL_ACTIVITY") or "").strip().lower() in {"1", "true", "yes"}
    try:
        from .temporal_client_run import run_generate_via_temporal, temporal_configured
        if temporal_configured() and not inside and (os.environ.get("LUMEN_GENERATE_VIA_TEMPORAL") or "1").strip().lower() not in {"0", "false", "no"}:
            tr = run_generate_via_temporal(
                request=request or "",
                work_dir=str(work),
                user_id=int(user_id or 0),
                preferred_keys=list(preferred_keys or []),
            )
            result = tr.get("result") or tr
            if tr.get("error") and not result.get("ok"):
                return GenerationResult(success=False, errors=[str(tr.get("error"))], metadata={"engine": "temporal", "temporal": tr})
            path = str((result or {}).get("generated_path") or "") or None
            success = bool((result or {}).get("ok") or (result or {}).get("qa_passed"))
            return GenerationResult(
                success=success,
                project_path=path,
                errors=[] if success else [str((result or {}).get("status") or "failed")],
                metadata={"engine": "temporal+langgraph+cline", "workflow_id": tr.get("workflow_id"), "task_tree": (result or {}).get("task_tree")},
            )
    except Exception:
        logger.exception("temporal path failed — LangGraph in-process")

    from .langgraph_pipeline import langgraph_available, run_langgraph_pipeline
    from .registry import get_registry
    from .blackboard import get_blackboard

    if not langgraph_available():
        return GenerationResult(
            success=False,
            errors=["langgraph_required: pip install langgraph langchain-core"],
            metadata={"engine": "multi_agent"},
        )

    board = board or get_blackboard()
    registry = registry or get_registry()
    state = AgentState(
        user_id=int(user_id or 0),
        user_text=_safe_user_text(request),
        spec_request=(spec_request or request or ""),
        preferred_keys=list(preferred_keys or []),
    )
    state.extensions["work_dir"] = str(work)
    state.capability_id = "generate_bot"
    board.put(state)

    out = run_langgraph_pipeline(
        state,
        context={"work_dir": str(work), "user_id": int(user_id or 0)},
        registry=registry,
        board=board,
        thread_id=state.state_id,
    )
    board.put(out)
    try:
        _phase_d_e_finalize(out)
    except Exception:
        logger.exception("finalize failed")

    status_u = str(out.status).upper()
    awaiting = status_u == "AWAITING_CONFIRMATION" or bool((out.extensions or {}).get("langgraph_interrupt"))
    # Smart presentation: agents/engine decide if a native table clarifies the result
    try:
        from lumen.engine.services.presentation import decide_and_attach
        decide_and_attach(out)
    except Exception:
        logger.exception("presentation decide_and_attach failed")

    success = bool(out.qa_passed) or status_u in {"PASSED", "DELIVERED"}
    # HITL pause is not a hard failure — surface message for the user to confirm
    errors = list(out.build_errors or [])
    if not success and not awaiting and out.final_message:
        errors.append(out.final_message[:500])
    pending = (out.extensions or {}).get("pending_action") or {}
    return GenerationResult(
        success=success or awaiting,  # awaiting counts as handled success path
        project_path=out.generated_path or None,
        validation_reports=[out.qa_report] if out.qa_report else [],
        errors=errors[:30],
        metadata={
            "final_message": (out.final_message or "")[:2000],
            "engine": "langgraph+cline",
            "orchestration": "langgraph+cline",
            "state_id": out.state_id,
            "status": out.status,
            "attempts": out.attempts,
            "task_tree": (out.extensions or {}).get("task_tree_summary"),
            "qa_passed": out.qa_passed,
            "langgraph_interrupt": bool((out.extensions or {}).get("langgraph_interrupt")),
            "hitl_status": (out.extensions or {}).get("hitl_status"),
            "langgraph_thread_id": (out.extensions or {}).get("langgraph_thread_id"),
            "pending_action_id": pending.get("action_id"),
            "confirm_token": pending.get("confirm_token"),
            "awaiting_hitl": awaiting,
            # Engine → Telegram presentation bridge (Rich tables)
            "presentation": (out.extensions or {}).get("presentation"),
            "stages": (out.extensions or {}).get("stages"),
            "build_success": bool(getattr(out, "build_success", False)),
            # Phase-4 E2E: surface agent router to Telegram delivery
            "router": ((out.extensions or {}).get("last_coding_session") or {}).get("router"),
            "provider": ((out.extensions or {}).get("last_coding_session") or {}).get("provider"),
            "model_id": ((out.extensions or {}).get("last_coding_session") or {}).get("model_id"),
            "stop_reason": ((out.extensions or {}).get("last_coding_session") or {}).get("stop_reason"),
        },
    )




def _resume_or_rerun(state, ctx, board, orch, decision: str = "approved"):
    """Prefer official LangGraph Command(resume) when an interrupt is pending.

    On resume failure for an *approved* decision we surface the error instead of
    falling through to ``orch.run`` — a full restart would re-interrupt at the
    plan gate and trap the user in an infinite "confirm the plan" loop.
    """
    ext = state.extensions or {}
    pending = ext.get("pending_action") or {}
    tool = str(pending.get("tool") or state.capability_id or "")
    is_lg = (
        ext.get("langgraph_interrupt")
        or ext.get("hitl_status") in {
            "awaiting_approval",
            "awaiting_deliver_approval",
        }
        or tool in {"langgraph_plan_approve", "langgraph_deliver_approve"}
    )
    if is_lg:
        try:
            from .langgraph_pipeline import resume_langgraph_hitl
            return resume_langgraph_hitl(state, decision, context=ctx, board=board)
        except Exception as exc:
            state.extensions = dict(ext)
            state.extensions["hitl_resume_error"] = f"{type(exc).__name__}:{exc}"
            # Clear the stale awaiting-approval flags so callers (Telegram bot)
            # do not mistake this FAILED state for a fresh interrupt prompt
            # (which would re-ask "confirm the plan" and loop forever).
            state.extensions["langgraph_interrupt"] = False
            state.extensions["hitl_status"] = "resume_failed"
            if str(decision).lower() in {"rejected", "reject", "no", "cancel"}:
                state.status = "FAILED"
                # OVERRIDE (not fallback) — state.final_message still holds the
                # stale "إجراء حساس — بوابة تأكيد" prompt from request_confirmation,
                # so `or` would never use the real failure reason.
                state.final_message = f"HITL reject failed: {exc}"
                return state
            # Approved resume failed — do NOT fall through to orch.run (full restart)
            # which would re-interrupt and loop forever. Surface a clear failure so
            # the user sees what went wrong and can retry the whole generation.
            logger.exception("HITL approved resume failed — surfacing error (no full restart)")
            try:
                state.transition(AgentStatus.FAILED, role=AgentRole.HITL, detail=f"hitl_resume_failed:{type(exc).__name__}", force=True)
            except Exception:
                state.status = AgentStatus.FAILED.value
            # OVERRIDE (not fallback) — state.final_message still holds the stale
            # "⚠️ إجراء حساس — بوابة تأكيد" prompt from request_confirmation, so
            # using `or` would keep showing the approval prompt instead of this
            # real error.  The user would see "confirm the plan" forever and think
            # their confirmation did nothing — exactly the reported bug
            # ("ببعت تاكيد مش بيبدا التوليد ليه").
            state.final_message = (
                f"تعذّر استئناف التنفيذ بعد التأكيد: {type(exc).__name__}. "
                f"السبب الأرجح: فقدان نقطة حفظ LangGraph بين العمليات. "
                f"أعد طلب التوليد من البداية."
            )
            try:
                board.put(state)
            except Exception:
                pass
            return state
    return orch.run(state, context=ctx)




def resume_after_confirm(
    state_id: str,
    action_id: str,
    *,
    user_id: int = 0,
    confirm_token: str = "",
    work_dir: str | Path | None = None,
    board: BlackboardStore | None = None,
) -> AgentState:
    """Confirm HITL action (action_id + token) then continue orchestration."""
    from .hitl import confirm_action
    board = board or get_blackboard()
    ok, state, reason = confirm_action(
        state_id, action_id, user_id=user_id, confirm_token=confirm_token, board=board,
    )
    if not ok or state is None:
        if state is None:
            state = AgentState(status=AgentStatus.FAILED.value)
            state.final_message = f"فشل التأكيد: {reason}"
        return state
    pending = (state.extensions or {}).get("pending_action") or {}
    tool = str(pending.get("tool") or state.capability_id or "")
    ctx = {"work_dir": Path(work_dir) if work_dir else Path(state.extensions.get("work_dir") or ".")}
    orch = Orchestrator(board=board)
    # For generate tools after confirm, run full build loop
    if tool in {"generate_bot", "refine_bot", "langgraph_plan_approve", "langgraph_deliver_approve"}:
        return _resume_or_rerun(state, ctx, board, orch, decision="approved")
    from .tools import execute_tool_gated
    state = execute_tool_gated(state, tool, dict(pending.get("params") or {}), skip_hitl=True)
    board.put(state)
    return orch._deliver(state)

def continue_after_confirm(
    state_id: str,
    *,
    user_id: int = 0,
    work_dir: str | Path | None = None,
    board: BlackboardStore | None = None,
) -> AgentState:
    """Continue after confirm_action already succeeded (token already consumed)."""
    board = board or get_blackboard()
    state = board.get(state_id)
    if state is None:
        state = AgentState(status=AgentStatus.FAILED.value)
        state.final_message = "state_not_found"
        return state
    if user_id and int(state.user_id or 0) not in {0, int(user_id)}:
        state.final_message = "user_mismatch"
        return state
    pending = (state.extensions or {}).get("pending_action") or {}
    tool = str(pending.get("tool") or state.capability_id or "")
    ctx = {"work_dir": Path(work_dir) if work_dir else Path(state.extensions.get("work_dir") or ".")}
    orch = Orchestrator(board=board)
    if tool in {"generate_bot", "refine_bot", "langgraph_plan_approve", "langgraph_deliver_approve"}:
        return _resume_or_rerun(state, ctx, board, orch, decision="approved")
    from .tools import execute_tool_gated
    state = execute_tool_gated(state, tool, dict(pending.get("params") or {}), skip_hitl=True)
    board.put(state)
    return orch._deliver(state)

