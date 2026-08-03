"""
Self-Healing Report (Specification 041 — ULTRA CRITICAL).

Intelligent Self-Healing Engine artefacts.
Automatically repairs issues found by upstream engines, re-validates,
and blocks progression until tests pass without breaking architecture.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


SOURCE_RUNTIME = "runtime_simulation_report"
SOURCE_STATIC = "static_analysis_report"
SOURCE_ARCHITECTURE = "architecture_compliance_report"
SOURCE_SECURITY = "security_review_report"
SOURCE_PERFORMANCE = "performance_optimization_report"
SOURCE_REFACTORING = "code_refactoring_report"

ALL_SOURCES = (
    SOURCE_RUNTIME,
    SOURCE_STATIC,
    SOURCE_ARCHITECTURE,
    SOURCE_SECURITY,
    SOURCE_PERFORMANCE,
    SOURCE_REFACTORING,
)

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"
SEVERITY_INFO = "info"

# Issue categories
CAT_SYNTAX = "syntax"
CAT_ARCHITECTURE = "architecture"
CAT_DEPENDENCY = "dependency"
CAT_PERFORMANCE = "performance"
CAT_SECURITY = "security"
CAT_RUNTIME = "runtime"
CAT_LOGIC = "logic"
CAT_CONFIGURATION = "configuration"
CAT_INTEGRATION = "integration"

ALL_CATEGORIES = (
    CAT_SYNTAX, CAT_ARCHITECTURE, CAT_DEPENDENCY, CAT_PERFORMANCE,
    CAT_SECURITY, CAT_RUNTIME, CAT_LOGIC, CAT_CONFIGURATION, CAT_INTEGRATION,
)

# Repair action types
REP_SYNTAX_FIX = "syntax_fix"
REP_IMPORT_FIX = "import_fix"
REP_LAYER_FIX = "layer_fix"
REP_SECRET_FIX = "secret_fix"
REP_SAFE_API = "safe_api_fix"
REP_TIMEOUT_FIX = "timeout_fix"
REP_EXTRACT_METHOD = "extract_method_hint"
REP_EXTRACT_CLASS = "extract_class_hint"
REP_DI_FIX = "dependency_injection_fix"
REP_CONFIG_FIX = "configuration_fix"
REP_RETRY_POLICY = "retry_policy"
REP_GUARD_CLAUSE = "guard_clause"
REP_GENERIC = "generic_repair"

ALL_REPAIR_TYPES = (
    REP_SYNTAX_FIX, REP_IMPORT_FIX, REP_LAYER_FIX, REP_SECRET_FIX,
    REP_SAFE_API, REP_TIMEOUT_FIX, REP_EXTRACT_METHOD, REP_EXTRACT_CLASS,
    REP_DI_FIX, REP_CONFIG_FIX, REP_RETRY_POLICY, REP_GUARD_CLAUSE, REP_GENERIC,
)

RULE_NO_ARCH_BREAK = "no_architecture_break"
RULE_NO_LOGIC_BREAK = "no_business_logic_break"
RULE_NO_PERF_REGRESSION = "no_performance_regression"
RULE_NO_SEC_REGRESSION = "no_security_regression"
RULE_ALL_TESTS_PASS = "all_validation_tests_pass"
RULE_CONFIDENCE_OK = "repair_confidence_sufficient"
RULE_LIMITS_RESPECTED = "repair_limits_respected"
RULE_SELF_OK = "self_verification_passed"

ALL_QUALITY_RULES = (
    RULE_NO_ARCH_BREAK,
    RULE_NO_LOGIC_BREAK,
    RULE_NO_PERF_REGRESSION,
    RULE_NO_SEC_REGRESSION,
    RULE_ALL_TESTS_PASS,
    RULE_CONFIDENCE_OK,
    RULE_LIMITS_RESPECTED,
    RULE_SELF_OK,
)

MAX_ATTEMPTS_PER_ISSUE = 3
MIN_REPAIR_CONFIDENCE = 0.60
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
STATUS_HEALED = "healed"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"
STATUS_ACCEPTED = "accepted"


@dataclass
class IssueRecord:
    issue_id: str
    category: str
    severity: str = SEVERITY_HIGH
    source_engine: str = ""
    message: str = ""
    location: str = ""
    root_cause: str = ""
    status: str = STATUS_OPEN
    attempts: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "category": self.category,
            "severity": self.severity,
            "source_engine": self.source_engine,
            "message": self.message,
            "location": self.location,
            "root_cause": self.root_cause,
            "status": self.status,
            "attempts": self.attempts,
        }


@dataclass
class RepairPlan:
    plan_id: str
    issue_id: str
    repair_type: str
    description: str = ""
    what_changes: str = ""
    why: str = ""
    impact: str = ""
    confidence: float = 0.0
    architecture_safe: bool = True
    logic_safe: bool = True
    security_safe: bool = True
    performance_safe: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "issue_id": self.issue_id,
            "repair_type": self.repair_type,
            "description": self.description,
            "what_changes": self.what_changes,
            "why": self.why,
            "impact": self.impact,
            "confidence": self.confidence,
            "architecture_safe": self.architecture_safe,
            "logic_safe": self.logic_safe,
            "security_safe": self.security_safe,
            "performance_safe": self.performance_safe,
        }


@dataclass
class RepairAttempt:
    attempt_id: str
    issue_id: str
    plan_id: str
    attempt_number: int = 1
    success: bool = False
    message: str = ""
    validation_passed: bool = False
    regression_detected: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attempt_id": self.attempt_id,
            "issue_id": self.issue_id,
            "plan_id": self.plan_id,
            "attempt_number": self.attempt_number,
            "success": self.success,
            "message": self.message,
            "validation_passed": self.validation_passed,
            "regression_detected": self.regression_detected,
        }


@dataclass
class ValidationCycleResult:
    cycle_id: str
    static_ok: bool = True
    security_ok: bool = True
    performance_ok: bool = True
    architecture_ok: bool = True
    runtime_ok: bool = True
    overall_ok: bool = True
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "static_ok": self.static_ok,
            "security_ok": self.security_ok,
            "performance_ok": self.performance_ok,
            "architecture_ok": self.architecture_ok,
            "runtime_ok": self.runtime_ok,
            "overall_ok": self.overall_ok,
            "notes": self.notes,
        }


@dataclass
class HealingFinding:
    severity: str
    code: str
    message: str
    affected: str = ""
    resolution_hint: str = ""
    category: str = "healing"

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
class HealingProvenance:
    engine_name: str = "self_healing"
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
class SelfHealingReport:
    report_id: str = ""
    issues: List[IssueRecord] = field(default_factory=list)
    plans: List[RepairPlan] = field(default_factory=list)
    attempts: List[RepairAttempt] = field(default_factory=list)
    validation_cycles: List[ValidationCycleResult] = field(default_factory=list)
    findings: List[HealingFinding] = field(default_factory=list)
    issue_count: int = 0
    healed_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    average_confidence: float = 0.0
    all_validations_passed: bool = False
    self_verification_passed: bool = False
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: HealingProvenance = field(default_factory=HealingProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "issues": [i.to_dict() for i in self.issues],
            "plans": [p.to_dict() for p in self.plans],
            "attempts": [a.to_dict() for a in self.attempts],
            "validation_cycles": [v.to_dict() for v in self.validation_cycles],
            "findings": [f.to_dict() for f in self.findings],
            "issue_count": self.issue_count,
            "healed_count": self.healed_count,
            "failed_count": self.failed_count,
            "skipped_count": self.skipped_count,
            "average_confidence": self.average_confidence,
            "all_validations_passed": self.all_validations_passed,
            "self_verification_passed": self.self_verification_passed,
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_RUNTIME", "SOURCE_STATIC", "SOURCE_ARCHITECTURE",
    "SOURCE_SECURITY", "SOURCE_PERFORMANCE", "SOURCE_REFACTORING", "ALL_SOURCES",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW", "SEVERITY_INFO",
    "CAT_SYNTAX", "CAT_ARCHITECTURE", "CAT_DEPENDENCY", "CAT_PERFORMANCE",
    "CAT_SECURITY", "CAT_RUNTIME", "CAT_LOGIC", "CAT_CONFIGURATION", "CAT_INTEGRATION",
    "ALL_CATEGORIES",
    "REP_SYNTAX_FIX", "REP_IMPORT_FIX", "REP_LAYER_FIX", "REP_SECRET_FIX",
    "REP_SAFE_API", "REP_TIMEOUT_FIX", "REP_EXTRACT_METHOD", "REP_EXTRACT_CLASS",
    "REP_DI_FIX", "REP_CONFIG_FIX", "REP_RETRY_POLICY", "REP_GUARD_CLAUSE", "REP_GENERIC",
    "ALL_REPAIR_TYPES",
    "RULE_NO_ARCH_BREAK", "RULE_NO_LOGIC_BREAK", "RULE_NO_PERF_REGRESSION",
    "RULE_NO_SEC_REGRESSION", "RULE_ALL_TESTS_PASS", "RULE_CONFIDENCE_OK",
    "RULE_LIMITS_RESPECTED", "RULE_SELF_OK", "ALL_QUALITY_RULES",
    "MAX_ATTEMPTS_PER_ISSUE", "MIN_REPAIR_CONFIDENCE", "MIN_QUALITY_SCORE",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "STATUS_OPEN", "STATUS_HEALED", "STATUS_FAILED", "STATUS_SKIPPED", "STATUS_ACCEPTED",
    "IssueRecord", "RepairPlan", "RepairAttempt", "ValidationCycleResult",
    "HealingFinding", "CacheInfo", "HealingProvenance", "SelfHealingReport",
]
