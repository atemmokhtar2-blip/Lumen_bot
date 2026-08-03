"""
Unit Test Generation Report (Specification 043 — ULTRA CRITICAL).

Generates professional unit tests for all testable units.
No unit without tests; all tests must pass before progression.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


SOURCE_INTEGRATION = "integration_verification_report"
SOURCE_SELF_HEALING = "self_healing_report"
SOURCE_ARCHITECTURE = "architecture_compliance_report"
SOURCE_REFACTORING = "code_refactoring_report"
SOURCE_BUSINESS_LOGIC = "business_logic_report"
SOURCE_PROJECT_CONTEXT = "project_context_report"

ALL_SOURCES = (
    SOURCE_INTEGRATION,
    SOURCE_SELF_HEALING,
    SOURCE_ARCHITECTURE,
    SOURCE_REFACTORING,
    SOURCE_BUSINESS_LOGIC,
    SOURCE_PROJECT_CONTEXT,
)

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"
SEVERITY_INFO = "info"

# Test case kinds
CASE_NORMAL = "normal"
CASE_BOUNDARY = "boundary"
CASE_NULL = "null"
CASE_EMPTY = "empty"
CASE_INVALID = "invalid_input"
CASE_LARGE = "large_input"
CASE_UNEXPECTED = "unexpected_input"
CASE_EXCEPTION = "exception"
CASE_TIMEOUT = "timeout"
CASE_FAILURE = "failure"
CASE_RECOVERY = "recovery"

ALL_CASE_KINDS = (
    CASE_NORMAL, CASE_BOUNDARY, CASE_NULL, CASE_EMPTY, CASE_INVALID,
    CASE_LARGE, CASE_UNEXPECTED, CASE_EXCEPTION, CASE_TIMEOUT,
    CASE_FAILURE, CASE_RECOVERY,
)

# Unit kinds
UNIT_FUNCTION = "function"
UNIT_METHOD = "method"
UNIT_SERVICE = "service"
UNIT_REPOSITORY = "repository"
UNIT_MANAGER = "manager"
UNIT_UTILITY = "utility"
UNIT_VALIDATOR = "validator"
UNIT_STRATEGY = "strategy"
UNIT_CLASS = "class"

ALL_UNIT_KINDS = (
    UNIT_FUNCTION, UNIT_METHOD, UNIT_SERVICE, UNIT_REPOSITORY,
    UNIT_MANAGER, UNIT_UTILITY, UNIT_VALIDATOR, UNIT_STRATEGY, UNIT_CLASS,
)

RULE_NO_UNIT_WITHOUT_TEST = "no_unit_without_test"
RULE_ALL_TESTS_PASS = "all_tests_pass"
RULE_COVERAGE_OK = "coverage_sufficient"
RULE_SELF_VERIFICATION = "self_verification_passed"
RULE_QUALITY_PASS = "quality_pass"
RULE_SUFFICIENT_CONFIDENCE = "sufficient_confidence"

ALL_QUALITY_RULES = (
    RULE_NO_UNIT_WITHOUT_TEST,
    RULE_ALL_TESTS_PASS,
    RULE_COVERAGE_OK,
    RULE_SELF_VERIFICATION,
    RULE_QUALITY_PASS,
    RULE_SUFFICIENT_CONFIDENCE,
)

MIN_LINE_COVERAGE = 80.0
MIN_BRANCH_COVERAGE = 70.0
MIN_METHOD_COVERAGE = 90.0
MIN_OVERALL_COVERAGE = 80.0

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

STATUS_GENERATED = "generated"
STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"
STATUS_GAP = "gap"


@dataclass
class TestCase:
    case_id: str
    unit_id: str
    case_kind: str
    name: str = ""
    description: str = ""
    assertions: List[str] = field(default_factory=list)
    uses_mock: bool = False
    status: str = STATUS_GENERATED
    failure_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "unit_id": self.unit_id,
            "case_kind": self.case_kind,
            "name": self.name,
            "description": self.description,
            "assertions": list(self.assertions),
            "uses_mock": self.uses_mock,
            "status": self.status,
            "failure_reason": self.failure_reason,
        }


@dataclass
class GeneratedTest:
    test_id: str
    unit_id: str
    unit_kind: str
    class_name: str = ""
    method_name: str = ""
    test_code: str = ""
    cases: List[TestCase] = field(default_factory=list)
    status: str = STATUS_GENERATED
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "unit_id": self.unit_id,
            "unit_kind": self.unit_kind,
            "class_name": self.class_name,
            "method_name": self.method_name,
            "test_code": self.test_code,
            "cases": [c.to_dict() for c in self.cases],
            "status": self.status,
            "notes": self.notes,
        }


@dataclass
class CoverageScore:
    line_coverage: float = 0.0
    branch_coverage: float = 0.0
    method_coverage: float = 0.0
    class_coverage: float = 0.0
    module_coverage: float = 0.0
    overall: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "line_coverage": self.line_coverage,
            "branch_coverage": self.branch_coverage,
            "method_coverage": self.method_coverage,
            "class_coverage": self.class_coverage,
            "module_coverage": self.module_coverage,
            "overall": self.overall,
        }


@dataclass
class CoverageGap:
    gap_id: str
    unit_id: str
    unit_kind: str = ""
    message: str = ""
    filled: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gap_id": self.gap_id,
            "unit_id": self.unit_id,
            "unit_kind": self.unit_kind,
            "message": self.message,
            "filled": self.filled,
        }


@dataclass
class FailureRecord:
    failure_id: str
    test_id: str
    case_id: str = ""
    reason: str = ""
    location: str = ""
    responsible_unit: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "failure_id": self.failure_id,
            "test_id": self.test_id,
            "case_id": self.case_id,
            "reason": self.reason,
            "location": self.location,
            "responsible_unit": self.responsible_unit,
        }


@dataclass
class UnitTestFinding:
    severity: str
    code: str
    message: str
    affected: str = ""
    resolution_hint: str = ""
    category: str = "unit_test"

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
class UnitTestProvenance:
    engine_name: str = "unit_test_generation"
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
class UnitTestGenerationReport:
    report_id: str = ""
    tests: List[GeneratedTest] = field(default_factory=list)
    gaps: List[CoverageGap] = field(default_factory=list)
    failures: List[FailureRecord] = field(default_factory=list)
    coverage: CoverageScore = field(default_factory=CoverageScore)
    findings: List[UnitTestFinding] = field(default_factory=list)
    test_count: int = 0
    case_count: int = 0
    gap_count: int = 0
    failure_count: int = 0
    all_tests_passed: bool = False
    self_verification_passed: bool = False
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: UnitTestProvenance = field(default_factory=UnitTestProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "tests": [t.to_dict() for t in self.tests],
            "gaps": [g.to_dict() for g in self.gaps],
            "failures": [f.to_dict() for f in self.failures],
            "coverage": self.coverage.to_dict(),
            "findings": [f.to_dict() for f in self.findings],
            "test_count": self.test_count,
            "case_count": self.case_count,
            "gap_count": self.gap_count,
            "failure_count": self.failure_count,
            "all_tests_passed": self.all_tests_passed,
            "self_verification_passed": self.self_verification_passed,
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_INTEGRATION", "SOURCE_SELF_HEALING", "SOURCE_ARCHITECTURE",
    "SOURCE_REFACTORING", "SOURCE_BUSINESS_LOGIC", "SOURCE_PROJECT_CONTEXT",
    "ALL_SOURCES",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW", "SEVERITY_INFO",
    "CASE_NORMAL", "CASE_BOUNDARY", "CASE_NULL", "CASE_EMPTY", "CASE_INVALID",
    "CASE_LARGE", "CASE_UNEXPECTED", "CASE_EXCEPTION", "CASE_TIMEOUT",
    "CASE_FAILURE", "CASE_RECOVERY", "ALL_CASE_KINDS",
    "UNIT_FUNCTION", "UNIT_METHOD", "UNIT_SERVICE", "UNIT_REPOSITORY",
    "UNIT_MANAGER", "UNIT_UTILITY", "UNIT_VALIDATOR", "UNIT_STRATEGY", "UNIT_CLASS",
    "ALL_UNIT_KINDS",
    "RULE_NO_UNIT_WITHOUT_TEST", "RULE_ALL_TESTS_PASS", "RULE_COVERAGE_OK",
    "RULE_SELF_VERIFICATION", "RULE_QUALITY_PASS", "RULE_SUFFICIENT_CONFIDENCE",
    "ALL_QUALITY_RULES",
    "MIN_LINE_COVERAGE", "MIN_BRANCH_COVERAGE", "MIN_METHOD_COVERAGE", "MIN_OVERALL_COVERAGE",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "STATUS_GENERATED", "STATUS_PASSED", "STATUS_FAILED", "STATUS_SKIPPED", "STATUS_GAP",
    "TestCase", "GeneratedTest", "CoverageScore", "CoverageGap", "FailureRecord",
    "UnitTestFinding", "CacheInfo", "UnitTestProvenance", "UnitTestGenerationReport",
]
