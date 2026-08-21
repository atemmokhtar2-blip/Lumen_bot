"""Router role — intent only (wraps chat_router). Does not build."""
from __future__ import annotations

from ..state import AgentRole, AgentState, AgentStatus


def run_router(state: AgentState) -> AgentState:
    state.set_status(AgentStatus.ROUTING, role=AgentRole.ROUTER)
    text = state.user_text or ""
    try:
        from telegram_bot_engine.services.chat_router import route_message
        route = route_message(text)
        if route.ok:
            state.capability_id = str(route.capability_id or "")
            state.route_params = dict(route.params or {})
            state.user_intent = str(route.capability_id or "unknown")
        else:
            # Heuristic: generation-shaped text
            low = text.lower()
            if any(k in low for k in ("بوت", "bot", "generate", "اعمل", "أنشئ", "انشئ")):
                state.user_intent = "generate_bot"
                state.capability_id = "generate_bot"
            else:
                state.user_intent = "chat_or_other"
                state.capability_id = ""
        state.record(AgentRole.ROUTER, "routed", state.user_intent)
    except Exception as exc:
        state.user_intent = "generate_bot"  # safe default for orchestrated generate entry
        state.capability_id = "generate_bot"
        state.record(AgentRole.ROUTER, "route_fallback", type(exc).__name__)
    return state
