"""Critic agent — structural QA (one-shot in Phase A; loop reserved in FSM)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ..protocol import Agent
from ..state import AgentRole, AgentState, AgentStatus


class CriticAgent(Agent):
    role = AgentRole.CRITIC.value
    name = "critic"
    order = 40

    def can_run(self, state: AgentState) -> bool:
        return bool(state.build_success) and state.status != AgentStatus.FAILED.value

    def run(self, state: AgentState, *, context: Optional[dict[str, Any]] = None) -> AgentState:
        if state.status == AgentStatus.FAILED.value and not state.build_success:
            return state
        state.transition(AgentStatus.QA, role=AgentRole.CRITIC)
        path = (state.generated_path or "").strip()
        if not path or not Path(path).is_dir():
            state.qa_passed = False
            state.qa_report = {"ok": False, "errors": ["no_generated_path"]}
            state.record(AgentRole.CRITIC, "qa_skip", "no_path")
            state.transition(AgentStatus.FAILED, role=AgentRole.CRITIC, detail="no_path")
            return state
        try:
            from telegram_bot_engine.services.gen_verify import verify_generated_project
            rep = verify_generated_project(path)
            state.qa_report = rep.to_dict() if hasattr(rep, "to_dict") else {"ok": bool(getattr(rep, "ok", False))}
            state.qa_passed = bool(getattr(rep, "ok", False))
            state.record(AgentRole.CRITIC, "qa_done", f"ok={state.qa_passed}")
        except Exception as exc:
            state.qa_passed = False
            state.qa_report = {"ok": False, "errors": [f"critic_error:{type(exc).__name__}"]}
            state.record(AgentRole.CRITIC, "qa_error", type(exc).__name__)

        if state.build_success and state.qa_passed:
            state.transition(AgentStatus.PASSED, role=AgentRole.CRITIC)
        else:
            state.transition(AgentStatus.FAILED, role=AgentRole.CRITIC, detail="qa_failed")
        return state


def run_critic(state: AgentState) -> AgentState:
    return CriticAgent().run(state)
