"""Multi-Agent orchestration (Phase A: blackboard + orchestrator)."""
from .state import AgentState, AgentStatus, AgentRole, get_state, latest_for_user, save_state
from .orchestrator import orchestrate_generate, orchestrator_enabled

__all__ = [
    "AgentState",
    "AgentStatus",
    "AgentRole",
    "get_state",
    "latest_for_user",
    "save_state",
    "orchestrate_generate",
    "orchestrator_enabled",
]
