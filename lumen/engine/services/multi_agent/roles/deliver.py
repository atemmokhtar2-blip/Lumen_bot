"""Deliver agent — final user-facing message (does not rewrite FAILED → DELIVERED)."""
from __future__ import annotations

from typing import Any, Optional

from ..context_views import deliver_view
from ..protocol import Agent
from ..state import AgentRole, AgentState, AgentStatus


class DeliverAgent(Agent):
    role = "DELIVER"
    name = "deliver"
    order = 90

    def can_run(self, state: AgentState) -> bool:
        return state.status in {
            AgentStatus.PASSED.value,
            AgentStatus.FAILED.value,
            AgentStatus.DELIVERED.value,
            AgentStatus.CANCELLED.value,
            AgentStatus.AWAITING_CONFIRMATION.value,
        }

    def run(self, state: AgentState, *, context: Optional[dict[str, Any]] = None) -> AgentState:
        if state.status == AgentStatus.AWAITING_CONFIRMATION.value:
            return state
        view = deliver_view(state)
        terminal_failed = str(state.status).lower() in {
            AgentStatus.FAILED.value.lower(),
            AgentStatus.CANCELLED.value.lower(),
        }
        if (state.qa_passed or state.status == AgentStatus.PASSED.value) and not terminal_failed:
            state.final_message = (
                f"✅ تم البناء بنجاح\n"
                f"المسار: {state.generated_path or '—'}\n"
                f"QA: PASSED\n"
                f"المحاولات: {state.attempts}/{state.max_attempts}\n"
                f"state_id: {state.state_id}"
            )
            try:
                state.transition(AgentStatus.DELIVERED, role=AgentRole.ORCHESTRATOR, force=True)
            except Exception:
                state.status = AgentStatus.DELIVERED.value
        elif view.get("clarification_needed") and view.get("clarification_questions"):
            qs = view["clarification_questions"]
            state.final_message = (
                "المعماري يحتاج توضيح:\n"
                + "\n".join(f"• {q}" for q in qs[:5])
                + f"\nstate_id: {state.state_id}"
            )
            # Clarification is not a successful delivery
            if not terminal_failed:
                try:
                    state.transition(AgentStatus.FAILED, role=AgentRole.ORCHESTRATOR, force=True)
                except Exception:
                    state.status = AgentStatus.FAILED.value
        else:
            errs = (state.qa_report or {}).get("errors") or state.build_errors or []
            state.final_message = (
                f"انتهى المسار: {state.status}\n"
                f"المسار: {state.generated_path or '—'}\n"
                f"QA: {'PASSED' if state.qa_passed else 'FAILED'}\n"
                f"محاولات: {state.attempts}/{state.max_attempts}\n"
                f"تفاصيل: {'; '.join(str(e) for e in errs[:5])}\n"
                f"state_id: {state.state_id}"
            )
            # CRITICAL: keep FAILED — never promote to DELIVERED on failure
            if not terminal_failed and not (state.qa_passed or state.status == AgentStatus.PASSED.value):
                try:
                    state.transition(AgentStatus.FAILED, role=AgentRole.ORCHESTRATOR, force=True)
                except Exception:
                    state.status = AgentStatus.FAILED.value
        state.record("DELIVER", "message_composed", state.status)
        return state


def run_deliver(state: AgentState) -> AgentState:
    return DeliverAgent().run(state)
