"""
Business Logic Generation Report (Specification 033 — ULTRA CRITICAL).

First engine that emits real production-grade business logic bodies.
Enforces Clean Code, SOLID, security, performance and self-review rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


SOURCE_CLASS_GENERATION = "class_generation_report"
SOURCE_FUNCTION_GENERATION = "function_generation_report"
SOURCE_COMPONENT_ARCHITECTURE = "component_architecture_blueprint"
SOURCE_INTERFACE_CONTRACT = "interface_contract_blueprint"
SOURCE_CODE_PLAN = "code_generation_plan"
SOURCE_MODULE_ARCHITECTURE = "module_architecture_blueprint"

ALL_SOURCES = (
    SOURCE_CLASS_GENERATION,
    SOURCE_FUNCTION_GENERATION,
    SOURCE_COMPONENT_ARCHITECTURE,
    SOURCE_INTERFACE_CONTRACT,
    SOURCE_CODE_PLAN,
    SOURCE_MODULE_ARCHITECTURE,
)

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

ISSUE_DUPLICATION = "code_duplication"
ISSUE_DEAD_CODE = "dead_code"
ISSUE_MAGIC = "magic_value"
ISSUE_HUGE_FUNCTION = "huge_function"
ISSUE_SECURITY = "security_risk"
ISSUE_SOLID = "solid_violation"
ISSUE_MISSING_ERROR_HANDLING = "missing_error_handling"
ISSUE_QUALITY = "quality_failure"

ALL_ISSUE_TYPES = (
    ISSUE_DUPLICATION, ISSUE_DEAD_CODE, ISSUE_MAGIC, ISSUE_HUGE_FUNCTION,
    ISSUE_SECURITY, ISSUE_SOLID, ISSUE_MISSING_ERROR_HANDLING, ISSUE_QUALITY,
)

RULE_NO_DUPLICATION = "no_duplication"
RULE_NO_MAGIC = "no_magic_values"
RULE_SIZE_LIMITS = "size_limits"
RULE_ERROR_HANDLING = "error_handling"
RULE_SECURITY_CLEAN = "security_clean"
RULE_SOLID = "solid"
RULE_QUALITY_PASS = "quality_pass"
RULE_SUFFICIENT_CONFIDENCE = "sufficient_confidence"

ALL_QUALITY_RULES = (
    RULE_NO_DUPLICATION,
    RULE_NO_MAGIC,
    RULE_SIZE_LIMITS,
    RULE_ERROR_HANDLING,
    RULE_SECURITY_CLEAN,
    RULE_SOLID,
    RULE_QUALITY_PASS,
    RULE_SUFFICIENT_CONFIDENCE,
)

MAX_FUNCTION_LINES = 40
MAX_PARAMS = 5
MIN_QUALITY_SCORE = 75.0

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
class LogicBody:
    method_id: str
    class_id: str = ""
    class_name: str = ""
    method_name: str = ""
    source_code: str = ""  # full implementation body
    quality_score: float = 0.0
    optimized: bool = False
    has_error_handling: bool = False
    has_logging: bool = False
    is_async: bool = False
    line_count: int = 0
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "method_id": self.method_id,
            "class_id": self.class_id,
            "class_name": self.class_name,
            "method_name": self.method_name,
            "source_code": self.source_code,
            "quality_score": self.quality_score,
            "optimized": self.optimized,
            "has_error_handling": self.has_error_handling,
            "has_logging": self.has_logging,
            "is_async": self.is_async,
            "line_count": self.line_count,
            "notes": self.notes,
        }


@dataclass
class LogicIssue:
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
class LogicFinding:
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
class OptimizationNote:
    method_id: str
    before_score: float = 0.0
    after_score: float = 0.0
    change: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "method_id": self.method_id,
            "before_score": self.before_score,
            "after_score": self.after_score,
            "change": self.change,
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
class LogicProvenance:
    engine_name: str = "business_logic_generation"
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
class BusinessLogicReport:
    """Production-grade business logic generation report."""

    report_id: str = ""
    bodies: List[LogicBody] = field(default_factory=list)
    issues: List[LogicIssue] = field(default_factory=list)
    findings: List[LogicFinding] = field(default_factory=list)
    optimizations: List[OptimizationNote] = field(default_factory=list)
    body_count: int = 0
    average_quality: float = 0.0
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: LogicProvenance = field(default_factory=LogicProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "bodies": [b.to_dict() for b in self.bodies],
            "issues": [i.to_dict() for i in self.issues],
            "findings": [f.to_dict() for f in self.findings],
            "optimizations": [o.to_dict() for o in self.optimizations],
            "body_count": self.body_count,
            "average_quality": self.average_quality,
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_CLASS_GENERATION", "SOURCE_FUNCTION_GENERATION",
    "SOURCE_COMPONENT_ARCHITECTURE", "SOURCE_INTERFACE_CONTRACT",
    "SOURCE_CODE_PLAN", "SOURCE_MODULE_ARCHITECTURE", "ALL_SOURCES",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW",
    "ISSUE_DUPLICATION", "ISSUE_DEAD_CODE", "ISSUE_MAGIC", "ISSUE_HUGE_FUNCTION",
    "ISSUE_SECURITY", "ISSUE_SOLID", "ISSUE_MISSING_ERROR_HANDLING", "ISSUE_QUALITY",
    "ALL_ISSUE_TYPES",
    "RULE_NO_DUPLICATION", "RULE_NO_MAGIC", "RULE_SIZE_LIMITS", "RULE_ERROR_HANDLING",
    "RULE_SECURITY_CLEAN", "RULE_SOLID", "RULE_QUALITY_PASS", "RULE_SUFFICIENT_CONFIDENCE",
    "ALL_QUALITY_RULES",
    "MAX_FUNCTION_LINES", "MAX_PARAMS", "MIN_QUALITY_SCORE",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "LogicBody", "LogicIssue", "LogicFinding", "OptimizationNote",
    "CacheInfo", "LogicProvenance", "BusinessLogicReport",
]
