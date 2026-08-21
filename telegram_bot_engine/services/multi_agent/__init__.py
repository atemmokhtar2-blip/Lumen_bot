"""Multi-Agent foundation — protocol, blackboard, registry, orchestrator."""
from .state import (
    SCHEMA_VERSION,
    AgentState,
    AgentStatus,
    AgentRole,
    AgentEvent,
    InvalidTransition,
)
from .protocol import Agent
from .blackboard import (
    BlackboardStore,
    MemoryBlackboard,
    FileBlackboard,
    LayeredBlackboard,
    get_blackboard,
    set_blackboard,
)
from .registry import AgentRegistry, get_registry, set_registry, build_default_registry
from .orchestrator import (
    Orchestrator,
    orchestrate_generate,
    orchestrator_enabled,
    save_state,
    get_state,
    latest_for_user,
)

__all__ = [
    "SCHEMA_VERSION",
    "AgentState",
    "AgentStatus",
    "AgentRole",
    "AgentEvent",
    "InvalidTransition",
    "Agent",
    "BlackboardStore",
    "MemoryBlackboard",
    "FileBlackboard",
    "LayeredBlackboard",
    "get_blackboard",
    "set_blackboard",
    "AgentRegistry",
    "get_registry",
    "set_registry",
    "build_default_registry",
    "Orchestrator",
    "orchestrate_generate",
    "orchestrator_enabled",
    "save_state",
    "get_state",
    "latest_for_user",
]
