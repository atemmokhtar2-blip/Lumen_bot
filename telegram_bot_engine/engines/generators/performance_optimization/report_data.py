"""
Performance Optimization Report (Specification 036 — ULTRA CRITICAL).

Intelligent Performance Optimization Engine output artefacts.
Improves speed and resource usage without changing behaviour or business logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


SOURCE_SECURITY_REVIEW = "security_review_report"
SOURCE_CODE_OPTIMIZATION = "code_optimization_report"
SOURCE_BUSINESS_LOGIC = "business_logic_report"
SOURCE_ARCHITECTURE_DECISION = "architecture_decision_report"
SOURCE_PROJECT_CONTEXT = "project_context_report"
SOURCE_CODE_PLAN = "code_generation_plan"

ALL_SOURCES = (
    SOURCE_SECURITY_REVIEW,
    SOURCE_CODE_OPTIMIZATION,
    SOURCE_BUSINESS_LOGIC,
    SOURCE_ARCHITECTURE_DECISION,
    SOURCE_PROJECT_CONTEXT,
    SOURCE_CODE_PLAN,
)

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

# Bottleneck / issue types
BN_NESTED_LOOP = "nested_loop"
BN_HEAVY_LOOP = "heavy_loop"
BN_RECURSION = "unbounded_recursion"
BN_CPU_HEAVY = "cpu_heavy_operation"
BN_MEMORY_ALLOC = "excessive_allocation"
BN_MEMORY_LEAK = "potential_memory_leak"
BN_ALGORITHM = "suboptimal_algorithm"
BN_DB_REPEATED = "repeated_query"
BN_DB_NO_INDEX = "missing_index_hint"
BN_DB_N_PLUS_1 = "n_plus_one_query"
BN_API_REPEATED = "repeated_api_call"
BN_API_NO_TIMEOUT = "missing_timeout"
BN_API_NO_RETRY = "missing_retry"
BN_TG_RATE = "telegram_rate_risk"
BN_TG_POLLING = "inefficient_polling"
BN_NO_CACHE = "missing_cache_opportunity"
BN_SYNC_BLOCKING = "blocking_sync_call"
BN_LOCK_RISK = "lock_contention_risk"
BN_RACE = "race_condition_risk"

ALL_BOTTLENECK_TYPES = (
    BN_NESTED_LOOP, BN_HEAVY_LOOP, BN_RECURSION, BN_CPU_HEAVY,
    BN_MEMORY_ALLOC, BN_MEMORY_LEAK, BN_ALGORITHM,
    BN_DB_REPEATED, BN_DB_NO_INDEX, BN_DB_N_PLUS_1,
    BN_API_REPEATED, BN_API_NO_TIMEOUT, BN_API_NO_RETRY,
    BN_TG_RATE, BN_TG_POLLING, BN_NO_CACHE,
    BN_SYNC_BLOCKING, BN_LOCK_RISK, BN_RACE,
)

OPT_LOOP_FLATTEN = "loop_flatten"
OPT_LIST_COMP = "list_comprehension"
OPT_GENERATOR = "generator_use"
OPT_CACHE_ADD = "cache_hint"
OPT_ASYNC_CONVERT = "async_hint"
OPT_BATCH = "batch_operation"
OPT_CONNECTION_REUSE = "connection_reuse"
OPT_TIMEOUT_ADD = "timeout_added"
OPT_ALGO_REPLACE = "algorithm_hint"
OPT_DB_CACHE = "query_cache_hint"
OPT_TG_BATCH = "telegram_batch_hint"

ALL_OPT_TYPES = (
    OPT_LOOP_FLATTEN, OPT_LIST_COMP, OPT_GENERATOR, OPT_CACHE_ADD,
    OPT_ASYNC_CONVERT, OPT_BATCH, OPT_CONNECTION_REUSE, OPT_TIMEOUT_ADD,
    OPT_ALGO_REPLACE, OPT_DB_CACHE, OPT_TG_BATCH,
)

RULE_NO_BEHAVIOR_CHANGE = "no_behavior_change"
RULE_NO_CRITICAL_BOTTLENECK = "no_critical_bottleneck"
RULE_SELF_REVIEW_PASSED = "self_review_passed"
RULE_QUALITY_PASS = "quality_pass"
RULE_SUFFICIENT_CONFIDENCE = "sufficient_confidence"
RULE_SIMULATION_OK = "simulation_acceptable"

ALL_QUALITY_RULES = (
    RULE_NO_BEHAVIOR_CHANGE,
    RULE_NO_CRITICAL_BOTTLENECK,
    RULE_SELF_REVIEW_PASSED,
    RULE_QUALITY_PASS,
    RULE_SUFFICIENT_CONFIDENCE,
    RULE_SIMULATION_OK,
)

MIN_QUALITY_SCORE = 70.0

CACHE_HIT = "hit"
CACHE_MISS = "miss"
CACHE_DISABLED = "disabled"

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"
CONFIDENCE_HIGH_THRESHOLD = 0.85
CONFIDENCE_MEDIUM_THRESHOLD = 0.60

VERDICT_READY = "ready"
VERDICT_READY_WITH_WARNINGS = "ready_with_warnings"
VERDICT_NOT_READY = "not_ready"

ALL_VERDICTS = (VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY)

STATUS_OPEN = "open"
STATUS_OPTIMIZED = "optimized"
STATUS_ACCEPTED = "accepted"
STATUS_FALSE_POSITIVE = "false_positive"


@dataclass
class Bottleneck:
    bottleneck_id: str
    bottleneck_type: str
    severity: str = SEVERITY_HIGH
    message: str = ""
    location: str = ""
    unit_id: str = ""
    snippet: str = ""
    estimated_impact: str = ""
    status: str = STATUS_OPEN
    resolution_hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bottleneck_id": self.bottleneck_id,
            "bottleneck_type": self.bottleneck_type,
            "severity": self.severity,
            "message": self.message,
            "location": self.location,
            "unit_id": self.unit_id,
            "snippet": self.snippet[:200] if self.snippet else "",
            "estimated_impact": self.estimated_impact,
            "status": self.status,
            "resolution_hint": self.resolution_hint,
        }


@dataclass
class PerformanceAction:
    action_id: str
    action_type: str
    unit_id: str = ""
    description: str = ""
    before_hint: str = ""
    after_hint: str = ""
    behavior_safe: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "unit_id": self.unit_id,
            "description": self.description,
            "before_hint": self.before_hint,
            "after_hint": self.after_hint,
            "behavior_safe": self.behavior_safe,
        }


@dataclass
class PerfUnit:
    unit_id: str
    class_name: str = ""
    method_name: str = ""
    original_code: str = ""
    optimized_code: str = ""
    bottlenecks_found: int = 0
    actions_applied: int = 0
    quality_before: float = 0.0
    quality_after: float = 0.0
    time_complexity_hint: str = ""
    space_complexity_hint: str = ""
    changed: bool = False
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "class_name": self.class_name,
            "method_name": self.method_name,
            "original_code": self.original_code,
            "optimized_code": self.optimized_code,
            "bottlenecks_found": self.bottlenecks_found,
            "actions_applied": self.actions_applied,
            "quality_before": self.quality_before,
            "quality_after": self.quality_after,
            "time_complexity_hint": self.time_complexity_hint,
            "space_complexity_hint": self.space_complexity_hint,
            "changed": self.changed,
            "notes": self.notes,
        }


@dataclass
class LoadSimulation:
    users: int
    estimated_latency_ms: float = 0.0
    estimated_cpu_pct: float = 0.0
    estimated_memory_mb: float = 0.0
    bottleneck_risk: str = "low"
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "users": self.users,
            "estimated_latency_ms": self.estimated_latency_ms,
            "estimated_cpu_pct": self.estimated_cpu_pct,
            "estimated_memory_mb": self.estimated_memory_mb,
            "bottleneck_risk": self.bottleneck_risk,
            "notes": self.notes,
        }


@dataclass
class CachePlan:
    opportunity_id: str
    data_description: str = ""
    suggested_ttl_seconds: int = 300
    scope: str = "process"
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "data_description": self.data_description,
            "suggested_ttl_seconds": self.suggested_ttl_seconds,
            "scope": self.scope,
            "reason": self.reason,
        }


@dataclass
class PerformanceFinding:
    severity: str
    code: str
    message: str
    affected: str = ""
    resolution_hint: str = ""
    category: str = "performance"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "affected": self.affected,
            "resolution_hint": self.resolution_hint,
            "category": self.category,
        }


@dataclass
class CacheInfo:
    status: str = CACHE_MISS
    key: str = ""
    created_at: str = ""
    hits: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "key": self.key,
            "created_at": self.created_at,
            "hits": self.hits,
        }


@dataclass
class PerformanceProvenance:
    engine_name: str = "performance_optimization"
    engine_version: str = "1.0.0"
    sources_used: List[str] = field(default_factory=list)
    sources_missing: List[str] = field(default_factory=list)
    generated_at: str = ""
    confidence: float = 0.0
    confidence_level: str = CONFIDENCE_LOW
    self_review_passed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine_name": self.engine_name,
            "engine_version": self.engine_version,
            "sources_used": list(self.sources_used),
            "sources_missing": list(self.sources_missing),
            "generated_at": self.generated_at,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level,
            "self_review_passed": self.self_review_passed,
        }


@dataclass
class PerformanceReport:
    report_id: str = ""
    units: List[PerfUnit] = field(default_factory=list)
    bottlenecks: List[Bottleneck] = field(default_factory=list)
    actions: List[PerformanceAction] = field(default_factory=list)
    findings: List[PerformanceFinding] = field(default_factory=list)
    simulations: List[LoadSimulation] = field(default_factory=list)
    cache_plans: List[CachePlan] = field(default_factory=list)
    unit_count: int = 0
    bottleneck_count: int = 0
    critical_bottleneck_count: int = 0
    open_critical_count: int = 0
    action_count: int = 0
    average_quality_after: float = 0.0
    self_review_passed: bool = False
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: PerformanceProvenance = field(default_factory=PerformanceProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "units": [u.to_dict() for u in self.units],
            "bottlenecks": [b.to_dict() for b in self.bottlenecks],
            "actions": [a.to_dict() for a in self.actions],
            "findings": [f.to_dict() for f in self.findings],
            "simulations": [s.to_dict() for s in self.simulations],
            "cache_plans": [c.to_dict() for c in self.cache_plans],
            "unit_count": self.unit_count,
            "bottleneck_count": self.bottleneck_count,
            "critical_bottleneck_count": self.critical_bottleneck_count,
            "open_critical_count": self.open_critical_count,
            "action_count": self.action_count,
            "average_quality_after": self.average_quality_after,
            "self_review_passed": self.self_review_passed,
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_SECURITY_REVIEW", "SOURCE_CODE_OPTIMIZATION", "SOURCE_BUSINESS_LOGIC",
    "SOURCE_ARCHITECTURE_DECISION", "SOURCE_PROJECT_CONTEXT", "SOURCE_CODE_PLAN",
    "ALL_SOURCES",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW",
    "BN_NESTED_LOOP", "BN_HEAVY_LOOP", "BN_RECURSION", "BN_CPU_HEAVY",
    "BN_MEMORY_ALLOC", "BN_MEMORY_LEAK", "BN_ALGORITHM",
    "BN_DB_REPEATED", "BN_DB_NO_INDEX", "BN_DB_N_PLUS_1",
    "BN_API_REPEATED", "BN_API_NO_TIMEOUT", "BN_API_NO_RETRY",
    "BN_TG_RATE", "BN_TG_POLLING", "BN_NO_CACHE",
    "BN_SYNC_BLOCKING", "BN_LOCK_RISK", "BN_RACE",
    "ALL_BOTTLENECK_TYPES",
    "OPT_LOOP_FLATTEN", "OPT_LIST_COMP", "OPT_GENERATOR", "OPT_CACHE_ADD",
    "OPT_ASYNC_CONVERT", "OPT_BATCH", "OPT_CONNECTION_REUSE", "OPT_TIMEOUT_ADD",
    "OPT_ALGO_REPLACE", "OPT_DB_CACHE", "OPT_TG_BATCH",
    "ALL_OPT_TYPES",
    "RULE_NO_BEHAVIOR_CHANGE", "RULE_NO_CRITICAL_BOTTLENECK", "RULE_SELF_REVIEW_PASSED",
    "RULE_QUALITY_PASS", "RULE_SUFFICIENT_CONFIDENCE", "RULE_SIMULATION_OK",
    "ALL_QUALITY_RULES", "MIN_QUALITY_SCORE",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "STATUS_OPEN", "STATUS_OPTIMIZED", "STATUS_ACCEPTED", "STATUS_FALSE_POSITIVE",
    "Bottleneck", "PerformanceAction", "PerfUnit", "LoadSimulation", "CachePlan",
    "PerformanceFinding", "CacheInfo", "PerformanceProvenance", "PerformanceReport",
]
