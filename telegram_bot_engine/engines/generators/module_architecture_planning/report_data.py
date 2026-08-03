"""
Module Architecture Blueprint data model (Specification 021).

This module defines the :class:`ModuleArchitectureBlueprint` -- the
complete, authoritative output of the
:class:`~telegram_bot_engine.engines.generators.module_architecture_planning.ModuleArchitecturePlanningEngine`.

The Module Architecture Planning Engine designs every logical module
of the project **before any file is created**.  It does **not** write
code or create files.  Its sole function is to produce a clear module
architecture that prevents overlapping responsibilities and defines
clean interfaces between modules.

Data sources
------------
1. Execution Plan
2. Project Structure Blueprint
3. Architecture Decision Report
4. Normalized Requirement Model
5. Technology Selection Report
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------#
# Source constants
# ---------------------------------------------------------------------------#

SOURCE_EXECUTION_PLAN = "execution_plan"
SOURCE_PROJECT_STRUCTURE = "project_structure_blueprint"
SOURCE_ARCHITECTURE_DECISION = "architecture_decision_report"
SOURCE_NORMALIZED_REQUIREMENTS = "requirement_normalization_report"
SOURCE_TECHNOLOGY_SELECTION = "technology_selection_report"

ALL_SOURCES = (
    SOURCE_EXECUTION_PLAN,
    SOURCE_PROJECT_STRUCTURE,
    SOURCE_ARCHITECTURE_DECISION,
    SOURCE_NORMALIZED_REQUIREMENTS,
    SOURCE_TECHNOLOGY_SELECTION,
)


# ---------------------------------------------------------------------------#
# Module category constants
# ---------------------------------------------------------------------------#

CATEGORY_CORE = "core"
CATEGORY_BUSINESS = "business"
CATEGORY_INFRASTRUCTURE = "infrastructure"
CATEGORY_INTEGRATION = "integration"
CATEGORY_SUPPORT = "support"
CATEGORY_TESTING = "testing"
CATEGORY_OTHER = "other"

ALL_CATEGORIES = (
    CATEGORY_CORE,
    CATEGORY_BUSINESS,
    CATEGORY_INFRASTRUCTURE,
    CATEGORY_INTEGRATION,
    CATEGORY_SUPPORT,
    CATEGORY_TESTING,
    CATEGORY_OTHER,
)


# ---------------------------------------------------------------------------#
# Communication / dependency constants
# ---------------------------------------------------------------------------#

COMM_INTERFACE = "interface"
COMM_EVENT = "event"
COMM_DIRECT = "direct"
COMM_SHARED = "shared"

ALL_COMM_TYPES = (COMM_INTERFACE, COMM_EVENT, COMM_DIRECT, COMM_SHARED)

DEP_HARD = "hard"
DEP_SOFT = "soft"
DEP_OPTIONAL = "optional"

ALL_DEP_KINDS = (DEP_HARD, DEP_SOFT, DEP_OPTIONAL)


# ---------------------------------------------------------------------------#
# Severity / conflict / quality / verdict constants
# ---------------------------------------------------------------------------#

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

ALL_SEVERITIES = (SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW)

CONFLICT_DUPLICATE_MODULE = "duplicate_module"
CONFLICT_OVERLAPPING_RESPONSIBILITY = "overlapping_responsibility"
CONFLICT_CIRCULAR_DEPENDENCY = "circular_dependency"
CONFLICT_HIDDEN_DEPENDENCY = "hidden_dependency"
CONFLICT_STRONG_COUPLING = "strong_coupling"
CONFLICT_MISSING_INTERFACE = "missing_interface"
CONFLICT_INCOMPLETE_MODULE = "incomplete_module"

ALL_CONFLICT_TYPES = (
    CONFLICT_DUPLICATE_MODULE,
    CONFLICT_OVERLAPPING_RESPONSIBILITY,
    CONFLICT_CIRCULAR_DEPENDENCY,
    CONFLICT_HIDDEN_DEPENDENCY,
    CONFLICT_STRONG_COUPLING,
    CONFLICT_MISSING_INTERFACE,
    CONFLICT_INCOMPLETE_MODULE,
)

RULE_NO_CRITICAL_CONFLICTS = "no_critical_conflicts"
RULE_NO_DUPLICATES = "no_duplicates"
RULE_NO_OVERLAPPING_RESPONSIBILITIES = "no_overlapping_responsibilities"
RULE_NO_CIRCULAR_DEPENDENCIES = "no_circular_dependencies"
RULE_ALL_INTERFACES_DEFINED = "all_interfaces_defined"
RULE_ARCHITECTURE_COMPLETE = "architecture_complete"
RULE_SUFFICIENT_CONFIDENCE = "sufficient_confidence"

ALL_QUALITY_RULES = (
    RULE_NO_CRITICAL_CONFLICTS,
    RULE_NO_DUPLICATES,
    RULE_NO_OVERLAPPING_RESPONSIBILITIES,
    RULE_NO_CIRCULAR_DEPENDENCIES,
    RULE_ALL_INTERFACES_DEFINED,
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
class ModuleInterface:
    """A public interface exposed by a module."""

    interface_id: str
    name: str
    description: str = ""
    methods: List[str] = field(default_factory=list)
    events: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "interface_id": self.interface_id,
            "name": self.name,
            "description": self.description,
            "methods": list(self.methods),
            "events": list(self.events),
        }


@dataclass
class ModuleDescriptor:
    """Full description of a single logical module.

    Attributes:
        module_id: Unique identifier.
        name: Human-readable name.
        category: One of ALL_CATEGORIES.
        purpose: High-level goal of the module.
        responsibility: Detailed responsibility statement.
        boundaries: What the module must NOT do.
        inputs: Expected inputs / messages.
        outputs: Produced outputs / events.
        interfaces: Public interfaces this module exposes.
        depends_on: Other module_ids this module requires.
        communication_rules: Allowed communication styles.
        folder_path: Suggested physical location.
        tags: Classification tags.
    """

    module_id: str
    name: str
    category: str = CATEGORY_OTHER
    purpose: str = ""
    responsibility: str = ""
    boundaries: str = ""
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    interfaces: List[ModuleInterface] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)
    communication_rules: List[str] = field(default_factory=list)
    folder_path: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module_id": self.module_id,
            "name": self.name,
            "category": self.category,
            "purpose": self.purpose,
            "responsibility": self.responsibility,
            "boundaries": self.boundaries,
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "interfaces": [i.to_dict() for i in self.interfaces],
            "depends_on": list(self.depends_on),
            "communication_rules": list(self.communication_rules),
            "folder_path": self.folder_path,
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
        }


@dataclass
class ModuleRelation:
    """A directed relationship between two modules."""

    from_module_id: str
    to_module_id: str
    relation_type: str = DEP_HARD
    communication: str = COMM_INTERFACE
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_module_id": self.from_module_id,
            "to_module_id": self.to_module_id,
            "relation_type": self.relation_type,
            "communication": self.communication,
            "reason": self.reason,
        }


@dataclass
class ArchitectureConflict:
    """A detected architectural problem."""

    conflict_id: str
    conflict_type: str
    severity: str = SEVERITY_HIGH
    message: str = ""
    affected_modules: List[str] = field(default_factory=list)
    resolution_hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "conflict_type": self.conflict_type,
            "severity": self.severity,
            "message": self.message,
            "affected_modules": list(self.affected_modules),
            "resolution_hint": self.resolution_hint,
        }


@dataclass
class ArchitectureFinding:
    """A quality / validation finding."""

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
class ArchitectureProvenance:
    engine_name: str = "module_architecture_planning"
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
class ModuleArchitectureBlueprint:
    """The complete Module Architecture Blueprint.

    Downstream engines treat this as the single source of truth for
    the logical module structure of the generated project.
    """

    blueprint_id: str = ""
    modules: List[ModuleDescriptor] = field(default_factory=list)
    relations: List[ModuleRelation] = field(default_factory=list)
    interfaces: List[ModuleInterface] = field(default_factory=list)
    conflicts: List[ArchitectureConflict] = field(default_factory=list)
    findings: List[ArchitectureFinding] = field(default_factory=list)
    dependency_graph: Dict[str, List[str]] = field(default_factory=dict)
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: ArchitectureProvenance = field(default_factory=ArchitectureProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "blueprint_id": self.blueprint_id,
            "modules": [m.to_dict() for m in self.modules],
            "relations": [r.to_dict() for r in self.relations],
            "interfaces": [i.to_dict() for i in self.interfaces],
            "conflicts": [c.to_dict() for c in self.conflicts],
            "findings": [f.to_dict() for f in self.findings],
            "dependency_graph": {k: list(v) for k, v in self.dependency_graph.items()},
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_EXECUTION_PLAN",
    "SOURCE_PROJECT_STRUCTURE",
    "SOURCE_ARCHITECTURE_DECISION",
    "SOURCE_NORMALIZED_REQUIREMENTS",
    "SOURCE_TECHNOLOGY_SELECTION",
    "ALL_SOURCES",
    "CATEGORY_CORE",
    "CATEGORY_BUSINESS",
    "CATEGORY_INFRASTRUCTURE",
    "CATEGORY_INTEGRATION",
    "CATEGORY_SUPPORT",
    "CATEGORY_TESTING",
    "CATEGORY_OTHER",
    "ALL_CATEGORIES",
    "COMM_INTERFACE",
    "COMM_EVENT",
    "COMM_DIRECT",
    "COMM_SHARED",
    "ALL_COMM_TYPES",
    "DEP_HARD",
    "DEP_SOFT",
    "DEP_OPTIONAL",
    "ALL_DEP_KINDS",
    "SEVERITY_CRITICAL",
    "SEVERITY_HIGH",
    "SEVERITY_MEDIUM",
    "SEVERITY_LOW",
    "ALL_SEVERITIES",
    "CONFLICT_DUPLICATE_MODULE",
    "CONFLICT_OVERLAPPING_RESPONSIBILITY",
    "CONFLICT_CIRCULAR_DEPENDENCY",
    "CONFLICT_HIDDEN_DEPENDENCY",
    "CONFLICT_STRONG_COUPLING",
    "CONFLICT_MISSING_INTERFACE",
    "CONFLICT_INCOMPLETE_MODULE",
    "ALL_CONFLICT_TYPES",
    "RULE_NO_CRITICAL_CONFLICTS",
    "RULE_NO_DUPLICATES",
    "RULE_NO_OVERLAPPING_RESPONSIBILITIES",
    "RULE_NO_CIRCULAR_DEPENDENCIES",
    "RULE_ALL_INTERFACES_DEFINED",
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
    "ModuleInterface",
    "ModuleDescriptor",
    "ModuleRelation",
    "ArchitectureConflict",
    "ArchitectureFinding",
    "CacheInfo",
    "ArchitectureProvenance",
    "ModuleArchitectureBlueprint",
]
