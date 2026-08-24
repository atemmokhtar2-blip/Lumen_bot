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
    resume_after_confirm,
    continue_after_confirm,
)
from .strict_spec import StrictSpec, validate_strict_spec, merge_spec_request, STRICT_SPEC_SCHEMA
from .context_views import router_view, architect_view, builder_view, critic_view, deliver_view
from .architect_backends import SpecBackend, GeminiSpecBackend, BridgeSpecBackend, DeterministicSpecBackend, produce_strict_spec
from .gates import architect_gate, filter_features_to_catalog, apply_catalog_filter_to_state
from .repair import RepairDirective, build_repair_directive, apply_deterministic_repair
from .hitl import PendingAction, request_confirmation, confirm_action, reject_action, parse_confirmation_message, tool_requires_confirmation, consume_execute_grant, audit_log, tool_risk
from .tools import execute_tool_gated, list_tools, select_tool
from .metrics import get_metrics, metrics_snapshot
from .circuit import get_circuit_board, CircuitBreaker
from .health import health_snapshot, liveness, readiness
from .run_report import write_run_report, recent_reports
from .tracing import ensure_trace, trace_summary
from .concurrency import active_count, orchestration_slot
from .fallback_template import should_trigger_verified_fallback, build_verified_bot, run_verified_fallback_on_state
from .redis_board import (
    RedisLayeredBlackboard, list_resumable_state_ids, resume_interrupted_state,
    scan_and_resume, redis_board_enabled,
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
    "resume_after_confirm",
    "continue_after_confirm",
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
    "RepairDirective",
    "build_repair_directive",
    "apply_deterministic_repair",
    "PendingAction", "request_confirmation", "confirm_action", "reject_action",
    "parse_confirmation_message", "tool_requires_confirmation",
    "consume_execute_grant", "audit_log", "tool_risk",
    "execute_tool_gated", "list_tools", "select_tool",
    "get_metrics", "metrics_snapshot",
    "get_circuit_board", "CircuitBreaker",
    "health_snapshot", "liveness", "readiness",
    "write_run_report", "recent_reports",
    "ensure_trace", "trace_summary",
    "active_count", "orchestration_slot",
    "should_trigger_verified_fallback", "build_verified_bot", "run_verified_fallback_on_state",
    "RedisLayeredBlackboard", "list_resumable_state_ids", "resume_interrupted_state",
    "scan_and_resume", "redis_board_enabled",
]
