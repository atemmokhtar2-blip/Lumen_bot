"""Critic / Reviewer agent — Phase A: Observe + structural QA + smoke feedback.

Feeds the orchestrator repair loop via qa_report. Role alias: critic/reviewer.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ..context_views import critic_view
from ..protocol import Agent
from ..state import AgentRole, AgentState, AgentStatus


class CriticAgent(Agent):
    role = AgentRole.CRITIC.value
    name = "critic"
    order = 40

    def can_run(self, state: AgentState) -> bool:
        path = (state.generated_path or "").strip()
        return bool(state.build_success and path)

    def run(self, state: AgentState, *, context: Optional[dict[str, Any]] = None) -> AgentState:
        state.transition(AgentStatus.QA, role=AgentRole.CRITIC, force=True)
        view = critic_view(state)
        path = str(view.get("generated_path") or "").strip()
        errors: list[str] = []
        warnings: list[str] = []
        details: dict[str, Any] = {}

        if not path or not Path(path).is_dir():
            state.qa_passed = False
            state.qa_report = {"ok": False, "errors": ["no_generated_path"]}
            state.record(AgentRole.CRITIC, "qa_skip", "no_path")
            state.transition(AgentStatus.FAILED, role=AgentRole.CRITIC, detail="no_path")
            return state

        # 1) gen_verify
        try:
            from lumen.engine.services.gen_verify import verify_generated_project
            rep = verify_generated_project(path)
            gv = rep.to_dict() if hasattr(rep, "to_dict") else {"ok": bool(getattr(rep, "ok", False))}
            details["gen_verify"] = gv
            if not gv.get("ok"):
                errors.extend(list(gv.get("errors") or ["gen_verify_failed"]))
            warnings.extend(list(gv.get("warnings") or []))
        except Exception as exc:
            errors.append(f"gen_verify_error:{type(exc).__name__}")
            details["gen_verify"] = {"ok": False, "error": type(exc).__name__}

        # 2) static_dev_gate — error findings are blocking
        try:
            from lumen.engine.services.static_dev_gate.engine import analyze
            sg = analyze(path)
            if hasattr(sg, "ok"):
                findings = list(getattr(sg, "findings", None) or [])
                err_msgs = [
                    f"{getattr(f, 'rule_id', '')}:{getattr(f, 'message_ar', '')}"[:200]
                    for f in findings
                    if getattr(f, "severity", "") == "error"
                ]
                details["static_dev_gate"] = {
                    "ok": bool(sg.ok),
                    "errors": int(getattr(sg, "errors", 0) or 0),
                    "warnings": int(getattr(sg, "warnings", 0) or 0),
                    "files_checked": int(getattr(sg, "files_checked", 0) or 0),
                    "error_messages": err_msgs[:15],
                }
                if not sg.ok:
                    errors.extend(err_msgs[:10] or ["static_dev_gate_failed"])
            elif isinstance(sg, dict):
                details["static_dev_gate"] = sg
                if sg.get("ok") is False:
                    errors.append("static_dev_gate_failed")
        except Exception as exc:
            warnings.append(f"static_gate_skip:{type(exc).__name__}")
            details["static_dev_gate"] = {"skipped": type(exc).__name__}

        # 3) Observe — execution feedback (smoke import / entry check)
        try:
            from lumen.bot.generation_steps.helpers import _smoke_test_project
            smoke_ok, smoke_msg = _smoke_test_project(Path(path), seconds=3.0)
            details["observe_smoke"] = {
                "ok": bool(smoke_ok),
                "message": str(smoke_msg)[:400],
            }
            if not smoke_ok:
                errors.append(f"observe_smoke:{str(smoke_msg)[:160]}")
        except Exception as exc:
            # Fallback: entry file must exist
            main = Path(path) / "main.py"
            bot = Path(path) / "bot.py"
            if not main.is_file() and not bot.is_file():
                errors.append("observe_no_entry:main.py|bot.py")
                details["observe_smoke"] = {"ok": False, "error": "no_entry"}
            else:
                warnings.append(f"observe_smoke_skip:{type(exc).__name__}")
                details["observe_smoke"] = {"skipped": type(exc).__name__}

        state.qa_passed = len(errors) == 0
        state.qa_report = {
            "ok": state.qa_passed,
            "errors": errors[:30],
            "warnings": warnings[:30],
            "details": details,
            "attempt": state.attempts,
            "role_alias": "critic",
        }
        try:
            from ..trajectory import append_trajectory
            append_trajectory(
                state,
                step="critic_qa",
                role=AgentRole.CRITIC.value,
                ok=state.qa_passed,
                detail=f"errors={len(errors)}",
                payload={"errors": errors[:8]},
            )
        except Exception:
            pass
        state.record(
            AgentRole.CRITIC,
            "qa_done",
            f"ok={state.qa_passed} errors={len(errors)} attempt={state.attempts}",
        )

        if state.qa_passed:
            state.transition(AgentStatus.PASSED, role=AgentRole.CRITIC)
        else:
            state.transition(AgentStatus.FAILED, role=AgentRole.CRITIC, detail="qa_failed")
        return state


def run_critic(state: AgentState) -> AgentState:
    return CriticAgent().run(state)
