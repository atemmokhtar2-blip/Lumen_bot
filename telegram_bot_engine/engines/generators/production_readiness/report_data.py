"""
Production Readiness Certification Report (Specification 045 — MAXIMUM CRITICAL).

Final gate: certifies whether the project is production-ready.
Telegram token must NOT be requested until certificate is granted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


SOURCE_E2E = "e2e_scenario_testing_report"
SOURCE_UNIT_TEST = "unit_test_generation_report"
SOURCE_INTEGRATION = "integration_verification_report"
SOURCE_SELF_HEALING = "self_healing_report"
SOURCE_RUNTIME = "runtime_simulation_report"
SOURCE_STATIC = "static_analysis_report"
SOURCE_ARCHITECTURE = "architecture_compliance_report"
SOURCE_SECURITY = "security_review_report"
SOURCE_PERFORMANCE = "performance_optimization_report"
SOURCE_REFACTORING = "code_refactoring_report"

ALL_SOURCES = (
    SOURCE_E2E, SOURCE_UNIT_TEST, SOURCE_INTEGRATION, SOURCE_SELF_HEALING,
    SOURCE_RUNTIME, SOURCE_STATIC, SOURCE_ARCHITECTURE, SOURCE_SECURITY,
    SOURCE_PERFORMANCE, SOURCE_REFACTORING,
)

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"
SEVERITY_INFO = "info"

# Score axes
AXIS_ARCHITECTURE = "architecture"
AXIS_SECURITY = "security"
AXIS_PERFORMANCE = "performance"
AXIS_CODE_QUALITY = "code_quality"
AXIS_RELIABILITY = "reliability"
AXIS_MAINTAINABILITY = "maintainability"
AXIS_SCALABILITY = "scalability"
AXIS_TESTING = "testing"
AXIS_INTEGRATION = "integration"
AXIS_OVERALL = "overall"

ALL_AXES = (
    AXIS_ARCHITECTURE, AXIS_SECURITY, AXIS_PERFORMANCE, AXIS_CODE_QUALITY,
    AXIS_RELIABILITY, AXIS_MAINTAINABILITY, AXIS_SCALABILITY, AXIS_TESTING,
    AXIS_INTEGRATION, AXIS_OVERALL,
)

# Minimum thresholds (strict)
MIN_ARCHITECTURE = 80.0
MIN_SECURITY = 85.0
MIN_PERFORMANCE = 75.0
MIN_CODE_QUALITY = 75.0
MIN_RELIABILITY = 80.0
MIN_MAINTAINABILITY = 70.0
MIN_SCALABILITY = 70.0
MIN_TESTING = 80.0
MIN_INTEGRATION = 80.0
MIN_OVERALL = 80.0

RULE_NO_CRITICAL = "no_critical_issues"
RULE_ALL_AXES_PASS = "all_axes_above_threshold"
RULE_REGRESSION_CLEAN = "no_regression"
RULE_TOKEN_GATE = "telegram_token_gate"
RULE_SELF_VERIFICATION = "self_verification_passed"
RULE_CERTIFICATE_VALID = "certificate_valid"

ALL_QUALITY_RULES = (
    RULE_NO_CRITICAL,
    RULE_ALL_AXES_PASS,
    RULE_REGRESSION_CLEAN,
    RULE_TOKEN_GATE,
    RULE_SELF_VERIFICATION,
    RULE_CERTIFICATE_VALID,
)

CACHE_HIT = "hit"
CACHE_MISS = "miss"
CACHE_DISABLED = "disabled"

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"
CONFIDENCE_HIGH_THRESHOLD = 0.85
CONFIDENCE_MEDIUM_THRESHOLD = 0.60

VERDICT_CERTIFIED = "certified"
VERDICT_REJECTED = "rejected"
VERDICT_CONDITIONAL = "conditional"

ALL_VERDICTS = (VERDICT_CERTIFIED, VERDICT_REJECTED, VERDICT_CONDITIONAL)

STATUS_PASS = "pass"
STATUS_FAIL = "fail"
STATUS_WARN = "warn"


@dataclass
class AxisScore:
    axis: str
    score: float = 0.0
    threshold: float = 0.0
    status: str = STATUS_FAIL
    responsible_engine: str = ""
    rejection_reason: str = ""
    repair_hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "axis": self.axis,
            "score": self.score,
            "threshold": self.threshold,
            "status": self.status,
            "responsible_engine": self.responsible_engine,
            "rejection_reason": self.rejection_reason,
            "repair_hint": self.repair_hint,
        }


@dataclass
class CriticalBlocker:
    blocker_id: str
    source_engine: str
    severity: str = SEVERITY_CRITICAL
    message: str = ""
    repair_hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "blocker_id": self.blocker_id,
            "source_engine": self.source_engine,
            "severity": self.severity,
            "message": self.message,
            "repair_hint": self.repair_hint,
        }


@dataclass
class Certificate:
    certificate_id: str = ""
    issued: bool = False
    issued_at: str = ""
    overall_score: float = 0.0
    token_gate_open: bool = False  # True ONLY when certified
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "certificate_id": self.certificate_id,
            "issued": self.issued,
            "issued_at": self.issued_at,
            "overall_score": self.overall_score,
            "token_gate_open": self.token_gate_open,
            "summary": self.summary,
        }


@dataclass
class CertificationFinding:
    severity: str
    code: str
    message: str
    affected: str = ""
    resolution_hint: str = ""
    category: str = "certification"

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
class CertificationProvenance:
    engine_name: str = "production_readiness"
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
class ProductionReadinessReport:
    report_id: str = ""
    axes: List[AxisScore] = field(default_factory=list)
    blockers: List[CriticalBlocker] = field(default_factory=list)
    certificate: Certificate = field(default_factory=Certificate)
    findings: List[CertificationFinding] = field(default_factory=list)
    overall_score: float = 0.0
    certified: bool = False
    token_gate_open: bool = False
    self_verification_passed: bool = False
    readiness_status: str = VERDICT_REJECTED
    verdict: str = VERDICT_REJECTED
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: CertificationProvenance = field(default_factory=CertificationProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "axes": [a.to_dict() for a in self.axes],
            "blockers": [b.to_dict() for b in self.blockers],
            "certificate": self.certificate.to_dict(),
            "findings": [f.to_dict() for f in self.findings],
            "overall_score": self.overall_score,
            "certified": self.certified,
            "token_gate_open": self.token_gate_open,
            "self_verification_passed": self.self_verification_passed,
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_E2E", "SOURCE_UNIT_TEST", "SOURCE_INTEGRATION", "SOURCE_SELF_HEALING",
    "SOURCE_RUNTIME", "SOURCE_STATIC", "SOURCE_ARCHITECTURE", "SOURCE_SECURITY",
    "SOURCE_PERFORMANCE", "SOURCE_REFACTORING", "ALL_SOURCES",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW", "SEVERITY_INFO",
    "AXIS_ARCHITECTURE", "AXIS_SECURITY", "AXIS_PERFORMANCE", "AXIS_CODE_QUALITY",
    "AXIS_RELIABILITY", "AXIS_MAINTAINABILITY", "AXIS_SCALABILITY", "AXIS_TESTING",
    "AXIS_INTEGRATION", "AXIS_OVERALL", "ALL_AXES",
    "MIN_ARCHITECTURE", "MIN_SECURITY", "MIN_PERFORMANCE", "MIN_CODE_QUALITY",
    "MIN_RELIABILITY", "MIN_MAINTAINABILITY", "MIN_SCALABILITY", "MIN_TESTING",
    "MIN_INTEGRATION", "MIN_OVERALL",
    "RULE_NO_CRITICAL", "RULE_ALL_AXES_PASS", "RULE_REGRESSION_CLEAN",
    "RULE_TOKEN_GATE", "RULE_SELF_VERIFICATION", "RULE_CERTIFICATE_VALID",
    "ALL_QUALITY_RULES",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_CERTIFIED", "VERDICT_REJECTED", "VERDICT_CONDITIONAL", "ALL_VERDICTS",
    "STATUS_PASS", "STATUS_FAIL", "STATUS_WARN",
    "AxisScore", "CriticalBlocker", "Certificate", "CertificationFinding",
    "CacheInfo", "CertificationProvenance", "ProductionReadinessReport",
]
