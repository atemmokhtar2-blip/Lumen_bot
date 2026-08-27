"""Multi-Agent foundation — LangGraph + Cline coding agent (slim surface)."""
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
from .architect_backends import (
    SpecBackend,
    GeminiSpecBackend,
    BridgeSpecBackend,
    DeterministicSpecBackend,
    produce_strict_spec,
)
from .gates import architect_gate, filter_features_to_catalog, apply_catalog_filter_to_state
from .repair import RepairDirective, build_repair_directive, apply_deterministic_repair
from .hitl import (
    PendingAction,
    request_confirmation,
    confirm_action,
    reject_action,
    parse_confirmation_message,
    tool_requires_confirmation,
    consume_execute_grant,
    audit_log,
    tool_risk,
)
from .tools import execute_tool_gated, list_tools, select_tool
from .metrics import get_metrics, metrics_snapshot
from .health import health_snapshot, liveness, readiness
from .run_report import write_run_report, recent_reports
from .tracing import ensure_trace, trace_summary
from .trajectory import append_trajectory, load_trajectory, trajectory_summary
from .plan_contract import ExecutionPlan, PlanTask, build_plan_from_spec
from .findings import CritiqueFinding
from .event_wake import temporal_enabled, signal_wake, schedule_wake_cron, handle_agent_event, EVENT_ROUTES
from .langgraph_pipeline import resume_langgraph_hitl, hitl_interrupt_enabled
from .production_policy import policy_snapshot, allow_template_fallback
from .repair_worker import should_incremental_repair, run_incremental_repair
from .dynamic_planner import assemble_plan, classify_intent
from .acceptance_check import evaluate_task, evaluate_tree
from .coding_agent import run_coding_session
from .layer_scenarios import run_all_layer_scenarios

try:
    from .langgraph_pipeline import langgraph_available, run_langgraph_pipeline, use_langgraph_pipeline
except Exception:  # pragma: no cover
    def langgraph_available() -> bool:
        return False

    def use_langgraph_pipeline() -> bool:
        return False

    def run_langgraph_pipeline(*a, **k):
        raise RuntimeError("langgraph_not_installed")

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
    "PendingAction",
    "request_confirmation",
    "confirm_action",
    "reject_action",
    "parse_confirmation_message",
    "tool_requires_confirmation",
    "consume_execute_grant",
    "audit_log",
    "tool_risk",
    "execute_tool_gated",
    "list_tools",
    "select_tool",
    "get_metrics",
    "metrics_snapshot",
    "health_snapshot",
    "liveness",
    "readiness",
    "write_run_report",
    "recent_reports",
    "ensure_trace",
    "trace_summary",
    "append_trajectory",
    "load_trajectory",
    "trajectory_summary",
    "ExecutionPlan",
    "PlanTask",
    "build_plan_from_spec",
    "CritiqueFinding",
    "temporal_enabled",
    "signal_wake",
    "schedule_wake_cron",
    "handle_agent_event",
    "EVENT_ROUTES",
    "resume_langgraph_hitl",
    "hitl_interrupt_enabled",
    "policy_snapshot",
    "allow_template_fallback",
    "should_incremental_repair",
    "run_incremental_repair",
    "assemble_plan",
    "classify_intent",
    "evaluate_task",
    "evaluate_tree",
    "run_coding_session",
    "run_all_layer_scenarios",
    "langgraph_available",
    "run_langgraph_pipeline",
    "use_langgraph_pipeline",
]
