"""Router agent — intent + explicit tool selection only. Never builds."""
from __future__ import annotations

from typing import Any, Optional

from ..context_views import router_view
from ..protocol import Agent
from ..state import AgentRole, AgentState, AgentStatus
from ..tools import list_tools, select_tool


class RouterAgent(Agent):
    role = AgentRole.ROUTER.value
    name = "router"
    order = 10

    def run(self, state: AgentState, *, context: Optional[dict[str, Any]] = None) -> AgentState:
        state.transition(AgentStatus.ROUTING, role=AgentRole.ROUTER)
        view = router_view(state)
        text = str(view.get("user_text") or "")
        tools = set(list_tools())
        try:
            from lumen.engine.services.chat_router import route_message
            route = route_message(text)
            if getattr(route, "ok", False):
                cap = str(getattr(route, "capability_id", "") or "")
                state.capability_id = cap
                state.route_params = dict(getattr(route, "params", None) or {})
                state.user_intent = cap or "unknown"
            else:
                low = text.lower()
                if any(k in low for k in ("بوت", "bot", "generate", "اعمل", "أنشئ", "انشئ")):
                    state.user_intent = "generate_bot"
                    state.capability_id = "generate_bot"
                else:
                    state.user_intent = "chat_or_other"
                    state.capability_id = "chat_or_other"
        except Exception as exc:
            state.user_intent = "generate_bot"
            state.capability_id = "generate_bot"
            state.record(AgentRole.ROUTER, "route_fallback", type(exc).__name__)

        tool = select_tool(state)
        state.extensions["router"] = {
            "tools_available": sorted(tools),
            "selected_tool": tool,
            "selected": state.user_intent,
        }
        state.extensions["selected_tool"] = tool
        state.record(AgentRole.ROUTER, "routed", f"{state.user_intent}->{tool}")
        return state


def run_router(state: AgentState) -> AgentState:
    return RouterAgent().run(state)
