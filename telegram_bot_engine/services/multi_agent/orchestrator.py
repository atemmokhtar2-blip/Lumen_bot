"""
Extensible Multi-Agent Orchestrator.

Phase C: Critic repair loop — QA FAIL → Architect repair → Builder → Critic
until PASSED or max_attempts.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

from .blackboard import BlackboardStore, get_blackboard
from .registry import AgentRegistry, get_registry
from .state import AgentRole, AgentState, AgentStatus

logger = logging.getLogger(__name__)


def orchestrator_enabled() -> bool:
    return (os.environ.get("MULTI_AGENT_ORCHESTRATOR") or "1").strip().lower() not in {
        "0", "false", "no", "off",
    }


def _max_attempts(state: AgentState) -> int:
    try:
        env = int(os.environ.get("MULTI_AGENT_MAX_ATTEMPTS") or state.max_attempts or 3)
    except ValueError:
        env = 3
    return max(1, min(env, 5))


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

        # 2) Build–QA loop (Phase C) for generate_bot / refine_bot
        while True:
            # Architect (fresh plan or repair using qa_summary in architect_view)
            try:
                state.transition(AgentStatus.PLANNING, role=AgentRole.ORCHESTRATOR, force=True)
            except Exception:
                state.status = AgentStatus.PLANNING.value
            state = self._run_agent("architect", state, ctx)

            # Builder + gate
            state = self._builder_with_gate(state, ctx)

            # Critic only if build produced a path
            if state.build_success and (state.generated_path or "").strip():
                state = self._run_agent("critic", state, ctx)
            else:
                state.qa_passed = False
                if not state.qa_report:
                    state.qa_report = {
                        "ok": False,
                        "errors": list(state.build_errors or ["build_failed"]),
                        "attempt": state.attempts,
                    }
                try:
                    state.transition(AgentStatus.FAILED, role=AgentRole.ORCHESTRATOR, detail="no_build", force=True)
                except Exception:
                    state.status = AgentStatus.FAILED.value
                self.board.put(state)

            if state.status == AgentStatus.PASSED.value or state.qa_passed:
                break

            # Repair decision — verified template beats endless text-simplify
            from .repair import build_repair_directive, spec_hash, record_repair_history
            from .fallback_template import (
                should_trigger_verified_fallback,
                run_verified_fallback_on_state,
            )
            directive = build_repair_directive(state)
            hist = list((state.extensions or {}).get("repair_history") or [])
            cur_h = spec_hash(state.strict_spec)
            stagnant = bool(hist) and any(h.get("spec_hash") == cur_h for h in hist[-2:])
            directive.stagnant = stagnant
            state.extensions["last_repair"] = directive.to_dict()
            try:
                record_repair_history(state, directive, cur_h)
            except Exception:
                pass

            exhausted = int(state.attempts or 0) >= max_att
            already = bool((state.extensions or {}).get("fallback_template_tried"))
            if should_trigger_verified_fallback(
                attempts=int(state.attempts or 0),
                stagnant=stagnant,
                already_tried=already,
            ) or (exhausted and not already):
                state.record(
                    AgentRole.ORCHESTRATOR,
                    "verified_fallback_trigger",
                    f"stagnant={stagnant} attempts={state.attempts} exhausted={exhausted}",
                )
                self.board.put(state)
                work = Path(
                    ctx.get("work_dir")
                    or (state.extensions or {}).get("work_dir")
                    or ""
                )
                state = run_verified_fallback_on_state(state, work_dir=work)
                self.board.put(state)
                # Real QA: run Critic on verified build (do not fake qa_passed)
                if state.build_success and (state.generated_path or "").strip():
                    state = self._run_agent("critic", state, ctx)
                    self.board.put(state)
                    if state.status == AgentStatus.PASSED.value or state.qa_passed:
                        break
                    # Critic failed on verified template — stop (no more random repair)
                    state.record(
                        AgentRole.ORCHESTRATOR,
                        "verified_fallback_qa_failed",
                        str((state.qa_report or {}).get("errors") or state.build_errors)[:200],
                    )
                    break
                # Build itself failed
                state.record(
                    AgentRole.ORCHESTRATOR,
                    "repair_exhausted" if exhausted else "verified_fallback_build_failed",
                    f"attempts={state.attempts} max={max_att} errs={state.build_errors[:3]}",
                )
                break

            if exhausted:
                state.record(
                    AgentRole.ORCHESTRATOR,
                    "repair_exhausted",
                    f"attempts={state.attempts} max={max_att}",
                )
                break

            state.record(
                AgentRole.ORCHESTRATOR,
                "repair_loop",
                f"attempt={state.attempts} stagnant={stagnant} errors={(state.qa_report or {}).get('errors', [])[:3]}",
            )
            try:
                state.transition(AgentStatus.PLANNING, role=AgentRole.ORCHESTRATOR, force=True)
            except Exception:
                state.status = AgentStatus.PLANNING.value
            state.build_success = False
            state.extensions["last_failed_path"] = state.generated_path
            state.generated_path = ""
            state.qa_passed = False
            self.board.put(state)

        return self._deliver(state)

    def _deliver(self, state: AgentState) -> AgentState:
        from .context_views import deliver_view
        dview = deliver_view(state)
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
        return state


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
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    state = AgentState(
        user_id=int(user_id or 0),
        user_text=request or "",
        spec_request=(spec_request or request or ""),
        preferred_keys=list(preferred_keys or []),
    )
    state.extensions["work_dir"] = str(work)
    orch = Orchestrator(registry=registry, board=board)
    state = orch.run(state, context={"work_dir": work})

    result = (state.extensions or {}).pop("_generation_result", None)
    state.extensions.pop("_generation_result", None)
    try:
        orch.board.put(state)
    except Exception:
        pass

    if result is not None:
        try:
            meta = dict(getattr(result, "metadata", None) or {})
            meta["multi_agent"] = state.to_dict()
            result.metadata = meta
            # If final QA failed after retries, surface honesty
            if not state.qa_passed and getattr(result, "success", False):
                meta["qa_failed_after_retries"] = True
                result.metadata = meta
        except Exception:
            pass
        return result

    from telegram_bot_engine.core.result import GenerationResult
    return GenerationResult(
        success=False,
        errors=list(state.build_errors or ["orchestrator_no_result"]),
        metadata={"multi_agent": state.to_dict()},
    )


def save_state(state: AgentState) -> AgentState:
    return get_blackboard().put(state)


def get_state(state_id: str) -> Optional[AgentState]:
    return get_blackboard().get(state_id)


def latest_for_user(user_id: int) -> Optional[AgentState]:
    return get_blackboard().latest_for_user(user_id)


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
    if tool in {"generate_bot", "refine_bot"}:
        return orch.run(state, context=ctx)
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
    if tool in {"generate_bot", "refine_bot"}:
        return orch.run(state, context=ctx)
    from .tools import execute_tool_gated
    state = execute_tool_gated(state, tool, dict(pending.get("params") or {}), skip_hitl=True)
    board.put(state)
    return orch._deliver(state)

