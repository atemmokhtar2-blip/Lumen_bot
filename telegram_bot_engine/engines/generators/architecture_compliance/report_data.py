"""
Architecture Compliance Report (Specification 037 — ULTRA CRITICAL).

Validates that generated code still matches the designed architecture.
Any architecture violation blocks progression to the next engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


SOURCE_PERFORMANCE = "performance_optimization_report"
SOURCE_SECURITY = "security_review_report"
SOURCE_ARCHITECTURE_DECISION = "architecture_decision_report"
SOURCE_COMPONENT_ARCHITECTURE = "component_architecture_blueprint"
SOURCE_INTERFACE_CONTRACT = "interface_contract_blueprint"
SOURCE_MODULE_ARCHITECTURE = "module_architecture_blueprint"
SOURCE_PROJECT_CONTEXT = "project_context_report"
SOURCE_BUSINESS_LOGIC = "business_logic_report"

ALL_SOURCES = (
    SOURCE_PERFORMANCE,
    SOURCE_SECURITY,
    SOURCE_ARCHITECTURE_DECISION,
    SOURCE_COMPONENT_ARCHITECTURE,
    SOURCE_INTERFACE_CONTRACT,
    SOURCE_MODULE_ARCHITECTURE,
    SOURCE_PROJECT_CONTEXT,
    SOURCE_BUSINESS_LOGIC,
)

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

# Violation types
VIO_LAYER_BYPASS = "layer_bypass"
VIO_MISSING_MODULE = "missing_module"
VIO_MISSING_COMPONENT = "missing_component"
VIO_MISSING_INTERFACE = "missing_interface"
VIO_CONTRACT_BREAK = "contract_break"
VIO_UNEXPECTED_DEPENDENCY = "unexpected_dependency"
VIO_CIRCULAR_DEPENDENCY = "circular_dependency"
VIO_STRONG_COUPLING = "strong_coupling"
VIO_HIDDEN_DEPENDENCY = "hidden_dependency"
VIO_SRP = "srp_violation"
VIO_OCP = "ocp_violation"
VIO_LSP = "lsp_violation"
VIO_ISP = "isp_violation"
VIO_DIP = "dip_violation"
VIO_RESPONSIBILITY = "responsibility_overload"
VIO_INTERFACE_MISUSE = "interface_misuse"
VIO_ARCHITECTURE_DRIFT = "architecture_drift"

ALL_VIOLATION_TYPES = (
    VIO_LAYER_BYPASS, VIO_MISSING_MODULE, VIO_MISSING_COMPONENT,
    VIO_MISSING_INTERFACE, VIO_CONTRACT_BREAK, VIO_UNEXPECTED_DEPENDENCY,
    VIO_CIRCULAR_DEPENDENCY, VIO_STRONG_COUPLING, VIO_HIDDEN_DEPENDENCY,
    VIO_SRP, VIO_OCP, VIO_LSP, VIO_ISP, VIO_DIP,
    VIO_RESPONSIBILITY, VIO_INTERFACE_MISUSE, VIO_ARCHITECTURE_DRIFT,
)

RULE_NO_ARCHITECTURE_VIOLATION = "no_architecture_violation"
RULE_SOLID_COMPLIANT = "solid_compliant"
RULE_LAYERS_RESPECTED = "layers_respected"
RULE_DEPENDENCIES_VALID = "dependencies_valid"
RULE_INTERFACES_HONOURED = "interfaces_honoured"
RULE_SELF_REVIEW_PASSED = "self_review_passed"
RULE_QUALITY_PASS = "quality_pass"
RULE_SUFFICIENT_CONFIDENCE = "sufficient_confidence"

ALL_QUALITY_RULES = (
    RULE_NO_ARCHITECTURE_VIOLATION,
    RULE_SOLID_COMPLIANT,
    RULE_LAYERS_RESPECTED,
    RULE_DEPENDENCIES_VALID,
    RULE_INTERFACES_HONOURED,
    RULE_SELF_REVIEW_PASSED,
    RULE_QUALITY_PASS,
    RULE_SUFFICIENT_CONFIDENCE,
)

MIN_COMPLIANCE_SCORE = 80.0

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
STATUS_RESOLVED = "resolved"
STATUS_ACCEPTED = "accepted"
STATUS_FALSE_POSITIVE = "false_positive"


@dataclass
class ArchitectureViolation:
    violation_id: str
    violation_type: str
    severity: str = SEVERITY_HIGH
    message: str = ""
    location: str = ""
    expected: str = ""
    actual: str = ""
    unit_id: str = ""
    status: str = STATUS_OPEN
    resolution_hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "violation_id": self.violation_id,
            "violation_type": self.violation_type,
            "severity": self.severity,
            "message": self.message,
            "location": self.location,
            "expected": self.expected,
            "actual": self.actual,
            "unit_id": self.unit_id,
            "status": self.status,
            "resolution_hint": self.resolution_hint,
        }


@dataclass
class RefactoringSuggestion:
    suggestion_id: str
    target: str = ""
    violation_ids: List[str] = field(default_factory=list)
    description: str = ""
    steps: List[str] = field(default_factory=list)
    priority: str = SEVERITY_MEDIUM

    def to_dict(self) -> Dict[str, Any]:
        return {
            "suggestion_id": self.suggestion_id,
            "target": self.target,
            "violation_ids": list(self.violation_ids),
            "description": self.description,
            "steps": list(self.steps),
            "priority": self.priority,
        }


@dataclass
class ComplianceUnit:
    unit_id: str
    name: str = ""
    unit_kind: str = "class"  # class | module | interface | component
    compliant: bool = True
    violation_count: int = 0
    solid_score: float = 100.0
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "name": self.name,
            "unit_kind": self.unit_kind,
            "compliant": self.compliant,
            "violation_count": self.violation_count,
            "solid_score": self.solid_score,
            "notes": self.notes,
        }


@dataclass
class ComplianceFinding:
    severity: str
    code: str
    message: str
    affected: str = ""
    resolution_hint: str = ""
    category: str = "architecture"

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
class ComplianceProvenance:
    engine_name: str = "architecture_compliance"
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
class ArchitectureComplianceReport:
    report_id: str = ""
    units: List[ComplianceUnit] = field(default_factory=list)
    violations: List[ArchitectureViolation] = field(default_factory=list)
    refactorings: List[RefactoringSuggestion] = field(default_factory=list)
    findings: List[ComplianceFinding] = field(default_factory=list)
    unit_count: int = 0
    violation_count: int = 0
    critical_violation_count: int = 0
    open_violation_count: int = 0
    compliance_score: float = 0.0
    solid_score: float = 0.0
    self_review_passed: bool = False
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: ComplianceProvenance = field(default_factory=ComplianceProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "units": [u.to_dict() for u in self.units],
            "violations": [v.to_dict() for v in self.violations],
            "refactorings": [r.to_dict() for r in self.refactorings],
            "findings": [f.to_dict() for f in self.findings],
            "unit_count": self.unit_count,
            "violation_count": self.violation_count,
            "critical_violation_count": self.critical_violation_count,
            "open_violation_count": self.open_violation_count,
            "compliance_score": self.compliance_score,
            "solid_score": self.solid_score,
            "self_review_passed": self.self_review_passed,
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_PERFORMANCE", "SOURCE_SECURITY", "SOURCE_ARCHITECTURE_DECISION",
    "SOURCE_COMPONENT_ARCHITECTURE", "SOURCE_INTERFACE_CONTRACT",
    "SOURCE_MODULE_ARCHITECTURE", "SOURCE_PROJECT_CONTEXT", "SOURCE_BUSINESS_LOGIC",
    "ALL_SOURCES",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW",
    "VIO_LAYER_BYPASS", "VIO_MISSING_MODULE", "VIO_MISSING_COMPONENT",
    "VIO_MISSING_INTERFACE", "VIO_CONTRACT_BREAK", "VIO_UNEXPECTED_DEPENDENCY",
    "VIO_CIRCULAR_DEPENDENCY", "VIO_STRONG_COUPLING", "VIO_HIDDEN_DEPENDENCY",
    "VIO_SRP", "VIO_OCP", "VIO_LSP", "VIO_ISP", "VIO_DIP",
    "VIO_RESPONSIBILITY", "VIO_INTERFACE_MISUSE", "VIO_ARCHITECTURE_DRIFT",
    "ALL_VIOLATION_TYPES",
    "RULE_NO_ARCHITECTURE_VIOLATION", "RULE_SOLID_COMPLIANT", "RULE_LAYERS_RESPECTED",
    "RULE_DEPENDENCIES_VALID", "RULE_INTERFACES_HONOURED", "RULE_SELF_REVIEW_PASSED",
    "RULE_QUALITY_PASS", "RULE_SUFFICIENT_CONFIDENCE",
    "ALL_QUALITY_RULES", "MIN_COMPLIANCE_SCORE",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "STATUS_OPEN", "STATUS_RESOLVED", "STATUS_ACCEPTED", "STATUS_FALSE_POSITIVE",
    "ArchitectureViolation", "RefactoringSuggestion", "ComplianceUnit",
    "ComplianceFinding", "CacheInfo", "ComplianceProvenance",
    "ArchitectureComplianceReport",
]
