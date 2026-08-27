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
# fallback_template is DEAD — not re-exported (import path still works for fail-loud)
from .trajectory import append_trajectory, load_trajectory, trajectory_summary
from .plan_contract import ExecutionPlan, PlanTask, build_plan_from_spec
from .findings import CritiqueFinding
from .event_wake import temporal_enabled, signal_wake, schedule_wake_cron
from .langgraph_pipeline import resume_langgraph_hitl, hitl_interrupt_enabled
from .production_policy import policy_snapshot, allow_swarm, allow_template_fallback
from .repair_worker import should_incremental_repair, run_incremental_repair
from .redis_board import (
    RedisLayeredBlackboard, list_resumable_state_ids, resume_interrupted_state,
    scan_and_resume, redis_board_enabled, enqueue_pending_resumes, enqueue_resume_job,
    append_agent_event,
)

__all__ = [
    "policy_snapshot", "allow_swarm", "allow_template_fallback",
    "temporal_enabled", "signal_wake", "schedule_wake_cron",
    "resume_langgraph_hitl", "hitl_interrupt_enabled",

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
    
    "append_trajectory",
    "load_trajectory",
    "trajectory_summary",
    "ExecutionPlan",
    "PlanTask",
    "build_plan_from_spec",
    "CritiqueFinding",
    "should_incremental_repair",
    "run_incremental_repair",
    "RedisLayeredBlackboard", "list_resumable_state_ids", "resume_interrupted_state",
    "scan_and_resume", "redis_board_enabled", "enqueue_pending_resumes", "enqueue_resume_job",
    "append_agent_event",
]

try:
    from .durable_workflow import resume_generate, get_journal
except Exception:
    resume_generate = None  # type: ignore
    get_journal = None  # type: ignore


# Phase B
try:
    from .worker_pool import get_worker_pool, submit_resume_job
except Exception:  # pragma: no cover
    get_worker_pool = None  # type: ignore
    submit_resume_job = None  # type: ignore

# Official LangGraph orchestration (optional when installed)
try:
    from .langgraph_pipeline import langgraph_available, run_langgraph_pipeline, use_langgraph_pipeline
except Exception:  # pragma: no cover
    def langgraph_available() -> bool:
        return False
    def use_langgraph_pipeline() -> bool:
        return False
    def run_langgraph_pipeline(*a, **k):
        raise RuntimeError("langgraph_not_installed")
