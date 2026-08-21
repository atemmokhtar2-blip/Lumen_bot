"""Critic role — Phase A: one-shot structural QA (no repair loop yet)."""
from __future__ import annotations

from pathlib import Path

from ..state import AgentRole, AgentState, AgentStatus


def run_critic(state: AgentState) -> AgentState:
    state.set_status(AgentStatus.QA, role=AgentRole.CRITIC)
    path = (state.generated_path or "").strip()
    if not path or not Path(path).is_dir():
        state.qa_passed = False
        state.qa_report = {"ok": False, "errors": ["no_generated_path"]}
        state.record(AgentRole.CRITIC, "qa_skip", "no_path")
        return state

    try:
        from telegram_bot_engine.services.gen_verify import verify_generated_project
        rep = verify_generated_project(path)
        state.qa_report = rep.to_dict() if hasattr(rep, "to_dict") else {"ok": bool(getattr(rep, "ok", False))}
        state.qa_passed = bool(getattr(rep, "ok", False))
        state.record(
            AgentRole.CRITIC,
            "qa_done",
            f"ok={state.qa_passed} errors={len(state.qa_report.get('errors') or [])}",
        )
    except Exception as exc:
        # Phase A: QA tooling failure must not fake PASSED
        state.qa_passed = False
        state.qa_report = {"ok": False, "errors": [f"critic_error:{type(exc).__name__}"]}
        state.record(AgentRole.CRITIC, "qa_error", type(exc).__name__)

    if state.build_success and state.qa_passed:
        state.set_status(AgentStatus.PASSED, role=AgentRole.CRITIC)
    elif state.build_success and not state.qa_passed:
        # Phase A: record failure but do not loop (Phase C)
        state.set_status(AgentStatus.FAILED, role=AgentRole.CRITIC, detail="qa_failed")
    else:
        state.set_status(AgentStatus.FAILED, role=AgentRole.CRITIC, detail="build_or_qa_failed")
    return state
