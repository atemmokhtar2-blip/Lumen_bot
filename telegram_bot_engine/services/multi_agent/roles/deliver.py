"""Deliver agent — final user-facing message composition (no build/QA)."""
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
        # AWAITING_CONFIRMATION keeps existing final_message from HITL
        if state.status == AgentStatus.AWAITING_CONFIRMATION.value:
            return state
        view = deliver_view(state)
        if state.qa_passed or state.status == AgentStatus.PASSED.value:
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
            try:
                state.transition(AgentStatus.DELIVERED, role=AgentRole.ORCHESTRATOR, force=True)
            except Exception:
                state.status = AgentStatus.DELIVERED.value
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
            try:
                state.transition(AgentStatus.DELIVERED, role=AgentRole.ORCHESTRATOR, force=True)
            except Exception:
                state.status = AgentStatus.DELIVERED.value
        state.record("DELIVER", "delivered", state.status)
        return state
