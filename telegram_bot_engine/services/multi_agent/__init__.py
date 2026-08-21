"""Multi-Agent foundation — protocol, blackboard, registry, orchestrator, strict_spec."""
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
from .strict_spec import StrictSpec, validate_strict_spec, merge_spec_request, STRICT_SPEC_SCHEMA
from .context_views import router_view, architect_view, builder_view, critic_view, deliver_view
from .architect_backends import SpecBackend, GeminiSpecBackend, BridgeSpecBackend, DeterministicSpecBackend, produce_strict_spec
from .gates import architect_gate, filter_features_to_catalog, apply_catalog_filter_to_state

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
    "StrictSpec",
    "validate_strict_spec",
    "merge_spec_request",
    "STRICT_SPEC_SCHEMA",
    "router_view",
    "architect_view",
    "builder_view",
    "critic_view",
    "deliver_view",
    "SpecBackend",
    "GeminiSpecBackend",
    "BridgeSpecBackend",
    "DeterministicSpecBackend",
    "produce_strict_spec",
    "architect_gate",
    "filter_features_to_catalog",
    "apply_catalog_filter_to_state",
]
