"""
Code Optimization Report (Specification 034 — ULTRA CRITICAL).

Intelligent Code Optimization Engine output artefacts.
Optimizes generated source without changing behaviour or architecture.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


SOURCE_BUSINESS_LOGIC = "business_logic_report"
SOURCE_CLASS_GENERATION = "class_generation_report"
SOURCE_FUNCTION_GENERATION = "function_generation_report"
SOURCE_PROJECT_BUILDER = "project_builder_report"
SOURCE_ARCHITECTURE_DECISION = "architecture_decision_report"
SOURCE_CODE_PLAN = "code_generation_plan"

ALL_SOURCES = (
    SOURCE_BUSINESS_LOGIC,
    SOURCE_CLASS_GENERATION,
    SOURCE_FUNCTION_GENERATION,
    SOURCE_PROJECT_BUILDER,
    SOURCE_ARCHITECTURE_DECISION,
    SOURCE_CODE_PLAN,
)

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

OPT_DEAD_CODE = "dead_code_removal"
OPT_UNUSED_IMPORT = "unused_import_removal"
OPT_UNUSED_VARIABLE = "unused_variable_removal"
OPT_DUPLICATE_LOGIC = "duplicate_logic_removal"
OPT_DUPLICATE_CONDITION = "duplicate_condition_removal"
OPT_DUPLICATE_FUNCTION = "duplicate_function_removal"
OPT_DUPLICATE_CONSTANT = "duplicate_constant_removal"
OPT_COMPLEXITY = "complexity_reduction"
OPT_NESTED_CONDITION = "nested_condition_flatten"
OPT_NESTED_LOOP = "nested_loop_simplify"
OPT_HUGE_FUNCTION = "huge_function_split_hint"
OPT_HUGE_CLASS = "huge_class_split_hint"
OPT_MEMORY = "memory_usage"
OPT_CPU = "cpu_usage"
OPT_ALGORITHM = "algorithm_complexity"
OPT_DB_ACCESS = "database_access"
OPT_API_CALL = "api_call"
OPT_OBJECT_CREATION = "object_creation"
OPT_NAMING = "naming"
OPT_FORMATTING = "formatting"
OPT_SPACING = "spacing"
OPT_GROUPING = "grouping"
OPT_ORDERING = "ordering"

ALL_OPT_TYPES = (
    OPT_DEAD_CODE, OPT_UNUSED_IMPORT, OPT_UNUSED_VARIABLE,
    OPT_DUPLICATE_LOGIC, OPT_DUPLICATE_CONDITION, OPT_DUPLICATE_FUNCTION,
    OPT_DUPLICATE_CONSTANT, OPT_COMPLEXITY, OPT_NESTED_CONDITION,
    OPT_NESTED_LOOP, OPT_HUGE_FUNCTION, OPT_HUGE_CLASS,
    OPT_MEMORY, OPT_CPU, OPT_ALGORITHM, OPT_DB_ACCESS, OPT_API_CALL,
    OPT_OBJECT_CREATION, OPT_NAMING, OPT_FORMATTING, OPT_SPACING,
    OPT_GROUPING, OPT_ORDERING,
)

RULE_NO_BEHAVIOR_CHANGE = "no_behavior_change"
RULE_NO_ARCHITECTURE_BREAK = "no_architecture_break"
RULE_NO_INTERFACE_CHANGE = "no_interface_change"
RULE_NO_CONTRACT_CHANGE = "no_contract_change"
RULE_REGRESSION_SAFE = "regression_safe"
RULE_QUALITY_PASS = "quality_pass"
RULE_SUFFICIENT_CONFIDENCE = "sufficient_confidence"
RULE_OPTIMIZATIONS_APPLIED = "optimizations_applied"

ALL_QUALITY_RULES = (
    RULE_NO_BEHAVIOR_CHANGE,
    RULE_NO_ARCHITECTURE_BREAK,
    RULE_NO_INTERFACE_CHANGE,
    RULE_NO_CONTRACT_CHANGE,
    RULE_REGRESSION_SAFE,
    RULE_QUALITY_PASS,
    RULE_SUFFICIENT_CONFIDENCE,
    RULE_OPTIMIZATIONS_APPLIED,
)

MAX_FUNCTION_LINES = 40
MAX_CLASS_LINES = 300
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


@dataclass
class OptimizedUnit:
    unit_id: str
    unit_type: str = "method"  # method | class | module | file
    original_source: str = ""
    optimized_source: str = ""
    quality_before: float = 0.0
    quality_after: float = 0.0
    lines_before: int = 0
    lines_after: int = 0
    optimizations_applied: List[str] = field(default_factory=list)
    behavior_preserved: bool = True
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "unit_type": self.unit_type,
            "original_source": self.original_source,
            "optimized_source": self.optimized_source,
            "quality_before": self.quality_before,
            "quality_after": self.quality_after,
            "lines_before": self.lines_before,
            "lines_after": self.lines_after,
            "optimizations_applied": list(self.optimizations_applied),
            "behavior_preserved": self.behavior_preserved,
            "notes": self.notes,
        }


@dataclass
class OptimizationAction:
    action_id: str
    opt_type: str
    severity: str = SEVERITY_MEDIUM
    message: str = ""
    affected_ids: List[str] = field(default_factory=list)
    before_snippet: str = ""
    after_snippet: str = ""
    behavior_safe: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "opt_type": self.opt_type,
            "severity": self.severity,
            "message": self.message,
            "affected_ids": list(self.affected_ids),
            "before_snippet": self.before_snippet,
            "after_snippet": self.after_snippet,
            "behavior_safe": self.behavior_safe,
        }


@dataclass
class OptimizationIssue:
    issue_id: str
    issue_type: str
    severity: str = SEVERITY_HIGH
    message: str = ""
    affected_ids: List[str] = field(default_factory=list)
    resolution_hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "issue_type": self.issue_type,
            "severity": self.severity,
            "message": self.message,
            "affected_ids": list(self.affected_ids),
            "resolution_hint": self.resolution_hint,
        }


@dataclass
class OptimizationFinding:
    severity: str
    code: str
    message: str
    affected: str = ""
    resolution_hint: str = ""
    category: str = "quality"

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
class OptimizationProvenance:
    engine_name: str = "code_optimization"
    engine_version: str = "1.0.0"
    sources_used: List[str] = field(default_factory=list)
    sources_missing: List[str] = field(default_factory=list)
    generated_at: str = ""
    confidence: float = 0.0
    confidence_level: str = CONFIDENCE_LOW

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine_name": self.engine_name,
            "engine_version": self.engine_version,
            "sources_used": list(self.sources_used),
            "sources_missing": list(self.sources_missing),
            "generated_at": self.generated_at,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level,
        }


@dataclass
class CodeOptimizationReport:
    report_id: str = ""
    units: List[OptimizedUnit] = field(default_factory=list)
    actions: List[OptimizationAction] = field(default_factory=list)
    issues: List[OptimizationIssue] = field(default_factory=list)
    findings: List[OptimizationFinding] = field(default_factory=list)
    unit_count: int = 0
    action_count: int = 0
    average_quality_before: float = 0.0
    average_quality_after: float = 0.0
    lines_saved: int = 0
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: OptimizationProvenance = field(default_factory=OptimizationProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "units": [u.to_dict() for u in self.units],
            "actions": [a.to_dict() for a in self.actions],
            "issues": [i.to_dict() for i in self.issues],
            "findings": [f.to_dict() for f in self.findings],
            "unit_count": self.unit_count,
            "action_count": self.action_count,
            "average_quality_before": self.average_quality_before,
            "average_quality_after": self.average_quality_after,
            "lines_saved": self.lines_saved,
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_BUSINESS_LOGIC", "SOURCE_CLASS_GENERATION", "SOURCE_FUNCTION_GENERATION",
    "SOURCE_PROJECT_BUILDER", "SOURCE_ARCHITECTURE_DECISION", "SOURCE_CODE_PLAN",
    "ALL_SOURCES",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW",
    "OPT_DEAD_CODE", "OPT_UNUSED_IMPORT", "OPT_UNUSED_VARIABLE",
    "OPT_DUPLICATE_LOGIC", "OPT_DUPLICATE_CONDITION", "OPT_DUPLICATE_FUNCTION",
    "OPT_DUPLICATE_CONSTANT", "OPT_COMPLEXITY", "OPT_NESTED_CONDITION",
    "OPT_NESTED_LOOP", "OPT_HUGE_FUNCTION", "OPT_HUGE_CLASS",
    "OPT_MEMORY", "OPT_CPU", "OPT_ALGORITHM", "OPT_DB_ACCESS", "OPT_API_CALL",
    "OPT_OBJECT_CREATION", "OPT_NAMING", "OPT_FORMATTING", "OPT_SPACING",
    "OPT_GROUPING", "OPT_ORDERING", "ALL_OPT_TYPES",
    "RULE_NO_BEHAVIOR_CHANGE", "RULE_NO_ARCHITECTURE_BREAK", "RULE_NO_INTERFACE_CHANGE",
    "RULE_NO_CONTRACT_CHANGE", "RULE_REGRESSION_SAFE", "RULE_QUALITY_PASS",
    "RULE_SUFFICIENT_CONFIDENCE", "RULE_OPTIMIZATIONS_APPLIED", "ALL_QUALITY_RULES",
    "MAX_FUNCTION_LINES", "MAX_CLASS_LINES", "MIN_QUALITY_SCORE",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "OptimizedUnit", "OptimizationAction", "OptimizationIssue", "OptimizationFinding",
    "CacheInfo", "OptimizationProvenance", "CodeOptimizationReport",
]
