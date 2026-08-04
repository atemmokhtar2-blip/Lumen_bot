"""
Resource Management Report (Specification 056 — CRITICAL).

Manages CPU, RAM, storage, threads across all engines.
Allocation, monitoring, optimization, limits, leak detection, cleanup.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


SOURCE_SYNC = "synchronization_report"
SOURCE_ORCHESTRATOR = "engine_orchestrator_report"
SOURCE_ECOSYSTEM = "engine_ecosystem_report"
SOURCE_EXECUTION_CONTEXT = "execution_context_report"
SOURCE_USER_REQUEST = "user_request"

ALL_SOURCES = (
    SOURCE_SYNC,
    SOURCE_ORCHESTRATOR,
    SOURCE_ECOSYSTEM,
    SOURCE_EXECUTION_CONTEXT,
    SOURCE_USER_REQUEST,
)

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"
SEVERITY_INFO = "info"

# Resource kinds
RES_CPU = "cpu"
RES_RAM = "ram"
RES_STORAGE = "storage"
RES_THREAD = "thread"

ALL_RESOURCES = (RES_CPU, RES_RAM, RES_STORAGE, RES_THREAD)

RULE_NO_OVER_LIMIT = "no_engine_over_limit"
RULE_NO_SYSTEM_DEGRADE = "no_system_degrade_by_single_engine"
RULE_LEAKS_CLEANED = "leaks_cleaned"
RULE_SELF_VERIFICATION = "self_verification_passed"
RULE_QUALITY_PASS = "quality_pass"

ALL_QUALITY_RULES = (
    RULE_NO_OVER_LIMIT,
    RULE_NO_SYSTEM_DEGRADE,
    RULE_LEAKS_CLEANED,
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


@dataclass
class ResourceQuota:
    engine_id: str
    cpu_percent: float = 10.0
    ram_mb: float = 128.0
    storage_mb: float = 256.0
    threads: int = 2
    priority: int = 5  # 1 highest – 10 lowest

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "cpu_percent": self.cpu_percent,
            "ram_mb": self.ram_mb,
            "storage_mb": self.storage_mb,
            "threads": self.threads,
            "priority": self.priority,
        }


@dataclass
class ResourceUsage:
    engine_id: str
    cpu_percent: float = 0.0
    ram_mb: float = 0.0
    storage_mb: float = 0.0
    threads: int = 0
    over_limit: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "cpu_percent": self.cpu_percent,
            "ram_mb": self.ram_mb,
            "storage_mb": self.storage_mb,
            "threads": self.threads,
            "over_limit": self.over_limit,
        }


@dataclass
class LeakRecord:
    leak_id: str
    leak_type: str  # memory|resource|handle
    engine_id: str = ""
    size_mb: float = 0.0
    cleaned: bool = False
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "leak_id": self.leak_id,
            "leak_type": self.leak_type,
            "engine_id": self.engine_id,
            "size_mb": self.size_mb,
            "cleaned": self.cleaned,
            "message": self.message,
        }


@dataclass
class CleanupAction:
    action_id: str
    target: str  # unused_memory|temp|dead_threads|cache
    amount: float = 0.0
    success: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "target": self.target,
            "amount": self.amount,
            "success": self.success,
        }


@dataclass
class SystemSnapshot:
    total_cpu_percent: float = 0.0
    total_ram_mb: float = 0.0
    total_storage_mb: float = 0.0
    total_threads: int = 0
    available_cpu_percent: float = 100.0
    available_ram_mb: float = 0.0
    available_storage_mb: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_cpu_percent": self.total_cpu_percent,
            "total_ram_mb": self.total_ram_mb,
            "total_storage_mb": self.total_storage_mb,
            "total_threads": self.total_threads,
            "available_cpu_percent": self.available_cpu_percent,
            "available_ram_mb": self.available_ram_mb,
            "available_storage_mb": self.available_storage_mb,
        }


@dataclass
class ResourceFinding:
    severity: str
    code: str
    message: str
    affected: str = ""
    resolution_hint: str = ""
    category: str = "resource"

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
class ResourceProvenance:
    engine_name: str = "resource_management"
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
class ResourceManagementReport:
    report_id: str = ""
    quotas: List[ResourceQuota] = field(default_factory=list)
    usage: List[ResourceUsage] = field(default_factory=list)
    leaks: List[LeakRecord] = field(default_factory=list)
    cleanups: List[CleanupAction] = field(default_factory=list)
    system: SystemSnapshot = field(default_factory=SystemSnapshot)
    findings: List[ResourceFinding] = field(default_factory=list)
    engine_count: int = 0
    over_limit_count: int = 0
    leak_count: int = 0
    recovered: bool = False
    self_verification_passed: bool = False
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: ResourceProvenance = field(default_factory=ResourceProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "quotas": [q.to_dict() for q in self.quotas],
            "usage": [u.to_dict() for u in self.usage],
            "leaks": [l.to_dict() for l in self.leaks],
            "cleanups": [c.to_dict() for c in self.cleanups],
            "system": self.system.to_dict(),
            "findings": [f.to_dict() for f in self.findings],
            "engine_count": self.engine_count,
            "over_limit_count": self.over_limit_count,
            "leak_count": self.leak_count,
            "recovered": self.recovered,
            "self_verification_passed": self.self_verification_passed,
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_SYNC", "SOURCE_ORCHESTRATOR", "SOURCE_ECOSYSTEM",
    "SOURCE_EXECUTION_CONTEXT", "SOURCE_USER_REQUEST", "ALL_SOURCES",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW", "SEVERITY_INFO",
    "RES_CPU", "RES_RAM", "RES_STORAGE", "RES_THREAD", "ALL_RESOURCES",
    "RULE_NO_OVER_LIMIT", "RULE_NO_SYSTEM_DEGRADE", "RULE_LEAKS_CLEANED",
    "RULE_SELF_VERIFICATION", "RULE_QUALITY_PASS", "ALL_QUALITY_RULES",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "ResourceQuota", "ResourceUsage", "LeakRecord", "CleanupAction", "SystemSnapshot",
    "ResourceFinding", "CacheInfo", "ResourceProvenance", "ResourceManagementReport",
]
