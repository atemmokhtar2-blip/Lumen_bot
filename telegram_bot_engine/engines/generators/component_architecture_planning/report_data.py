"""
Component Architecture Blueprint data model (Specification 022).

Designs the internal components of every module before any file is created.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------#
# Sources
# ---------------------------------------------------------------------------#

SOURCE_MODULE_ARCHITECTURE = "module_architecture_blueprint"
SOURCE_PROJECT_STRUCTURE = "project_structure_blueprint"
SOURCE_EXECUTION_PLAN = "execution_plan"
SOURCE_ARCHITECTURE_DECISION = "architecture_decision_report"
SOURCE_NORMALIZED_REQUIREMENTS = "requirement_normalization_report"

ALL_SOURCES = (
    SOURCE_MODULE_ARCHITECTURE,
    SOURCE_PROJECT_STRUCTURE,
    SOURCE_EXECUTION_PLAN,
    SOURCE_ARCHITECTURE_DECISION,
    SOURCE_NORMALIZED_REQUIREMENTS,
)


# ---------------------------------------------------------------------------#
# Component kinds
# ---------------------------------------------------------------------------#

KIND_CONTROLLER = "controller"
KIND_SERVICE = "service"
KIND_MANAGER = "manager"
KIND_REPOSITORY = "repository"
KIND_ADAPTER = "adapter"
KIND_VALIDATOR = "validator"
KIND_HELPER = "helper"
KIND_UTILITY = "utility"
KIND_FACTORY = "factory"
KIND_BUILDER = "builder"
KIND_STRATEGY = "strategy"
KIND_PROVIDER = "provider"
KIND_OTHER = "other"

ALL_KINDS = (
    KIND_CONTROLLER, KIND_SERVICE, KIND_MANAGER, KIND_REPOSITORY,
    KIND_ADAPTER, KIND_VALIDATOR, KIND_HELPER, KIND_UTILITY,
    KIND_FACTORY, KIND_BUILDER, KIND_STRATEGY, KIND_PROVIDER, KIND_OTHER,
)


# ---------------------------------------------------------------------------#
# Communication / dependency
# ---------------------------------------------------------------------------#

COMM_INTERFACE = "interface"
COMM_EVENT = "event"
COMM_DIRECT = "direct"
COMM_SHARED = "shared"

DEP_HARD = "hard"
DEP_SOFT = "soft"
DEP_OPTIONAL = "optional"


# ---------------------------------------------------------------------------#
# Severity / conflict / quality / verdict
# ---------------------------------------------------------------------------#

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

CONFLICT_DUPLICATE_COMPONENT = "duplicate_component"
CONFLICT_OVERLAPPING_RESPONSIBILITY = "overlapping_responsibility"
CONFLICT_CIRCULAR_DEPENDENCY = "circular_dependency"
CONFLICT_HIDDEN_DEPENDENCY = "hidden_dependency"
CONFLICT_STRONG_COUPLING = "strong_coupling"
CONFLICT_UNUSED_COMPONENT = "unused_component"
CONFLICT_MISSING_INTERFACE = "missing_interface"

ALL_CONFLICT_TYPES = (
    CONFLICT_DUPLICATE_COMPONENT,
    CONFLICT_OVERLAPPING_RESPONSIBILITY,
    CONFLICT_CIRCULAR_DEPENDENCY,
    CONFLICT_HIDDEN_DEPENDENCY,
    CONFLICT_STRONG_COUPLING,
    CONFLICT_UNUSED_COMPONENT,
    CONFLICT_MISSING_INTERFACE,
)

RULE_NO_CRITICAL_CONFLICTS = "no_critical_conflicts"
RULE_NO_DUPLICATES = "no_duplicates"
RULE_NO_OVERLAPPING = "no_overlapping_responsibilities"
RULE_NO_CIRCULAR = "no_circular_dependencies"
RULE_ARCHITECTURE_COMPLETE = "architecture_complete"
RULE_SUFFICIENT_CONFIDENCE = "sufficient_confidence"

ALL_QUALITY_RULES = (
    RULE_NO_CRITICAL_CONFLICTS,
    RULE_NO_DUPLICATES,
    RULE_NO_OVERLAPPING,
    RULE_NO_CIRCULAR,
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


# ---------------------------------------------------------------------------#
# Data classes
# ---------------------------------------------------------------------------#

@dataclass
class ComponentInterface:
    interface_id: str
    name: str
    description: str = ""
    methods: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "interface_id": self.interface_id,
            "name": self.name,
            "description": self.description,
            "methods": list(self.methods),
        }


@dataclass
class ComponentDescriptor:
    """A single component inside a module."""

    component_id: str
    name: str
    kind: str = KIND_OTHER
    module_id: str = ""
    purpose: str = ""
    responsibility: str = ""
    boundaries: str = ""
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    interfaces: List[ComponentInterface] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)
    communication_rules: List[str] = field(default_factory=list)
    reusable: bool = False
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "component_id": self.component_id,
            "name": self.name,
            "kind": self.kind,
            "module_id": self.module_id,
            "purpose": self.purpose,
            "responsibility": self.responsibility,
            "boundaries": self.boundaries,
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "interfaces": [i.to_dict() for i in self.interfaces],
            "depends_on": list(self.depends_on),
            "communication_rules": list(self.communication_rules),
            "reusable": self.reusable,
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
        }


@dataclass
class ComponentRelation:
    from_component_id: str
    to_component_id: str
    relation_type: str = DEP_HARD
    communication: str = COMM_INTERFACE
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_component_id": self.from_component_id,
            "to_component_id": self.to_component_id,
            "relation_type": self.relation_type,
            "communication": self.communication,
            "reason": self.reason,
        }


@dataclass
class ReuseOpportunity:
    opportunity_id: str
    component_ids: List[str] = field(default_factory=list)
    reason: str = ""
    suggested_shared_name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "component_ids": list(self.component_ids),
            "reason": self.reason,
            "suggested_shared_name": self.suggested_shared_name,
        }


@dataclass
class ComponentConflict:
    conflict_id: str
    conflict_type: str
    severity: str = SEVERITY_HIGH
    message: str = ""
    affected_components: List[str] = field(default_factory=list)
    resolution_hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "conflict_type": self.conflict_type,
            "severity": self.severity,
            "message": self.message,
            "affected_components": list(self.affected_components),
            "resolution_hint": self.resolution_hint,
        }


@dataclass
class ComponentFinding:
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
class ComponentProvenance:
    engine_name: str = "component_architecture_planning"
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
class ComponentArchitectureBlueprint:
    """Complete Component Architecture Blueprint."""

    blueprint_id: str = ""
    components: List[ComponentDescriptor] = field(default_factory=list)
    relations: List[ComponentRelation] = field(default_factory=list)
    interfaces: List[ComponentInterface] = field(default_factory=list)
    reuse_opportunities: List[ReuseOpportunity] = field(default_factory=list)
    conflicts: List[ComponentConflict] = field(default_factory=list)
    findings: List[ComponentFinding] = field(default_factory=list)
    communication_map: Dict[str, List[str]] = field(default_factory=dict)
    dependency_graph: Dict[str, List[str]] = field(default_factory=dict)
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: ComponentProvenance = field(default_factory=ComponentProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "blueprint_id": self.blueprint_id,
            "components": [c.to_dict() for c in self.components],
            "relations": [r.to_dict() for r in self.relations],
            "interfaces": [i.to_dict() for i in self.interfaces],
            "reuse_opportunities": [r.to_dict() for r in self.reuse_opportunities],
            "conflicts": [c.to_dict() for c in self.conflicts],
            "findings": [f.to_dict() for f in self.findings],
            "communication_map": {k: list(v) for k, v in self.communication_map.items()},
            "dependency_graph": {k: list(v) for k, v in self.dependency_graph.items()},
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_MODULE_ARCHITECTURE",
    "SOURCE_PROJECT_STRUCTURE",
    "SOURCE_EXECUTION_PLAN",
    "SOURCE_ARCHITECTURE_DECISION",
    "SOURCE_NORMALIZED_REQUIREMENTS",
    "ALL_SOURCES",
    "KIND_CONTROLLER",
    "KIND_SERVICE",
    "KIND_MANAGER",
    "KIND_REPOSITORY",
    "KIND_ADAPTER",
    "KIND_VALIDATOR",
    "KIND_HELPER",
    "KIND_UTILITY",
    "KIND_FACTORY",
    "KIND_BUILDER",
    "KIND_STRATEGY",
    "KIND_PROVIDER",
    "KIND_OTHER",
    "ALL_KINDS",
    "COMM_INTERFACE",
    "COMM_EVENT",
    "COMM_DIRECT",
    "COMM_SHARED",
    "DEP_HARD",
    "DEP_SOFT",
    "DEP_OPTIONAL",
    "SEVERITY_CRITICAL",
    "SEVERITY_HIGH",
    "SEVERITY_MEDIUM",
    "SEVERITY_LOW",
    "CONFLICT_DUPLICATE_COMPONENT",
    "CONFLICT_OVERLAPPING_RESPONSIBILITY",
    "CONFLICT_CIRCULAR_DEPENDENCY",
    "CONFLICT_HIDDEN_DEPENDENCY",
    "CONFLICT_STRONG_COUPLING",
    "CONFLICT_UNUSED_COMPONENT",
    "CONFLICT_MISSING_INTERFACE",
    "ALL_CONFLICT_TYPES",
    "RULE_NO_CRITICAL_CONFLICTS",
    "RULE_NO_DUPLICATES",
    "RULE_NO_OVERLAPPING",
    "RULE_NO_CIRCULAR",
    "RULE_ARCHITECTURE_COMPLETE",
    "RULE_SUFFICIENT_CONFIDENCE",
    "ALL_QUALITY_RULES",
    "CACHE_HIT",
    "CACHE_MISS",
    "CACHE_DISABLED",
    "CONFIDENCE_HIGH",
    "CONFIDENCE_MEDIUM",
    "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD",
    "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY",
    "VERDICT_READY_WITH_WARNINGS",
    "VERDICT_NOT_READY",
    "ALL_VERDICTS",
    "ComponentInterface",
    "ComponentDescriptor",
    "ComponentRelation",
    "ReuseOpportunity",
    "ComponentConflict",
    "ComponentFinding",
    "CacheInfo",
    "ComponentProvenance",
    "ComponentArchitectureBlueprint",
]
