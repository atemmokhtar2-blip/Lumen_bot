"""Router agent — intent classification only."""
from __future__ import annotations

from typing import Any, Optional

from ..protocol import Agent
from ..state import AgentRole, AgentState, AgentStatus


class RouterAgent(Agent):
    role = AgentRole.ROUTER.value
    name = "router"
    order = 10

    def run(self, state: AgentState, *, context: Optional[dict[str, Any]] = None) -> AgentState:
        state.transition(AgentStatus.ROUTING, role=AgentRole.ROUTER)
        text = state.user_text or ""
        try:
            from telegram_bot_engine.services.chat_router import route_message
            route = route_message(text)
            if getattr(route, "ok", False):
                state.capability_id = str(getattr(route, "capability_id", "") or "")
                state.route_params = dict(getattr(route, "params", None) or {})
                state.user_intent = state.capability_id or "unknown"
            else:
                low = text.lower()
                if any(k in low for k in ("بوت", "bot", "generate", "اعمل", "أنشئ", "انشئ")):
                    state.user_intent = "generate_bot"
                    state.capability_id = "generate_bot"
                else:
                    state.user_intent = "chat_or_other"
                    state.capability_id = ""
            state.record(AgentRole.ROUTER, "routed", state.user_intent)
        except Exception as exc:
            state.user_intent = "generate_bot"
            state.capability_id = "generate_bot"
            state.record(AgentRole.ROUTER, "route_fallback", type(exc).__name__)
        return state


def run_router(state: AgentState) -> AgentState:
    return RouterAgent().run(state)
