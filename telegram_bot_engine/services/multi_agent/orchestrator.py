"""
Extensible Multi-Agent Orchestrator.

Runs the registered agent pipeline against a BlackboardStore.
Adding a new agent = registry.register(MyAgent()) — no core edits required.
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


class Orchestrator:
    def __init__(
        self,
        registry: AgentRegistry | None = None,
        board: BlackboardStore | None = None,
    ) -> None:
        self.registry = registry or get_registry()
        self.board = board or get_blackboard()

    def run(
        self,
        state: AgentState,
        *,
        context: Optional[dict[str, Any]] = None,
    ) -> AgentState:
        ctx = dict(context or {})
        self.board.put(state)
        state.record(AgentRole.ORCHESTRATOR, "pipeline_start", f"agents={self.registry.names()}")

        for agent in self.registry.pipeline():
            if state.status in {AgentStatus.CANCELLED.value}:
                break
            # Skip remaining build chain if already failed hard before builder done
            if state.status == AgentStatus.FAILED.value and agent.order >= 40:
                # still allow critic? no — skip
                state.record(AgentRole.ORCHESTRATOR, "skip_agent", agent.name)
                continue
            if not agent.can_run(state):
                state.record(AgentRole.ORCHESTRATOR, "can_run_false", agent.name)
                continue
            # Phase B hard gate: Builder blocked without buildable StrictSpec
            if agent.name == "builder":
                from .gates import architect_gate, apply_catalog_filter_to_state
                state = apply_catalog_filter_to_state(state)
                ok, errors = architect_gate(state)
                if not ok:
                    state.build_success = False
                    state.build_errors = list(errors)
                    state.record(AgentRole.ORCHESTRATOR, "builder_blocked", ",".join(errors[:5]))
                    try:
                        state.transition(AgentStatus.FAILED, role=AgentRole.ORCHESTRATOR, detail="spec_gate")
                    except Exception:
                        state.status = AgentStatus.FAILED.value
                    self.board.put(state)
                    continue
            try:
                state = agent.run(state, context=ctx)
            except Exception as exc:
                logger.exception("agent %s crashed", agent.name)
                state.record(AgentRole.ORCHESTRATOR, "agent_crash", f"{agent.name}:{type(exc).__name__}")
                try:
                    state.transition(AgentStatus.FAILED, role=AgentRole.ORCHESTRATOR, detail=agent.name)
                except Exception:
                    state.status = AgentStatus.FAILED.value
            self.board.put(state)

        # Deliver
        from .context_views import deliver_view
        dview = deliver_view(state)
        if state.status == AgentStatus.PASSED.value:
            state.final_message = (
                f"تم البناء بنجاح.\nالمسار: {state.generated_path}\n"
                f"QA: PASSED\nstate_id: {state.state_id}"
            )
            try:
                state.transition(AgentStatus.DELIVERED, role=AgentRole.ORCHESTRATOR)
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
                f"انتهى المسار بحالة {state.status}.\n"
                f"المسار: {state.generated_path or '—'}\n"
                f"QA: {'PASSED' if state.qa_passed else 'FAILED'}\n"
                f"تفاصيل: {'; '.join(str(e) for e in qa_errs[:3])}\n"
                f"state_id: {state.state_id}"
            )
            if state.status != AgentStatus.DELIVERED.value:
                try:
                    state.transition(AgentStatus.DELIVERED, role=AgentRole.ORCHESTRATOR, force=True)
                except Exception:
                    state.status = AgentStatus.DELIVERED.value
            state.record(AgentRole.ORCHESTRATOR, "deliver_terminal", state.status)

        self.board.put(state)
        logger.info(
            "orchestrator done id=%s status=%s path=%s qa=%s",
            state.state_id, state.status, state.generated_path, state.qa_passed,
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
    # ensure not persisted
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
        except Exception:
            pass
        return result

    from telegram_bot_engine.core.result import GenerationResult
    return GenerationResult(
        success=False,
        errors=list(state.build_errors or ["orchestrator_no_result"]),
        metadata={"multi_agent": state.to_dict()},
    )


# Backward-compatible helpers
def save_state(state: AgentState) -> AgentState:
    return get_blackboard().put(state)


def get_state(state_id: str) -> Optional[AgentState]:
    return get_blackboard().get(state_id)


def latest_for_user(user_id: int) -> Optional[AgentState]:
    return get_blackboard().latest_for_user(user_id)
