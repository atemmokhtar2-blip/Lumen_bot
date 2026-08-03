"""
Code Refactoring Report (Specification 038 — ULTRA CRITICAL).

Intelligent Code Refactoring Engine output artefacts.
Improves design and maintainability without changing behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


SOURCE_ARCHITECTURE_COMPLIANCE = "architecture_compliance_report"
SOURCE_PERFORMANCE = "performance_optimization_report"
SOURCE_SECURITY = "security_review_report"
SOURCE_CODE_OPTIMIZATION = "code_optimization_report"
SOURCE_BUSINESS_LOGIC = "business_logic_report"
SOURCE_PROJECT_CONTEXT = "project_context_report"

ALL_SOURCES = (
    SOURCE_ARCHITECTURE_COMPLIANCE,
    SOURCE_PERFORMANCE,
    SOURCE_SECURITY,
    SOURCE_CODE_OPTIMIZATION,
    SOURCE_BUSINESS_LOGIC,
    SOURCE_PROJECT_CONTEXT,
)

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

# Smell / detection types
SMELL_LARGE_CLASS = "large_class"
SMELL_LARGE_METHOD = "large_method"
SMELL_DUPLICATED_LOGIC = "duplicated_logic"
SMELL_DUPLICATED_CODE = "duplicated_code"
SMELL_LONG_PARAMS = "long_parameter_list"
SMELL_COMPLEX_CONDITION = "complex_condition"
SMELL_DEEP_NESTING = "deep_nesting"
SMELL_POOR_NAMING = "poor_naming"
SMELL_HIDDEN_DEPENDENCY = "hidden_dependency"
SMELL_CODE_SMELL = "code_smell"
SMELL_DEAD_CODE = "dead_code"
SMELL_FEATURE_ENVY = "feature_envy"

ALL_SMELL_TYPES = (
    SMELL_LARGE_CLASS, SMELL_LARGE_METHOD, SMELL_DUPLICATED_LOGIC,
    SMELL_DUPLICATED_CODE, SMELL_LONG_PARAMS, SMELL_COMPLEX_CONDITION,
    SMELL_DEEP_NESTING, SMELL_POOR_NAMING, SMELL_HIDDEN_DEPENDENCY,
    SMELL_CODE_SMELL, SMELL_DEAD_CODE, SMELL_FEATURE_ENVY,
)

# Refactoring action types
REF_EXTRACT_METHOD = "extract_method"
REF_EXTRACT_CLASS = "extract_class"
REF_EXTRACT_INTERFACE = "extract_interface"
REF_MOVE_METHOD = "move_method"
REF_MOVE_CLASS = "move_class"
REF_RENAME = "rename"
REF_INLINE = "inline"
REF_SPLIT_LOGIC = "split_logic"
REF_MERGE_LOGIC = "merge_logic"
REF_DEPENDENCY = "dependency_refactoring"
REF_RENAME_PARAM = "rename_parameter"
REF_FLATTEN_NESTING = "flatten_nesting"
REF_SIMPLIFY_CONDITION = "simplify_condition"

ALL_REF_TYPES = (
    REF_EXTRACT_METHOD, REF_EXTRACT_CLASS, REF_EXTRACT_INTERFACE,
    REF_MOVE_METHOD, REF_MOVE_CLASS, REF_RENAME, REF_INLINE,
    REF_SPLIT_LOGIC, REF_MERGE_LOGIC, REF_DEPENDENCY,
    REF_RENAME_PARAM, REF_FLATTEN_NESTING, REF_SIMPLIFY_CONDITION,
)

RULE_NO_BEHAVIOR_CHANGE = "no_behavior_change"
RULE_ARCHITECTURE_PRESERVED = "architecture_preserved"
RULE_INTERFACES_PRESERVED = "interfaces_preserved"
RULE_CONTRACTS_PRESERVED = "contracts_preserved"
RULE_SELF_VERIFICATION_PASSED = "self_verification_passed"
RULE_REGRESSION_SAFE = "regression_safe"
RULE_QUALITY_PASS = "quality_pass"
RULE_SUFFICIENT_CONFIDENCE = "sufficient_confidence"

ALL_QUALITY_RULES = (
    RULE_NO_BEHAVIOR_CHANGE,
    RULE_ARCHITECTURE_PRESERVED,
    RULE_INTERFACES_PRESERVED,
    RULE_CONTRACTS_PRESERVED,
    RULE_SELF_VERIFICATION_PASSED,
    RULE_REGRESSION_SAFE,
    RULE_QUALITY_PASS,
    RULE_SUFFICIENT_CONFIDENCE,
)

MAX_METHOD_LINES = 40
MAX_CLASS_METHODS = 12
MAX_PARAMS = 5
MAX_NESTING = 3
MIN_MAINTAINABILITY = 70.0
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

STATUS_DETECTED = "detected"
STATUS_APPLIED = "applied"
STATUS_REJECTED = "rejected"
STATUS_SKIPPED = "skipped"


@dataclass
class CodeSmell:
    smell_id: str
    smell_type: str
    severity: str = SEVERITY_MEDIUM
    message: str = ""
    location: str = ""
    unit_id: str = ""
    snippet: str = ""
    status: str = STATUS_DETECTED
    resolution_hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "smell_id": self.smell_id,
            "smell_type": self.smell_type,
            "severity": self.severity,
            "message": self.message,
            "location": self.location,
            "unit_id": self.unit_id,
            "snippet": self.snippet[:200] if self.snippet else "",
            "status": self.status,
            "resolution_hint": self.resolution_hint,
        }


@dataclass
class RefactoringAction:
    action_id: str
    action_type: str
    unit_id: str = ""
    description: str = ""
    before_hint: str = ""
    after_hint: str = ""
    behavior_safe: bool = True
    architecture_safe: bool = True
    status: str = STATUS_APPLIED
    smell_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "unit_id": self.unit_id,
            "description": self.description,
            "before_hint": self.before_hint,
            "after_hint": self.after_hint,
            "behavior_safe": self.behavior_safe,
            "architecture_safe": self.architecture_safe,
            "status": self.status,
            "smell_ids": list(self.smell_ids),
        }


@dataclass
class RefactoredUnit:
    unit_id: str
    class_name: str = ""
    method_name: str = ""
    original_code: str = ""
    refactored_code: str = ""
    smells_found: int = 0
    actions_applied: int = 0
    maintainability_before: float = 0.0
    maintainability_after: float = 0.0
    changed: bool = False
    behavior_preserved: bool = True
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "class_name": self.class_name,
            "method_name": self.method_name,
            "original_code": self.original_code,
            "refactored_code": self.refactored_code,
            "smells_found": self.smells_found,
            "actions_applied": self.actions_applied,
            "maintainability_before": self.maintainability_before,
            "maintainability_after": self.maintainability_after,
            "changed": self.changed,
            "behavior_preserved": self.behavior_preserved,
            "notes": self.notes,
        }


@dataclass
class MaintainabilityScore:
    readability: float = 0.0
    maintainability: float = 0.0
    developability: float = 0.0
    extensibility: float = 0.0
    overall: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "readability": self.readability,
            "maintainability": self.maintainability,
            "developability": self.developability,
            "extensibility": self.extensibility,
            "overall": self.overall,
        }


@dataclass
class ExtensibilityPoint:
    point_id: str
    location: str = ""
    description: str = ""
    suggested_hook: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "point_id": self.point_id,
            "location": self.location,
            "description": self.description,
            "suggested_hook": self.suggested_hook,
        }


@dataclass
class RefactoringFinding:
    severity: str
    code: str
    message: str
    affected: str = ""
    resolution_hint: str = ""
    category: str = "refactoring"

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
class RefactoringProvenance:
    engine_name: str = "code_refactoring"
    engine_version: str = "1.0.0"
    sources_used: List[str] = field(default_factory=list)
    sources_missing: List[str] = field(default_factory=list)
    generated_at: str = ""
    confidence: float = 0.0
    confidence_level: str = CONFIDENCE_LOW
    self_verification_passed: bool = False
    regression_safe: bool = True

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
            "regression_safe": self.regression_safe,
        }


@dataclass
class CodeRefactoringReport:
    report_id: str = ""
    units: List[RefactoredUnit] = field(default_factory=list)
    smells: List[CodeSmell] = field(default_factory=list)
    actions: List[RefactoringAction] = field(default_factory=list)
    findings: List[RefactoringFinding] = field(default_factory=list)
    extensibility_points: List[ExtensibilityPoint] = field(default_factory=list)
    maintainability: MaintainabilityScore = field(default_factory=MaintainabilityScore)
    unit_count: int = 0
    smell_count: int = 0
    action_count: int = 0
    rejected_count: int = 0
    average_maintainability_after: float = 0.0
    self_verification_passed: bool = False
    regression_safe: bool = True
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: RefactoringProvenance = field(default_factory=RefactoringProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "units": [u.to_dict() for u in self.units],
            "smells": [s.to_dict() for s in self.smells],
            "actions": [a.to_dict() for a in self.actions],
            "findings": [f.to_dict() for f in self.findings],
            "extensibility_points": [e.to_dict() for e in self.extensibility_points],
            "maintainability": self.maintainability.to_dict(),
            "unit_count": self.unit_count,
            "smell_count": self.smell_count,
            "action_count": self.action_count,
            "rejected_count": self.rejected_count,
            "average_maintainability_after": self.average_maintainability_after,
            "self_verification_passed": self.self_verification_passed,
            "regression_safe": self.regression_safe,
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_ARCHITECTURE_COMPLIANCE", "SOURCE_PERFORMANCE", "SOURCE_SECURITY",
    "SOURCE_CODE_OPTIMIZATION", "SOURCE_BUSINESS_LOGIC", "SOURCE_PROJECT_CONTEXT",
    "ALL_SOURCES",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW",
    "SMELL_LARGE_CLASS", "SMELL_LARGE_METHOD", "SMELL_DUPLICATED_LOGIC",
    "SMELL_DUPLICATED_CODE", "SMELL_LONG_PARAMS", "SMELL_COMPLEX_CONDITION",
    "SMELL_DEEP_NESTING", "SMELL_POOR_NAMING", "SMELL_HIDDEN_DEPENDENCY",
    "SMELL_CODE_SMELL", "SMELL_DEAD_CODE", "SMELL_FEATURE_ENVY",
    "ALL_SMELL_TYPES",
    "REF_EXTRACT_METHOD", "REF_EXTRACT_CLASS", "REF_EXTRACT_INTERFACE",
    "REF_MOVE_METHOD", "REF_MOVE_CLASS", "REF_RENAME", "REF_INLINE",
    "REF_SPLIT_LOGIC", "REF_MERGE_LOGIC", "REF_DEPENDENCY",
    "REF_RENAME_PARAM", "REF_FLATTEN_NESTING", "REF_SIMPLIFY_CONDITION",
    "ALL_REF_TYPES",
    "RULE_NO_BEHAVIOR_CHANGE", "RULE_ARCHITECTURE_PRESERVED",
    "RULE_INTERFACES_PRESERVED", "RULE_CONTRACTS_PRESERVED",
    "RULE_SELF_VERIFICATION_PASSED", "RULE_REGRESSION_SAFE",
    "RULE_QUALITY_PASS", "RULE_SUFFICIENT_CONFIDENCE",
    "ALL_QUALITY_RULES",
    "MAX_METHOD_LINES", "MAX_CLASS_METHODS", "MAX_PARAMS", "MAX_NESTING",
    "MIN_MAINTAINABILITY", "MIN_QUALITY_SCORE",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "STATUS_DETECTED", "STATUS_APPLIED", "STATUS_REJECTED", "STATUS_SKIPPED",
    "CodeSmell", "RefactoringAction", "RefactoredUnit", "MaintainabilityScore",
    "ExtensibilityPoint", "RefactoringFinding", "CacheInfo",
    "RefactoringProvenance", "CodeRefactoringReport",
]
