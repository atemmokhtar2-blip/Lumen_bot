"""
Environment Configuration Report (Specification 051 — ULTRA CRITICAL).

Builds and validates Dev/Test/Staging/Production environments.
Secrets never stored in project; loaded from environment only.
Consistent behaviour across all environments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


SOURCE_DEPENDENCY = "dependency_management_report"
SOURCE_WORKSPACE = "workspace_management_report"
SOURCE_FILE_SYSTEM = "file_system_report"
SOURCE_PROJECT_CONTEXT = "project_context_report"
SOURCE_USER_REQUEST = "user_request"

ALL_SOURCES = (
    SOURCE_DEPENDENCY,
    SOURCE_WORKSPACE,
    SOURCE_FILE_SYSTEM,
    SOURCE_PROJECT_CONTEXT,
    SOURCE_USER_REQUEST,
)

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"
SEVERITY_INFO = "info"

# Environments
ENV_DEVELOPMENT = "development"
ENV_TESTING = "testing"
ENV_STAGING = "staging"
ENV_PRODUCTION = "production"

ALL_ENVIRONMENTS = (ENV_DEVELOPMENT, ENV_TESTING, ENV_STAGING, ENV_PRODUCTION)

# Config kinds
CFG_ENV_FILE = "env_file"
CFG_CONFIG_FILE = "config_file"
CFG_SECRET = "secret"
CFG_TOKEN = "token"
CFG_API_KEY = "api_key"

RULE_NO_SECRETS_IN_REPO = "no_secrets_in_repo"
RULE_NO_MISSING_VARS = "no_missing_variables"
RULE_NO_UNSAFE_VALUES = "no_unsafe_values"
RULE_CONSISTENCY_OK = "consistency_ok"
RULE_HEALTH_OK = "health_ok"
RULE_SELF_VERIFICATION = "self_verification_passed"
RULE_QUALITY_PASS = "quality_pass"

ALL_QUALITY_RULES = (
    RULE_NO_SECRETS_IN_REPO,
    RULE_NO_MISSING_VARS,
    RULE_NO_UNSAFE_VALUES,
    RULE_CONSISTENCY_OK,
    RULE_HEALTH_OK,
    RULE_SELF_VERIFICATION,
    RULE_QUALITY_PASS,
)

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

STATUS_OK = "ok"
STATUS_MISSING = "missing"
STATUS_UNSAFE = "unsafe"
STATUS_INCONSISTENT = "inconsistent"
STATUS_FAILED = "failed"


@dataclass
class EnvVariable:
    name: str
    value_present: bool = False
    is_secret: bool = False
    environment: str = ENV_DEVELOPMENT
    source: str = "environment"  # environment | .env template | config
    required: bool = True
    safe: bool = True
    masked_preview: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value_present": self.value_present,
            "is_secret": self.is_secret,
            "environment": self.environment,
            "source": self.source,
            "required": self.required,
            "safe": self.safe,
            "masked_preview": self.masked_preview if self.is_secret else self.masked_preview,
        }


@dataclass
class EnvironmentProfile:
    name: str
    active: bool = False
    variables: List[str] = field(default_factory=list)
    complete: bool = False
    consistent: bool = True
    health_ok: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "active": self.active,
            "variables": list(self.variables),
            "complete": self.complete,
            "consistent": self.consistent,
            "health_ok": self.health_ok,
        }


@dataclass
class HealthCheck:
    check_id: str
    target: str  # database|api|storage|cache|queue
    status: str = STATUS_OK
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "target": self.target,
            "status": self.status,
            "message": self.message,
        }


@dataclass
class ConfigBackup:
    backup_id: str
    environment: str
    created_at: str = ""
    item_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "backup_id": self.backup_id,
            "environment": self.environment,
            "created_at": self.created_at,
            "item_count": self.item_count,
        }


@dataclass
class EnvScore:
    security: float = 0.0
    completeness: float = 0.0
    consistency: float = 0.0
    reliability: float = 0.0
    overall: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "security": self.security,
            "completeness": self.completeness,
            "consistency": self.consistency,
            "reliability": self.reliability,
            "overall": self.overall,
        }


@dataclass
class EnvFinding:
    severity: str
    code: str
    message: str
    affected: str = ""
    resolution_hint: str = ""
    category: str = "environment"

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
class EnvProvenance:
    engine_name: str = "environment_config"
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
class EnvironmentConfigReport:
    report_id: str = ""
    profiles: List[EnvironmentProfile] = field(default_factory=list)
    variables: List[EnvVariable] = field(default_factory=list)
    health_checks: List[HealthCheck] = field(default_factory=list)
    backups: List[ConfigBackup] = field(default_factory=list)
    score: EnvScore = field(default_factory=EnvScore)
    findings: List[EnvFinding] = field(default_factory=list)
    detected_environment: str = ENV_DEVELOPMENT
    secrets_isolated: bool = True
    missing_count: int = 0
    unsafe_count: int = 0
    self_verification_passed: bool = False
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: EnvProvenance = field(default_factory=EnvProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "profiles": [p.to_dict() for p in self.profiles],
            "variables": [v.to_dict() for v in self.variables],
            "health_checks": [h.to_dict() for h in self.health_checks],
            "backups": [b.to_dict() for b in self.backups],
            "score": self.score.to_dict(),
            "findings": [f.to_dict() for f in self.findings],
            "detected_environment": self.detected_environment,
            "secrets_isolated": self.secrets_isolated,
            "missing_count": self.missing_count,
            "unsafe_count": self.unsafe_count,
            "self_verification_passed": self.self_verification_passed,
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_DEPENDENCY", "SOURCE_WORKSPACE", "SOURCE_FILE_SYSTEM",
    "SOURCE_PROJECT_CONTEXT", "SOURCE_USER_REQUEST", "ALL_SOURCES",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW", "SEVERITY_INFO",
    "ENV_DEVELOPMENT", "ENV_TESTING", "ENV_STAGING", "ENV_PRODUCTION", "ALL_ENVIRONMENTS",
    "CFG_ENV_FILE", "CFG_CONFIG_FILE", "CFG_SECRET", "CFG_TOKEN", "CFG_API_KEY",
    "RULE_NO_SECRETS_IN_REPO", "RULE_NO_MISSING_VARS", "RULE_NO_UNSAFE_VALUES",
    "RULE_CONSISTENCY_OK", "RULE_HEALTH_OK", "RULE_SELF_VERIFICATION", "RULE_QUALITY_PASS",
    "ALL_QUALITY_RULES",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "STATUS_OK", "STATUS_MISSING", "STATUS_UNSAFE", "STATUS_INCONSISTENT", "STATUS_FAILED",
    "EnvVariable", "EnvironmentProfile", "HealthCheck", "ConfigBackup", "EnvScore",
    "EnvFinding", "CacheInfo", "EnvProvenance", "EnvironmentConfigReport",
]
