"""
Integration Verification Report (Specification 042 — ULTRA CRITICAL).

Verifies that all project parts work together as one system.
Any integration failure blocks delivery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


SOURCE_SELF_HEALING = "self_healing_report"
SOURCE_RUNTIME = "runtime_simulation_report"
SOURCE_ARCHITECTURE = "architecture_compliance_report"
SOURCE_STATIC = "static_analysis_report"
SOURCE_SECURITY = "security_review_report"
SOURCE_PROJECT_CONTEXT = "project_context_report"

ALL_SOURCES = (
    SOURCE_SELF_HEALING,
    SOURCE_RUNTIME,
    SOURCE_ARCHITECTURE,
    SOURCE_STATIC,
    SOURCE_SECURITY,
    SOURCE_PROJECT_CONTEXT,
)

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"
SEVERITY_INFO = "info"

# Integration check types
CHK_MODULE = "module_integration"
CHK_PACKAGE = "package_integration"
CHK_COMPONENT = "component_integration"
CHK_SERVICE = "service_integration"
CHK_INTERFACE = "interface_implementation"
CHK_DI = "dependency_injection"
CHK_REGISTRATION = "service_registration"
CHK_LIFECYCLE = "lifecycle"
CHK_CONFIG = "configuration"
CHK_ENV = "environment"
CHK_SECRETS = "secrets"
CHK_DB_CONN = "database_connection"
CHK_DB_REPO = "database_repository"
CHK_DB_TX = "database_transaction"
CHK_TG_STARTUP = "telegram_startup"
CHK_TG_COMMANDS = "telegram_commands"
CHK_TG_HANDLERS = "telegram_handlers"
CHK_TG_MIDDLEWARE = "telegram_middleware"
CHK_TG_CALLBACKS = "telegram_callbacks"
CHK_TG_INLINE = "telegram_inline"
CHK_TG_TRANSPORT = "telegram_webhook_polling"
CHK_HTTP = "http_client"
CHK_CACHE = "cache"
CHK_QUEUE = "queue"
CHK_STORAGE = "storage"
CHK_DATA_FLOW = "data_flow"
CHK_FAILURE_RESPONSE = "failure_response"

ALL_CHECK_TYPES = (
    CHK_MODULE, CHK_PACKAGE, CHK_COMPONENT, CHK_SERVICE, CHK_INTERFACE,
    CHK_DI, CHK_REGISTRATION, CHK_LIFECYCLE, CHK_CONFIG, CHK_ENV, CHK_SECRETS,
    CHK_DB_CONN, CHK_DB_REPO, CHK_DB_TX,
    CHK_TG_STARTUP, CHK_TG_COMMANDS, CHK_TG_HANDLERS, CHK_TG_MIDDLEWARE,
    CHK_TG_CALLBACKS, CHK_TG_INLINE, CHK_TG_TRANSPORT,
    CHK_HTTP, CHK_CACHE, CHK_QUEUE, CHK_STORAGE, CHK_DATA_FLOW, CHK_FAILURE_RESPONSE,
)

RULE_NO_INTEGRATION_FAILURE = "no_integration_failure"
RULE_INTERFACES_OK = "interfaces_implemented"
RULE_DEPENDENCIES_OK = "dependencies_resolved"
RULE_TELEGRAM_OK = "telegram_integrated"
RULE_DATA_FLOW_OK = "data_flow_intact"
RULE_SELF_VERIFICATION = "self_verification_passed"
RULE_QUALITY_PASS = "quality_pass"
RULE_SUFFICIENT_CONFIDENCE = "sufficient_confidence"

ALL_QUALITY_RULES = (
    RULE_NO_INTEGRATION_FAILURE,
    RULE_INTERFACES_OK,
    RULE_DEPENDENCIES_OK,
    RULE_TELEGRAM_OK,
    RULE_DATA_FLOW_OK,
    RULE_SELF_VERIFICATION,
    RULE_QUALITY_PASS,
    RULE_SUFFICIENT_CONFIDENCE,
)

MIN_INTEGRATION_SCORE = 75.0

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

STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"
STATUS_WARNING = "warning"


@dataclass
class IntegrationCheck:
    check_id: str
    check_type: str
    status: str = STATUS_PASSED
    severity: str = SEVERITY_INFO
    message: str = ""
    target: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "check_type": self.check_type,
            "status": self.status,
            "severity": self.severity,
            "message": self.message,
            "target": self.target,
            "details": dict(self.details),
        }


@dataclass
class CompatibilityItem:
    item_id: str
    left: str
    right: str
    compatible: bool = True
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "left": self.left,
            "right": self.right,
            "compatible": self.compatible,
            "message": self.message,
        }


@dataclass
class DependencyLink:
    from_unit: str
    to_unit: str
    resolved: bool = True
    kind: str = "import"
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_unit": self.from_unit,
            "to_unit": self.to_unit,
            "resolved": self.resolved,
            "kind": self.kind,
            "message": self.message,
        }


@dataclass
class IntegrationScore:
    integration_quality: float = 0.0
    compatibility: float = 0.0
    reliability: float = 0.0
    consistency: float = 0.0
    overall: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "integration_quality": self.integration_quality,
            "compatibility": self.compatibility,
            "reliability": self.reliability,
            "consistency": self.consistency,
            "overall": self.overall,
        }


@dataclass
class IntegrationFinding:
    severity: str
    code: str
    message: str
    affected: str = ""
    resolution_hint: str = ""
    category: str = "integration"

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
class IntegrationProvenance:
    engine_name: str = "integration_verification"
    engine_version: str = "1.0.0"
    sources_used: List[str] = field(default_factory=list)
    sources_missing: List[str] = field(default_factory=list)
    generated_at: str = ""
    confidence: float = 0.0
    confidence_level: str = CONFIDENCE_LOW
    self_verification_passed: bool = False
    runs_completed: int = 0

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
            "runs_completed": self.runs_completed,
        }


@dataclass
class IntegrationVerificationReport:
    report_id: str = ""
    checks: List[IntegrationCheck] = field(default_factory=list)
    compatibility: List[CompatibilityItem] = field(default_factory=list)
    dependencies: List[DependencyLink] = field(default_factory=list)
    score: IntegrationScore = field(default_factory=IntegrationScore)
    findings: List[IntegrationFinding] = field(default_factory=list)
    check_count: int = 0
    failed_count: int = 0
    warning_count: int = 0
    self_verification_passed: bool = False
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: IntegrationProvenance = field(default_factory=IntegrationProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "checks": [c.to_dict() for c in self.checks],
            "compatibility": [c.to_dict() for c in self.compatibility],
            "dependencies": [d.to_dict() for d in self.dependencies],
            "score": self.score.to_dict(),
            "findings": [f.to_dict() for f in self.findings],
            "check_count": self.check_count,
            "failed_count": self.failed_count,
            "warning_count": self.warning_count,
            "self_verification_passed": self.self_verification_passed,
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_SELF_HEALING", "SOURCE_RUNTIME", "SOURCE_ARCHITECTURE",
    "SOURCE_STATIC", "SOURCE_SECURITY", "SOURCE_PROJECT_CONTEXT", "ALL_SOURCES",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW", "SEVERITY_INFO",
    "CHK_MODULE", "CHK_PACKAGE", "CHK_COMPONENT", "CHK_SERVICE", "CHK_INTERFACE",
    "CHK_DI", "CHK_REGISTRATION", "CHK_LIFECYCLE", "CHK_CONFIG", "CHK_ENV", "CHK_SECRETS",
    "CHK_DB_CONN", "CHK_DB_REPO", "CHK_DB_TX",
    "CHK_TG_STARTUP", "CHK_TG_COMMANDS", "CHK_TG_HANDLERS", "CHK_TG_MIDDLEWARE",
    "CHK_TG_CALLBACKS", "CHK_TG_INLINE", "CHK_TG_TRANSPORT",
    "CHK_HTTP", "CHK_CACHE", "CHK_QUEUE", "CHK_STORAGE", "CHK_DATA_FLOW", "CHK_FAILURE_RESPONSE",
    "ALL_CHECK_TYPES",
    "RULE_NO_INTEGRATION_FAILURE", "RULE_INTERFACES_OK", "RULE_DEPENDENCIES_OK",
    "RULE_TELEGRAM_OK", "RULE_DATA_FLOW_OK", "RULE_SELF_VERIFICATION",
    "RULE_QUALITY_PASS", "RULE_SUFFICIENT_CONFIDENCE", "ALL_QUALITY_RULES",
    "MIN_INTEGRATION_SCORE",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "STATUS_PASSED", "STATUS_FAILED", "STATUS_SKIPPED", "STATUS_WARNING",
    "IntegrationCheck", "CompatibilityItem", "DependencyLink", "IntegrationScore",
    "IntegrationFinding", "CacheInfo", "IntegrationProvenance",
    "IntegrationVerificationReport",
]
