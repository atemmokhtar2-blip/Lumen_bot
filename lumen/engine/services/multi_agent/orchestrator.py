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
        from .circuit import get_circuit_board
        from .metrics import get_metrics
        metrics = get_metrics()
        breaker = get_circuit_board().get(f"agent:{name}")
        if not breaker.allow():
            state.record(AgentRole.ORCHESTRATOR, "circuit_open", name)
            metrics.incr("agent_circuit_open", agent=name)
            try:
                state.transition(AgentStatus.FAILED, role=AgentRole.ORCHESTRATOR, detail=f"circuit:{name}", force=True)
            except Exception:
                state.status = AgentStatus.FAILED.value
            self.board.put(state)
            return state
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
            # Success heuristic: not FAILED after agent
            if state.status != AgentStatus.FAILED.value:
                breaker.record_success()
                metrics.incr("agent_success", agent=name)
                end_span(state, name, ok=True)
            else:
                breaker.record_failure()
                metrics.incr("agent_failure", agent=name)
                end_span(state, name, ok=False, detail=state.status)
        except Exception as exc:
            logger.exception("agent %s crashed", name)
            breaker.record_failure()
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

    def _builder_with_gate(self, state: AgentState, ctx: dict[str, Any]) -> AgentState:
        from .gates import architect_gate, apply_catalog_filter_to_state
        state = apply_catalog_filter_to_state(state)
        ok, errors = architect_gate(state)
        if not ok:
            state.build_success = False
            state.build_errors = list(errors)
            state.record(AgentRole.ORCHESTRATOR, "builder_blocked", ",".join(errors[:5]))
            try:
                state.transition(AgentStatus.FAILED, role=AgentRole.ORCHESTRATOR, detail="spec_gate", force=True)
            except Exception:
                state.status = AgentStatus.FAILED.value
            self.board.put(state)
            return state
        return self._run_agent("builder", state, ctx)

    def run(
        self,
        state: AgentState,
        *,
        context: Optional[dict[str, Any]] = None,
    ) -> AgentState:
        from .concurrency import orchestration_slot
        from .metrics import get_metrics
        metrics = get_metrics()
        with orchestration_slot(user_id=int(state.user_id or 0)) as got:
            if not got:
                metrics.incr("orchestrator_slot_timeout")
                state.final_message = "النظام مشغول (حد التوازي) — أعد المحاولة بعد لحظات."
                try:
                    state.transition(AgentStatus.FAILED, role=AgentRole.ORCHESTRATOR, detail="busy", force=True)
                except Exception:
                    state.status = AgentStatus.FAILED.value
                self.board.put(state)
                return state
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


    def resume_run(self, state: AgentState, *, from_step: str = "architect") -> AgentState:
        """Continue a crashed/paused generation from last durable checkpoint."""
        state.record(AgentRole.ORCHESTRATOR, "resume_run", from_step)
        # Force status so _run_inner skips router when appropriate
        if from_step in {"builder", "critic", "deliver"}:
            try:
                state.transition(AgentStatus.BUILDING, role=AgentRole.ORCHESTRATOR, force=True)
            except Exception:
                state.status = AgentStatus.BUILDING.value
        elif from_step == "architect":
            try:
                state.transition(AgentStatus.PLANNING, role=AgentRole.ORCHESTRATOR, force=True)
            except Exception:
                state.status = AgentStatus.PLANNING.value
        self.board.put(state)
        return self.run(state)


    def _rate_limit_errors(self, state: AgentState) -> bool:
        """True if build/QA errors look like provider 429 / rate limit / quota."""
        blobs = []
        blobs.extend(str(e) for e in (state.build_errors or [])[:20])
        blobs.extend(str(e) for e in ((state.qa_report or {}).get("errors") or [])[:20])
        text = " ".join(blobs).lower()
        keys = (
            "429",
            "rate limit",
            "rate_limit",
            "ratelimit",
            "quota",
            "resource_exhausted",
            "too many requests",
            "tpm",
            "rpm",
        )
        return any(k in text for k in keys)

    def _pause_for_rate_limit(self, state: AgentState) -> AgentState:
        """Phase B: durable pause on 429 — journal + schedule resume instead of hard fail-only."""
        ext = dict(state.extensions or {})
        ext["paused_reason"] = "rate_limit_429"
        ext["needs_resume"] = True
        state.extensions = ext
        try:
            state.status = AgentStatus.BUILDING.value  # resumable, not terminal success
        except Exception:
            state.status = "building"
        state.record(AgentRole.ORCHESTRATOR, "pause_429", "durable pause — will resume")
        self._wf_checkpoint(state, "paused_429")
        self.board.put(state)
        # Schedule resume via worker pool and/or Redis queue
        try:
            from .worker_pool import submit_resume_job
            submit_resume_job(state.state_id)
        except Exception:
            pass
        try:
            from .redis_board import enqueue_resume_job, redis_board_enabled
            if redis_board_enabled():
                enqueue_resume_job(state.state_id)
        except Exception:
            pass
        msg = (state.final_message or "").strip()
        extra = "[Phase B] paused for provider rate limit (429) — resume scheduled"
        state.final_message = (msg + "\n" + extra).strip() if msg else extra
        return state

    def _wf_checkpoint(self, state: AgentState, step: str) -> None:
        """Durable journal + workflow engine start/checkpoint after each agent step (Phase B)."""
        try:
            from .durable_workflow import JournalEntry, get_journal
            from .workflow_engine import get_workflow_engine
            ext = dict(state.extensions or {})
            wid = str(ext.get("workflow_id") or "")
            eng = get_workflow_engine()
            payload = {
                "qa_passed": bool(state.qa_passed),
                "generated_path": str(state.generated_path or "")[:500],
                "capability_id": str(state.capability_id or ""),
                "user_id": int(state.user_id or 0),
                "attempts": int(state.attempts or 0),
            }
            if not wid:
                wid = eng.start(
                    state.state_id,
                    step=step,
                    payload={
                        **payload,
                        "description": str(getattr(state, "user_text", "") or "")[:500],
                    },
                )
                ext["workflow_id"] = wid
                ext["workflow_engine"] = type(eng).__name__
            else:
                eng.checkpoint(
                    wid,
                    state_id=state.state_id,
                    step=step,
                    status=str(state.status or "running"),
                    payload=payload,
                )
            entry = JournalEntry(
                workflow_id=wid,
                state_id=state.state_id,
                step=step,
                status=str(state.status or "running"),
                user_id=int(state.user_id or 0),
                description=str(getattr(state, "user_text", "") or getattr(state, "description", "") or ""),
                attempts=int(state.attempts or 0),
                payload=payload,
            )
            get_journal().write(entry)
            state.extensions = ext
            self.board.put(state)
        except Exception:
            logger.exception("workflow checkpoint skipped")

    def _deliver(self, state: AgentState) -> AgentState:
        from .context_views import deliver_view
        dview = deliver_view(state)
        # Final automated unit gate before any "success" delivery
        if (state.status == AgentStatus.PASSED.value or state.qa_passed) and (state.generated_path or "").strip():
            try:
                from .generated_tests import run_generated_unit_gate
                gate = run_generated_unit_gate(state.generated_path)
                ext = dict(state.extensions or {})
                ext["unit_gate_deliver"] = gate
                state.extensions = ext
                if not gate.get("ok"):
                    state.qa_passed = False
                    state.status = AgentStatus.FAILED.value
                    state.final_message = (
                        "فشل بوابة الاختبار الآلي على الكود المولَّد:\n"
                        + "\n".join(str(e) for e in (gate.get("errors") or [])[:6])
                    )
                    self.board.put(state)
                    return state
            except Exception as _ug:
                logger.exception("unit gate at deliver failed")
                state.qa_passed = False
                state.status = AgentStatus.FAILED.value
                state.final_message = f"unit_gate_error:{type(_ug).__name__}"
                self.board.put(state)
                return state
        if state.status == AgentStatus.PASSED.value or state.qa_passed:
            state.final_message = (
                f"تم البناء بنجاح.\nالمسار: {state.generated_path}\n"
                f"QA: PASSED\nمحاولات: {state.attempts}/{state.max_attempts}\n"
                f"state_id: {state.state_id}"
            )
            try:
                state.transition(AgentStatus.DELIVERED, role=AgentRole.ORCHESTRATOR, force=True)
            except Exception:
                state.status = AgentStatus.DELIVERED.value
        elif dview.get("clarification_needed") and dview.get("clarification_questions"):
            qs = dview["clarification_questions"]
            state.final_message = (
                "المعماري يحتاج توضيح قبل البناء:\n"
                + "\n".join(f"• {q}" for q in qs[:5])
                + f"\nstate_id: {state.state_id}"
            )
            try:
                state.transition(AgentStatus.DELIVERED, role=AgentRole.ORCHESTRATOR, force=True)
            except Exception:
                state.status = AgentStatus.DELIVERED.value
        else:
            qa_errs = (state.qa_report or {}).get("errors") or state.build_errors or []
            state.final_message = (
                f"انتهى المسار بحالة {state.status} بعد {state.attempts} محاولة/محاولات.\n"
                f"المسار: {state.generated_path or '—'}\n"
                f"QA: {'PASSED' if state.qa_passed else 'FAILED'}\n"
                f"تفاصيل: {'; '.join(str(e) for e in qa_errs[:5])}\n"
                f"state_id: {state.state_id}"
            )
            try:
                state.transition(AgentStatus.DELIVERED, role=AgentRole.ORCHESTRATOR, force=True)
            except Exception:
                state.status = AgentStatus.DELIVERED.value
            state.record(AgentRole.ORCHESTRATOR, "deliver_terminal", state.status)

        # Formal deliver agent (if registered) may refine final_message
        deliver = self._agent("deliver")
        if deliver is not None and state.status != AgentStatus.AWAITING_CONFIRMATION.value:
            try:
                state = deliver.run(state, context={})
            except Exception:
                logger.exception("deliver agent failed")
        self.board.put(state)
        try:
            from .metrics import get_metrics
            from .run_report import write_run_report
            from .tracing import trace_summary
            m = get_metrics()
            m.incr("orchestrator_done", status=str(state.status))
            if state.qa_passed:
                m.incr("orchestrator_qa_passed")
            else:
                m.incr("orchestrator_qa_failed")
            path = write_run_report(state)
            state.extensions["run_report_path"] = str(path)
            state.extensions["trace_summary"] = trace_summary(state)
        except Exception:
            logger.exception("run report failed")
        logger.info(
            "orchestrator done id=%s status=%s path=%s qa=%s attempts=%s",
            state.state_id, state.status, state.generated_path, state.qa_passed, state.attempts,
        )
        try:
            _phase_d_e_finalize(state)
        except Exception:
            logger.exception("phase D/E finalize failed")
        return state


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
        from lumen.platform.queue_backpressure import check_enqueue_allowed
        ok_bp, reason_bp = check_enqueue_allowed(f"tg:{int(user_id or 0)}", kind="generate")
        if not ok_bp:
            return GenerationResult(success=False, errors=[f"backpressure:{reason_bp}"], metadata={"backpressure": True})
    except Exception as _bp:
        if (os.getenv("ENVIRONMENT") or "").strip().lower() in {"production", "prod", "staging"}:
            return GenerationResult(success=False, errors=[f"backpressure_error:{type(_bp).__name__}"], metadata={"backpressure": True})

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
        },
    )




def _resume_or_rerun(state, ctx, board, orch, decision: str = "approved"):
    """Prefer official LangGraph Command(resume) when an interrupt is pending."""
    ext = state.extensions or {}
    pending = ext.get("pending_action") or {}
    tool = str(pending.get("tool") or state.capability_id or "")
    is_lg = (
        ext.get("langgraph_interrupt")
        or ext.get("hitl_status") == "awaiting_approval"
        or tool == "langgraph_plan_approve"
    )
    if is_lg:
        try:
            from .langgraph_pipeline import resume_langgraph_hitl
            return resume_langgraph_hitl(state, decision, context=ctx, board=board)
        except Exception as exc:
            state.extensions = dict(ext)
            state.extensions["hitl_resume_error"] = f"{type(exc).__name__}:{exc}"
            if str(decision).lower() in {"rejected", "reject", "no", "cancel"}:
                state.status = "FAILED"
                state.final_message = state.final_message or f"HITL reject failed: {exc}"
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
    if tool in {"generate_bot", "refine_bot", "langgraph_plan_approve"}:
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
    if tool in {"generate_bot", "refine_bot", "langgraph_plan_approve"}:
        return _resume_or_rerun(state, ctx, board, orch, decision="approved")
    from .tools import execute_tool_gated
    state = execute_tool_gated(state, tool, dict(pending.get("params") or {}), skip_hitl=True)
    board.put(state)
    return orch._deliver(state)

