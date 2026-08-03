"""
Static Analysis Report (Specification 039 — ULTRA CRITICAL).

Intelligent Static Analysis Engine output artefacts.
Analyses code without execution; critical issues block next engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


SOURCE_CODE_REFACTORING = "code_refactoring_report"
SOURCE_ARCHITECTURE_COMPLIANCE = "architecture_compliance_report"
SOURCE_PERFORMANCE = "performance_optimization_report"
SOURCE_SECURITY = "security_review_report"
SOURCE_BUSINESS_LOGIC = "business_logic_report"
SOURCE_PROJECT_CONTEXT = "project_context_report"

ALL_SOURCES = (
    SOURCE_CODE_REFACTORING,
    SOURCE_ARCHITECTURE_COMPLIANCE,
    SOURCE_PERFORMANCE,
    SOURCE_SECURITY,
    SOURCE_BUSINESS_LOGIC,
    SOURCE_PROJECT_CONTEXT,
)

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"
SEVERITY_INFO = "info"

# Issue categories / types
ISSUE_SYNTAX = "syntax_error"
ISSUE_PARSE = "parse_error"
ISSUE_UNDEFINED_VAR = "undefined_variable"
ISSUE_UNDEFINED_METHOD = "undefined_method"
ISSUE_UNDEFINED_CLASS = "undefined_class"
ISSUE_BROKEN_REF = "broken_reference"
ISSUE_MISSING_IMPORT = "missing_import"
ISSUE_UNREACHABLE = "unreachable_code"
ISSUE_INFINITE_LOOP = "infinite_loop"
ISSUE_DEAD_BRANCH = "dead_branch"
ISSUE_UNUSED_CONDITION = "unused_condition"
ISSUE_UNINITIALIZED = "uninitialized_variable"
ISSUE_NULL_REF = "null_reference"
ISSUE_LAYER_BREAK = "layer_break"
ISSUE_INTERFACE_BREAK = "interface_break"
ISSUE_LONG_METHOD = "long_method"
ISSUE_LARGE_CLASS = "large_class"
ISSUE_FEATURE_ENVY = "feature_envy"
ISSUE_GOD_OBJECT = "god_object"
ISSUE_SHOTGUN = "shotgun_surgery"
ISSUE_LAZY_CLASS = "lazy_class"
ISSUE_SPECULATIVE = "speculative_generality"
ISSUE_MIDDLE_MAN = "middle_man"
ISSUE_PRIMITIVE = "primitive_obsession"
ISSUE_TEMP_FIELD = "temporary_field"
ISSUE_LONG_PARAMS = "long_parameter_list"
ISSUE_DUPLICATED = "duplicated_code"
ISSUE_CIRCULAR_DEP = "circular_dependency"
ISSUE_HIDDEN_COUPLING = "hidden_coupling"
ISSUE_UNSAFE_API = "unsafe_api"
ISSUE_UNSAFE_PARSE = "unsafe_parsing"
ISSUE_HEAVY_LOOP = "heavy_loop"
ISSUE_MEMORY_WASTE = "memory_waste"
ISSUE_REDUNDANT_OBJ = "redundant_object"

ALL_ISSUE_TYPES = (
    ISSUE_SYNTAX, ISSUE_PARSE, ISSUE_UNDEFINED_VAR, ISSUE_UNDEFINED_METHOD,
    ISSUE_UNDEFINED_CLASS, ISSUE_BROKEN_REF, ISSUE_MISSING_IMPORT,
    ISSUE_UNREACHABLE, ISSUE_INFINITE_LOOP, ISSUE_DEAD_BRANCH, ISSUE_UNUSED_CONDITION,
    ISSUE_UNINITIALIZED, ISSUE_NULL_REF, ISSUE_LAYER_BREAK, ISSUE_INTERFACE_BREAK,
    ISSUE_LONG_METHOD, ISSUE_LARGE_CLASS, ISSUE_FEATURE_ENVY, ISSUE_GOD_OBJECT,
    ISSUE_SHOTGUN, ISSUE_LAZY_CLASS, ISSUE_SPECULATIVE, ISSUE_MIDDLE_MAN,
    ISSUE_PRIMITIVE, ISSUE_TEMP_FIELD, ISSUE_LONG_PARAMS, ISSUE_DUPLICATED,
    ISSUE_CIRCULAR_DEP, ISSUE_HIDDEN_COUPLING, ISSUE_UNSAFE_API, ISSUE_UNSAFE_PARSE,
    ISSUE_HEAVY_LOOP, ISSUE_MEMORY_WASTE, ISSUE_REDUNDANT_OBJ,
)

RULE_NO_CRITICAL = "no_critical_issues"
RULE_SYNTAX_CLEAN = "syntax_clean"
RULE_REFS_RESOLVED = "references_resolved"
RULE_SELF_VERIFICATION = "self_verification_passed"
RULE_QUALITY_PASS = "quality_pass"
RULE_SUFFICIENT_CONFIDENCE = "sufficient_confidence"

ALL_QUALITY_RULES = (
    RULE_NO_CRITICAL,
    RULE_SYNTAX_CLEAN,
    RULE_REFS_RESOLVED,
    RULE_SELF_VERIFICATION,
    RULE_QUALITY_PASS,
    RULE_SUFFICIENT_CONFIDENCE,
)

MAX_METHOD_LINES = 40
MAX_CLASS_METHODS = 12
MAX_PARAMS = 5
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
STATUS_SUGGESTED = "suggested"
STATUS_ACCEPTED = "accepted"
STATUS_FALSE_POSITIVE = "false_positive"


@dataclass
class StaticIssue:
    issue_id: str
    issue_type: str
    severity: str = SEVERITY_MEDIUM
    message: str = ""
    location: str = ""
    unit_id: str = ""
    snippet: str = ""
    category: str = "general"  # syntax|semantic|control|data|architecture|smell|dependency|security|performance
    status: str = STATUS_OPEN
    repair_hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "issue_type": self.issue_type,
            "severity": self.severity,
            "message": self.message,
            "location": self.location,
            "unit_id": self.unit_id,
            "snippet": self.snippet[:200] if self.snippet else "",
            "category": self.category,
            "status": self.status,
            "repair_hint": self.repair_hint,
        }


@dataclass
class RepairSuggestion:
    suggestion_id: str
    issue_ids: List[str] = field(default_factory=list)
    target: str = ""
    description: str = ""
    steps: List[str] = field(default_factory=list)
    priority: str = SEVERITY_MEDIUM
    for_engine: str = ""  # hint which downstream engine might act

    def to_dict(self) -> Dict[str, Any]:
        return {
            "suggestion_id": self.suggestion_id,
            "issue_ids": list(self.issue_ids),
            "target": self.target,
            "description": self.description,
            "steps": list(self.steps),
            "priority": self.priority,
            "for_engine": self.for_engine,
        }


@dataclass
class AnalyzedUnit:
    unit_id: str
    class_name: str = ""
    method_name: str = ""
    source_code: str = ""
    issue_count: int = 0
    critical_count: int = 0
    syntax_ok: bool = True
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "class_name": self.class_name,
            "method_name": self.method_name,
            "source_code": self.source_code,
            "issue_count": self.issue_count,
            "critical_count": self.critical_count,
            "syntax_ok": self.syntax_ok,
            "notes": self.notes,
        }


@dataclass
class DependencyEdge:
    from_unit: str
    to_unit: str
    kind: str = "import"
    circular: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_unit": self.from_unit,
            "to_unit": self.to_unit,
            "kind": self.kind,
            "circular": self.circular,
        }


@dataclass
class RiskItem:
    risk_id: str
    severity: str
    title: str
    description: str = ""
    related_issue_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk_id": self.risk_id,
            "severity": self.severity,
            "title": self.title,
            "description": self.description,
            "related_issue_ids": list(self.related_issue_ids),
        }


@dataclass
class StaticFinding:
    severity: str
    code: str
    message: str
    affected: str = ""
    resolution_hint: str = ""
    category: str = "static"

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
class StaticProvenance:
    engine_name: str = "static_analysis"
    engine_version: str = "1.0.0"
    sources_used: List[str] = field(default_factory=list)
    sources_missing: List[str] = field(default_factory=list)
    generated_at: str = ""
    confidence: float = 0.0
    confidence_level: str = CONFIDENCE_LOW
    self_verification_passed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine_name": self.engine_name,
            "engine_version": self.engine_version,
            "sources_used": list(self.sources_used),
            "sources_missing": list(self.sources_missing),
            "generated_at": self.generated_at,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level,
            "self_verification_passed": self.self_verification_passed,
        }


@dataclass
class StaticAnalysisReport:
    report_id: str = ""
    units: List[AnalyzedUnit] = field(default_factory=list)
    issues: List[StaticIssue] = field(default_factory=list)
    suggestions: List[RepairSuggestion] = field(default_factory=list)
    dependencies: List[DependencyEdge] = field(default_factory=list)
    risks: List[RiskItem] = field(default_factory=list)
    findings: List[StaticFinding] = field(default_factory=list)
    unit_count: int = 0
    issue_count: int = 0
    critical_count: int = 0
    open_critical_count: int = 0
    suggestion_count: int = 0
    self_verification_passed: bool = False
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: StaticProvenance = field(default_factory=StaticProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "units": [u.to_dict() for u in self.units],
            "issues": [i.to_dict() for i in self.issues],
            "suggestions": [s.to_dict() for s in self.suggestions],
            "dependencies": [d.to_dict() for d in self.dependencies],
            "risks": [r.to_dict() for r in self.risks],
            "findings": [f.to_dict() for f in self.findings],
            "unit_count": self.unit_count,
            "issue_count": self.issue_count,
            "critical_count": self.critical_count,
            "open_critical_count": self.open_critical_count,
            "suggestion_count": self.suggestion_count,
            "self_verification_passed": self.self_verification_passed,
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_CODE_REFACTORING", "SOURCE_ARCHITECTURE_COMPLIANCE",
    "SOURCE_PERFORMANCE", "SOURCE_SECURITY", "SOURCE_BUSINESS_LOGIC",
    "SOURCE_PROJECT_CONTEXT", "ALL_SOURCES",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW", "SEVERITY_INFO",
    "ISSUE_SYNTAX", "ISSUE_PARSE", "ISSUE_UNDEFINED_VAR", "ISSUE_UNDEFINED_METHOD",
    "ISSUE_UNDEFINED_CLASS", "ISSUE_BROKEN_REF", "ISSUE_MISSING_IMPORT",
    "ISSUE_UNREACHABLE", "ISSUE_INFINITE_LOOP", "ISSUE_DEAD_BRANCH", "ISSUE_UNUSED_CONDITION",
    "ISSUE_UNINITIALIZED", "ISSUE_NULL_REF", "ISSUE_LAYER_BREAK", "ISSUE_INTERFACE_BREAK",
    "ISSUE_LONG_METHOD", "ISSUE_LARGE_CLASS", "ISSUE_FEATURE_ENVY", "ISSUE_GOD_OBJECT",
    "ISSUE_SHOTGUN", "ISSUE_LAZY_CLASS", "ISSUE_SPECULATIVE", "ISSUE_MIDDLE_MAN",
    "ISSUE_PRIMITIVE", "ISSUE_TEMP_FIELD", "ISSUE_LONG_PARAMS", "ISSUE_DUPLICATED",
    "ISSUE_CIRCULAR_DEP", "ISSUE_HIDDEN_COUPLING", "ISSUE_UNSAFE_API", "ISSUE_UNSAFE_PARSE",
    "ISSUE_HEAVY_LOOP", "ISSUE_MEMORY_WASTE", "ISSUE_REDUNDANT_OBJ",
    "ALL_ISSUE_TYPES",
    "RULE_NO_CRITICAL", "RULE_SYNTAX_CLEAN", "RULE_REFS_RESOLVED",
    "RULE_SELF_VERIFICATION", "RULE_QUALITY_PASS", "RULE_SUFFICIENT_CONFIDENCE",
    "ALL_QUALITY_RULES",
    "MAX_METHOD_LINES", "MAX_CLASS_METHODS", "MAX_PARAMS", "MIN_QUALITY_SCORE",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "STATUS_OPEN", "STATUS_SUGGESTED", "STATUS_ACCEPTED", "STATUS_FALSE_POSITIVE",
    "StaticIssue", "RepairSuggestion", "AnalyzedUnit", "DependencyEdge", "RiskItem",
    "StaticFinding", "CacheInfo", "StaticProvenance", "StaticAnalysisReport",
]
