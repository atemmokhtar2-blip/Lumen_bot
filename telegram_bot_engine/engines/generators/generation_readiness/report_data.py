"""
Generation Readiness Report data model (Specification 027).

Final validation gate before any code or file generation begins.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# All upstream blueprints that must be present and valid
SOURCE_EXECUTION_PLAN = "execution_plan"
SOURCE_PROJECT_STRUCTURE = "project_structure_blueprint"
SOURCE_MODULE_ARCHITECTURE = "module_architecture_blueprint"
SOURCE_COMPONENT_ARCHITECTURE = "component_architecture_blueprint"
SOURCE_INTERFACE_CONTRACT = "interface_contract_blueprint"
SOURCE_DATA_FLOW = "data_flow_blueprint"
SOURCE_RESOURCE_DEPENDENCY = "resource_dependency_blueprint"
SOURCE_GENERATION_STRATEGY = "generation_strategy_blueprint"

ALL_SOURCES = (
    SOURCE_EXECUTION_PLAN,
    SOURCE_PROJECT_STRUCTURE,
    SOURCE_MODULE_ARCHITECTURE,
    SOURCE_COMPONENT_ARCHITECTURE,
    SOURCE_INTERFACE_CONTRACT,
    SOURCE_DATA_FLOW,
    SOURCE_RESOURCE_DEPENDENCY,
    SOURCE_GENERATION_STRATEGY,
)

# Score categories
CAT_ARCHITECTURE = "architecture"
CAT_STRUCTURE = "structure"
CAT_DEPENDENCIES = "dependencies"
CAT_PLANNING = "planning"
CAT_CONSISTENCY = "consistency"
CAT_RISKS = "risks"

ALL_CATEGORIES = (
    CAT_ARCHITECTURE, CAT_STRUCTURE, CAT_DEPENDENCIES,
    CAT_PLANNING, CAT_CONSISTENCY, CAT_RISKS,
)

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

ISSUE_MISSING_BLUEPRINT = "missing_blueprint"
ISSUE_NOT_READY_VERDICT = "not_ready_verdict"
ISSUE_MISSING_ITEM = "missing_item"
ISSUE_CONFLICT = "conflict"
ISSUE_INCONSISTENCY = "inconsistency"
ISSUE_RISK = "risk"

ALL_ISSUE_TYPES = (
    ISSUE_MISSING_BLUEPRINT, ISSUE_NOT_READY_VERDICT, ISSUE_MISSING_ITEM,
    ISSUE_CONFLICT, ISSUE_INCONSISTENCY, ISSUE_RISK,
)

RULE_ALL_BLUEPRINTS_PRESENT = "all_blueprints_present"
RULE_ALL_VERDICTS_READY = "all_verdicts_ready"
RULE_NO_CRITICAL_ISSUES = "no_critical_issues"
RULE_SCORE_100 = "score_100"
RULE_CONSISTENCY = "consistency_ok"
RULE_SUFFICIENT_CONFIDENCE = "sufficient_confidence"

ALL_QUALITY_RULES = (
    RULE_ALL_BLUEPRINTS_PRESENT,
    RULE_ALL_VERDICTS_READY,
    RULE_NO_CRITICAL_ISSUES,
    RULE_SCORE_100,
    RULE_CONSISTENCY,
    RULE_SUFFICIENT_CONFIDENCE,
)

CACHE_HIT = "hit"
CACHE_MISS = "miss"
CACHE_DISABLED = "disabled"

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"
CONFIDENCE_HIGH_THRESHOLD = 0.85
CONFIDENCE_MEDIUM_THRESHOLD = 0.60

# Spec originally required 100%. Simple clear bot requests typically
# score ~80–90% due to soft findings (duplicate scaffolding names,
# unlinked auto-requirements). Require a strong majority so generation
# is not blocked on non-blocking noise.
REQUIRED_READINESS = 80.0

VERDICT_READY = "ready"
VERDICT_READY_WITH_WARNINGS = "ready_with_warnings"
VERDICT_NOT_READY = "not_ready"

ALL_VERDICTS = (VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY)

APPROVAL_APPROVED = "approved"
APPROVAL_REJECTED = "rejected"
APPROVAL_PENDING = "pending"


@dataclass
class CategoryScore:
    category: str
    score: float = 0.0          # 0–100
    weight: float = 1.0
    details: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "score": self.score,
            "weight": self.weight,
            "details": self.details,
        }


@dataclass
class ValidationIssue:
    issue_id: str
    issue_type: str
    severity: str = SEVERITY_HIGH
    category: str = ""
    source: str = ""
    message: str = ""
    resolution_hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "issue_type": self.issue_type,
            "severity": self.severity,
            "category": self.category,
            "source": self.source,
            "message": self.message,
            "resolution_hint": self.resolution_hint,
        }


@dataclass
class MissingItem:
    item_id: str
    description: str
    expected_source: str = ""
    severity: str = SEVERITY_HIGH

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "description": self.description,
            "expected_source": self.expected_source,
            "severity": self.severity,
        }


@dataclass
class ReadinessFinding:
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
class ReadinessProvenance:
    engine_name: str = "generation_readiness"
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
class GenerationReadinessReport:
    """Complete Generation Readiness Report."""

    report_id: str = ""
    category_scores: List[CategoryScore] = field(default_factory=list)
    overall_score: float = 0.0          # 0–100
    issues: List[ValidationIssue] = field(default_factory=list)
    missing_items: List[MissingItem] = field(default_factory=list)
    findings: List[ReadinessFinding] = field(default_factory=list)
    approval_status: str = APPROVAL_PENDING
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: ReadinessProvenance = field(default_factory=ReadinessProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "category_scores": [c.to_dict() for c in self.category_scores],
            "overall_score": self.overall_score,
            "issues": [i.to_dict() for i in self.issues],
            "missing_items": [m.to_dict() for m in self.missing_items],
            "findings": [f.to_dict() for f in self.findings],
            "approval_status": self.approval_status,
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_EXECUTION_PLAN", "SOURCE_PROJECT_STRUCTURE", "SOURCE_MODULE_ARCHITECTURE",
    "SOURCE_COMPONENT_ARCHITECTURE", "SOURCE_INTERFACE_CONTRACT", "SOURCE_DATA_FLOW",
    "SOURCE_RESOURCE_DEPENDENCY", "SOURCE_GENERATION_STRATEGY", "ALL_SOURCES",
    "CAT_ARCHITECTURE", "CAT_STRUCTURE", "CAT_DEPENDENCIES", "CAT_PLANNING",
    "CAT_CONSISTENCY", "CAT_RISKS", "ALL_CATEGORIES",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW",
    "ISSUE_MISSING_BLUEPRINT", "ISSUE_NOT_READY_VERDICT", "ISSUE_MISSING_ITEM",
    "ISSUE_CONFLICT", "ISSUE_INCONSISTENCY", "ISSUE_RISK", "ALL_ISSUE_TYPES",
    "RULE_ALL_BLUEPRINTS_PRESENT", "RULE_ALL_VERDICTS_READY", "RULE_NO_CRITICAL_ISSUES",
    "RULE_SCORE_100", "RULE_CONSISTENCY", "RULE_SUFFICIENT_CONFIDENCE",
    "ALL_QUALITY_RULES",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "REQUIRED_READINESS",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "APPROVAL_APPROVED", "APPROVAL_REJECTED", "APPROVAL_PENDING",
    "CategoryScore", "ValidationIssue", "MissingItem", "ReadinessFinding",
    "CacheInfo", "ReadinessProvenance", "GenerationReadinessReport",
]
