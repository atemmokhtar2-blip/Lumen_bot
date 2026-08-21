"""Architect agent — structured strict_spec (Phase A uses bridge; Gemini in Phase B)."""
from __future__ import annotations

from typing import Any, Optional

from ..protocol import Agent
from ..state import AgentRole, AgentState, AgentStatus


class ArchitectAgent(Agent):
    role = AgentRole.ARCHITECT.value
    name = "architect"
    order = 20

    def run(self, state: AgentState, *, context: Optional[dict[str, Any]] = None) -> AgentState:
        state.transition(AgentStatus.PLANNING, role=AgentRole.ARCHITECT)
        text = state.spec_request or state.user_text or ""
        preferred = list(state.preferred_keys or [])
        strict: dict[str, Any] = {
            "schema": "strict_spec.v1",
            "source": "architect_bridge",
            "raw_request": text[:2000],
            "intent": state.user_intent,
            "capability_id": state.capability_id,
        }
        try:
            from telegram_bot_engine.services.engine_groq_bridge import analyze_and_prepare
            package = analyze_and_prepare(text, None)
            strict["bridge"] = {
                "needs_ai_codegen": bool(package.get("needs_ai_codegen")),
                "preset_hint": package.get("preset_hint"),
                "domain_hint": package.get("domain_hint"),
            }
            if package.get("spec_request"):
                state.spec_request = str(package["spec_request"])
                strict["spec_request"] = state.spec_request[:2000]
            pk = package.get("preferred_keys")
            if pk and not preferred:
                preferred = list(pk) if isinstance(pk, (list, tuple)) else preferred
            strict["preferred_keys"] = list(preferred)
        except Exception as exc:
            strict["bridge_error"] = type(exc).__name__
            if not state.spec_request:
                state.spec_request = text

        state.preferred_keys = preferred
        state.strict_spec = strict
        state.record(AgentRole.ARCHITECT, "spec_written", f"keys={len(preferred)}")
        return state


def run_architect(state: AgentState) -> AgentState:
    return ArchitectAgent().run(state)
