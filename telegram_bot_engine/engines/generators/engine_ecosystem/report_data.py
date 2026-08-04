"""
Engine Ecosystem & Registry Report (Specification 052 — MAXIMUM CRITICAL).

Central registry for all engines. No engine runs without registration.
Dependency graph, capability discovery, health, failure isolation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


SOURCE_ENVIRONMENT = "environment_config_report"
SOURCE_DEPENDENCY = "dependency_management_report"
SOURCE_WORKSPACE = "workspace_management_report"
SOURCE_PROJECT_CONTEXT = "project_context_report"
SOURCE_USER_REQUEST = "user_request"

ALL_SOURCES = (
    SOURCE_ENVIRONMENT,
    SOURCE_DEPENDENCY,
    SOURCE_WORKSPACE,
    SOURCE_PROJECT_CONTEXT,
    SOURCE_USER_REQUEST,
)

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"
SEVERITY_INFO = "info"

# Capabilities
CAP_GENERATE = "generate_code"
CAP_ANALYZE = "analyze"
CAP_REVIEW = "review"
CAP_OPTIMIZE = "optimize"
CAP_REPAIR = "repair"
CAP_DEPLOY = "deploy"
CAP_LEARN = "learn"
CAP_SEARCH = "search"
CAP_VALIDATE = "validate"
CAP_TEST = "test"
CAP_CONFIGURE = "configure"
CAP_MANAGE = "manage"

ALL_CAPABILITIES = (
    CAP_GENERATE, CAP_ANALYZE, CAP_REVIEW, CAP_OPTIMIZE, CAP_REPAIR,
    CAP_DEPLOY, CAP_LEARN, CAP_SEARCH, CAP_VALIDATE, CAP_TEST,
    CAP_CONFIGURE, CAP_MANAGE,
)

# Engine health status
HEALTH_HEALTHY = "healthy"
HEALTH_DEGRADED = "degraded"
HEALTH_UNAVAILABLE = "unavailable"
HEALTH_FAILED = "failed"
HEALTH_ISOLATED = "isolated"

RULE_ALL_REGISTERED = "all_engines_registered"
RULE_NO_CONFLICTS = "no_engine_conflicts"
RULE_COMPATIBLE = "compatible_with_ecosystem"
RULE_DEPENDENCIES_RESOLVED = "dependencies_resolved"
RULE_HEALTH_OK = "health_ok"
RULE_SELF_VERIFICATION = "self_verification_passed"
RULE_QUALITY_PASS = "quality_pass"

ALL_QUALITY_RULES = (
    RULE_ALL_REGISTERED,
    RULE_NO_CONFLICTS,
    RULE_COMPATIBLE,
    RULE_DEPENDENCIES_RESOLVED,
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

STATUS_REGISTERED = "registered"
STATUS_ACTIVE = "active"
STATUS_DISABLED = "disabled"
STATUS_FAILED = "failed"
STATUS_ISOLATED = "isolated"


@dataclass
class EngineManifest:
    engine_id: str
    name: str
    version: str = "1.0.0"
    author: str = "platform"
    description: str = ""
    capabilities: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    priority: int = 100
    execution_order: int = 0
    status: str = STATUS_REGISTERED
    permissions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "capabilities": list(self.capabilities),
            "dependencies": list(self.dependencies),
            "priority": self.priority,
            "execution_order": self.execution_order,
            "status": self.status,
            "permissions": list(self.permissions),
        }


@dataclass
class DependencyEdge:
    from_engine: str
    to_engine: str
    relation: str = "depends_on"  # depends_on | precedes | follows

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_engine": self.from_engine,
            "to_engine": self.to_engine,
            "relation": self.relation,
        }


@dataclass
class CompatibilityResult:
    engine_id: str
    compatible: bool = True
    conflicts: List[str] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "compatible": self.compatible,
            "conflicts": list(self.conflicts),
            "message": self.message,
        }


@dataclass
class EngineHealth:
    engine_id: str
    status: str = HEALTH_HEALTHY
    availability: float = 100.0
    response_time_ms: float = 0.0
    failure_count: int = 0
    isolated: bool = False
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "status": self.status,
            "availability": self.availability,
            "response_time_ms": self.response_time_ms,
            "failure_count": self.failure_count,
            "isolated": self.isolated,
            "message": self.message,
        }


@dataclass
class CapabilityEntry:
    capability: str
    providers: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability": self.capability,
            "providers": list(self.providers),
        }


@dataclass
class EcosystemFinding:
    severity: str
    code: str
    message: str
    affected: str = ""
    resolution_hint: str = ""
    category: str = "ecosystem"

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
class EcosystemProvenance:
    engine_name: str = "engine_ecosystem"
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
class EngineEcosystemReport:
    report_id: str = ""
    manifests: List[EngineManifest] = field(default_factory=list)
    edges: List[DependencyEdge] = field(default_factory=list)
    capabilities: List[CapabilityEntry] = field(default_factory=list)
    compatibility: List[CompatibilityResult] = field(default_factory=list)
    health: List[EngineHealth] = field(default_factory=list)
    findings: List[EcosystemFinding] = field(default_factory=list)
    engine_count: int = 0
    conflict_count: int = 0
    isolated_count: int = 0
    self_verification_passed: bool = False
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: EcosystemProvenance = field(default_factory=EcosystemProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "manifests": [m.to_dict() for m in self.manifests],
            "edges": [e.to_dict() for e in self.edges],
            "capabilities": [c.to_dict() for c in self.capabilities],
            "compatibility": [c.to_dict() for c in self.compatibility],
            "health": [h.to_dict() for h in self.health],
            "findings": [f.to_dict() for f in self.findings],
            "engine_count": self.engine_count,
            "conflict_count": self.conflict_count,
            "isolated_count": self.isolated_count,
            "self_verification_passed": self.self_verification_passed,
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_ENVIRONMENT", "SOURCE_DEPENDENCY", "SOURCE_WORKSPACE",
    "SOURCE_PROJECT_CONTEXT", "SOURCE_USER_REQUEST", "ALL_SOURCES",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW", "SEVERITY_INFO",
    "CAP_GENERATE", "CAP_ANALYZE", "CAP_REVIEW", "CAP_OPTIMIZE", "CAP_REPAIR",
    "CAP_DEPLOY", "CAP_LEARN", "CAP_SEARCH", "CAP_VALIDATE", "CAP_TEST",
    "CAP_CONFIGURE", "CAP_MANAGE", "ALL_CAPABILITIES",
    "HEALTH_HEALTHY", "HEALTH_DEGRADED", "HEALTH_UNAVAILABLE", "HEALTH_FAILED", "HEALTH_ISOLATED",
    "RULE_ALL_REGISTERED", "RULE_NO_CONFLICTS", "RULE_COMPATIBLE",
    "RULE_DEPENDENCIES_RESOLVED", "RULE_HEALTH_OK", "RULE_SELF_VERIFICATION", "RULE_QUALITY_PASS",
    "ALL_QUALITY_RULES",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "STATUS_REGISTERED", "STATUS_ACTIVE", "STATUS_DISABLED", "STATUS_FAILED", "STATUS_ISOLATED",
    "EngineManifest", "DependencyEdge", "CompatibilityResult", "EngineHealth",
    "CapabilityEntry", "EcosystemFinding", "CacheInfo", "EcosystemProvenance",
    "EngineEcosystemReport",
]
