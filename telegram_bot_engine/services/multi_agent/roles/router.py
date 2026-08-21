"""Router agent — intent + tool selection only. Never builds. Never plans specs."""
from __future__ import annotations

from typing import Any, Optional

from ..context_views import router_view
from ..protocol import Agent
from ..state import AgentRole, AgentState, AgentStatus

# Tools the router may surface (extensible)
ROUTER_TOOLS = frozenset({
    "generate_bot", "refine_bot", "clone_repo", "create_repo",
    "git_push", "git_pull", "host_start", "host_stop", "host_status",
    "host_diagnose", "repo_inspect", "repo_understand", "repo_modify",
    "chat_or_other",
})


class RouterAgent(Agent):
    role = AgentRole.ROUTER.value
    name = "router"
    order = 10

    def run(self, state: AgentState, *, context: Optional[dict[str, Any]] = None) -> AgentState:
        state.transition(AgentStatus.ROUTING, role=AgentRole.ROUTER)
        view = router_view(state)
        text = str(view.get("user_text") or "")
        try:
            from telegram_bot_engine.services.chat_router import route_message
            route = route_message(text)
            if getattr(route, "ok", False):
                cap = str(getattr(route, "capability_id", "") or "")
                state.capability_id = cap if cap in ROUTER_TOOLS or cap else cap
                state.route_params = dict(getattr(route, "params", None) or {})
                state.user_intent = state.capability_id or "unknown"
            else:
                low = text.lower()
                if any(k in low for k in ("بوت", "bot", "generate", "اعمل", "أنشئ", "انشئ")):
                    state.user_intent = "generate_bot"
                    state.capability_id = "generate_bot"
                else:
                    state.user_intent = "chat_or_other"
                    state.capability_id = "chat_or_other"
            # Isolation marker: router does not write strict_spec / paths
            state.extensions["router"] = {
                "tools_allowed": sorted(ROUTER_TOOLS),
                "selected": state.user_intent,
            }
            state.record(AgentRole.ROUTER, "routed", state.user_intent)
        except Exception as exc:
            state.user_intent = "generate_bot"
            state.capability_id = "generate_bot"
            state.record(AgentRole.ROUTER, "route_fallback", type(exc).__name__)
        return state


def run_router(state: AgentState) -> AgentState:
    return RouterAgent().run(state)
