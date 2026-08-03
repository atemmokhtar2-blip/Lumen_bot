"""
Resource & Dependency Blueprint data model (Specification 025).

Plans all external dependencies and runtime resources before generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


SOURCE_EXECUTION_PLAN = "execution_plan"
SOURCE_PROJECT_STRUCTURE = "project_structure_blueprint"
SOURCE_MODULE_ARCHITECTURE = "module_architecture_blueprint"
SOURCE_COMPONENT_ARCHITECTURE = "component_architecture_blueprint"
SOURCE_INTERFACE_CONTRACT = "interface_contract_blueprint"
SOURCE_DATA_FLOW = "data_flow_blueprint"
SOURCE_TECHNOLOGY_SELECTION = "technology_selection_report"

ALL_SOURCES = (
    SOURCE_EXECUTION_PLAN,
    SOURCE_PROJECT_STRUCTURE,
    SOURCE_MODULE_ARCHITECTURE,
    SOURCE_COMPONENT_ARCHITECTURE,
    SOURCE_INTERFACE_CONTRACT,
    SOURCE_DATA_FLOW,
    SOURCE_TECHNOLOGY_SELECTION,
)

DEP_LIBRARY = "library"
DEP_FRAMEWORK = "framework"
DEP_SDK = "sdk"
DEP_DRIVER = "driver"
DEP_CLI = "cli_tool"
DEP_SYSTEM = "system_package"
DEP_API = "external_api"
DEP_DATABASE = "database"
DEP_STORAGE = "storage"
DEP_OTHER = "other"

ALL_DEP_KINDS = (
    DEP_LIBRARY, DEP_FRAMEWORK, DEP_SDK, DEP_DRIVER, DEP_CLI,
    DEP_SYSTEM, DEP_API, DEP_DATABASE, DEP_STORAGE, DEP_OTHER,
)

RES_CONFIG = "config_file"
RES_ENV = "environment_variable"
RES_SECRET = "secret"
RES_API_KEY = "api_key"
RES_ASSET = "static_asset"
RES_TEMPLATE = "template"
RES_LOG = "log"
RES_TEMP = "temporary"
RES_OTHER = "other"

ALL_RES_KINDS = (
    RES_CONFIG, RES_ENV, RES_SECRET, RES_API_KEY,
    RES_ASSET, RES_TEMPLATE, RES_LOG, RES_TEMP, RES_OTHER,
)

RISK_DEPRECATED = "deprecated"
RISK_UNMAINTAINED = "unmaintained"
RISK_SECURITY = "security_issue"
RISK_VERSION_CONFLICT = "version_conflict"
RISK_LICENSE = "license_problem"
RISK_OTHER = "other"

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

CONFLICT_VERSION = "version_conflict"
CONFLICT_DUPLICATE_DEP = "duplicate_dependency"
CONFLICT_INCOMPATIBLE = "incompatible"
CONFLICT_MISSING_RESOURCE = "missing_resource"
CONFLICT_LICENSE = "license_conflict"

ALL_CONFLICT_TYPES = (
    CONFLICT_VERSION, CONFLICT_DUPLICATE_DEP, CONFLICT_INCOMPATIBLE,
    CONFLICT_MISSING_RESOURCE, CONFLICT_LICENSE,
)

RULE_NO_CRITICAL_CONFLICTS = "no_critical_conflicts"
RULE_NO_VERSION_CONFLICTS = "no_version_conflicts"
RULE_NO_SECURITY_RISKS = "no_critical_security_risks"
RULE_ALL_DEPS_RESOLVED = "all_dependencies_resolved"
RULE_ARCHITECTURE_COMPLETE = "architecture_complete"
RULE_SUFFICIENT_CONFIDENCE = "sufficient_confidence"

ALL_QUALITY_RULES = (
    RULE_NO_CRITICAL_CONFLICTS,
    RULE_NO_VERSION_CONFLICTS,
    RULE_NO_SECURITY_RISKS,
    RULE_ALL_DEPS_RESOLVED,
    RULE_ARCHITECTURE_COMPLETE,
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

VERDICT_READY = "ready"
VERDICT_READY_WITH_WARNINGS = "ready_with_warnings"
VERDICT_NOT_READY = "not_ready"

ALL_VERDICTS = (VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY)


@dataclass
class DependencyItem:
    dep_id: str
    name: str
    kind: str = DEP_LIBRARY
    version: str = ""
    version_constraint: str = ""
    purpose: str = ""
    required_by: List[str] = field(default_factory=list)  # component/module ids
    license: str = ""
    maintained: bool = True
    optional: bool = False
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dep_id": self.dep_id,
            "name": self.name,
            "kind": self.kind,
            "version": self.version,
            "version_constraint": self.version_constraint,
            "purpose": self.purpose,
            "required_by": list(self.required_by),
            "license": self.license,
            "maintained": self.maintained,
            "optional": self.optional,
            "tags": list(self.tags),
        }


@dataclass
class ResourceItem:
    resource_id: str
    name: str
    kind: str = RES_OTHER
    path_or_key: str = ""
    description: str = ""
    required: bool = True
    sensitivity: str = "internal"
    consumed_by: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "name": self.name,
            "kind": self.kind,
            "path_or_key": self.path_or_key,
            "description": self.description,
            "required": self.required,
            "sensitivity": self.sensitivity,
            "consumed_by": list(self.consumed_by),
        }


@dataclass
class VersionMatrixEntry:
    package: str
    version: str
    compatible_with: List[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "package": self.package,
            "version": self.version,
            "compatible_with": list(self.compatible_with),
            "notes": self.notes,
        }


@dataclass
class RiskItem:
    risk_id: str
    risk_type: str
    severity: str = SEVERITY_MEDIUM
    target: str = ""  # dep_id or resource_id
    message: str = ""
    mitigation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk_id": self.risk_id,
            "risk_type": self.risk_type,
            "severity": self.severity,
            "target": self.target,
            "message": self.message,
            "mitigation": self.mitigation,
        }


@dataclass
class OptimizationSuggestion:
    suggestion_id: str
    description: str
    removes: List[str] = field(default_factory=list)
    replaces_with: str = ""
    benefit: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "suggestion_id": self.suggestion_id,
            "description": self.description,
            "removes": list(self.removes),
            "replaces_with": self.replaces_with,
            "benefit": self.benefit,
        }


@dataclass
class ResourceConflict:
    conflict_id: str
    conflict_type: str
    severity: str = SEVERITY_HIGH
    message: str = ""
    affected_ids: List[str] = field(default_factory=list)
    resolution_hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "conflict_type": self.conflict_type,
            "severity": self.severity,
            "message": self.message,
            "affected_ids": list(self.affected_ids),
            "resolution_hint": self.resolution_hint,
        }


@dataclass
class ResourceFinding:
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
class ResourceProvenance:
    engine_name: str = "resource_dependency_planning"
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
class ResourceDependencyBlueprint:
    """Complete Resource & Dependency Blueprint."""

    blueprint_id: str = ""
    dependencies: List[DependencyItem] = field(default_factory=list)
    resources: List[ResourceItem] = field(default_factory=list)
    version_matrix: List[VersionMatrixEntry] = field(default_factory=list)
    risks: List[RiskItem] = field(default_factory=list)
    optimizations: List[OptimizationSuggestion] = field(default_factory=list)
    conflicts: List[ResourceConflict] = field(default_factory=list)
    findings: List[ResourceFinding] = field(default_factory=list)
    python_version: str = ">=3.10"
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: ResourceProvenance = field(default_factory=ResourceProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "blueprint_id": self.blueprint_id,
            "dependencies": [d.to_dict() for d in self.dependencies],
            "resources": [r.to_dict() for r in self.resources],
            "version_matrix": [v.to_dict() for v in self.version_matrix],
            "risks": [r.to_dict() for r in self.risks],
            "optimizations": [o.to_dict() for o in self.optimizations],
            "conflicts": [c.to_dict() for c in self.conflicts],
            "findings": [f.to_dict() for f in self.findings],
            "python_version": self.python_version,
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
    "SOURCE_TECHNOLOGY_SELECTION", "ALL_SOURCES",
    "DEP_LIBRARY", "DEP_FRAMEWORK", "DEP_SDK", "DEP_DRIVER", "DEP_CLI",
    "DEP_SYSTEM", "DEP_API", "DEP_DATABASE", "DEP_STORAGE", "DEP_OTHER", "ALL_DEP_KINDS",
    "RES_CONFIG", "RES_ENV", "RES_SECRET", "RES_API_KEY", "RES_ASSET",
    "RES_TEMPLATE", "RES_LOG", "RES_TEMP", "RES_OTHER", "ALL_RES_KINDS",
    "RISK_DEPRECATED", "RISK_UNMAINTAINED", "RISK_SECURITY", "RISK_VERSION_CONFLICT",
    "RISK_LICENSE", "RISK_OTHER",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW",
    "CONFLICT_VERSION", "CONFLICT_DUPLICATE_DEP", "CONFLICT_INCOMPATIBLE",
    "CONFLICT_MISSING_RESOURCE", "CONFLICT_LICENSE", "ALL_CONFLICT_TYPES",
    "RULE_NO_CRITICAL_CONFLICTS", "RULE_NO_VERSION_CONFLICTS", "RULE_NO_SECURITY_RISKS",
    "RULE_ALL_DEPS_RESOLVED", "RULE_ARCHITECTURE_COMPLETE", "RULE_SUFFICIENT_CONFIDENCE",
    "ALL_QUALITY_RULES",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "DependencyItem", "ResourceItem", "VersionMatrixEntry", "RiskItem",
    "OptimizationSuggestion", "ResourceConflict", "ResourceFinding",
    "CacheInfo", "ResourceProvenance", "ResourceDependencyBlueprint",
]
