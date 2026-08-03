"""
Generated Class Skeletons data model (Specification 031).

First engine that writes actual code structure — class skeletons only.
No business logic, no method bodies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


SOURCE_INITIALIZED_PROJECT = "initialized_project_report"
SOURCE_COMPONENT_ARCHITECTURE = "component_architecture_blueprint"
SOURCE_INTERFACE_CONTRACT = "interface_contract_blueprint"
SOURCE_CODE_PLAN = "code_generation_plan"
SOURCE_MODULE_ARCHITECTURE = "module_architecture_blueprint"
SOURCE_GENERATION_STRATEGY = "generation_strategy_blueprint"

ALL_SOURCES = (
    SOURCE_INITIALIZED_PROJECT,
    SOURCE_COMPONENT_ARCHITECTURE,
    SOURCE_INTERFACE_CONTRACT,
    SOURCE_CODE_PLAN,
    SOURCE_MODULE_ARCHITECTURE,
    SOURCE_GENERATION_STRATEGY,
)

CLASS_CONTROLLER = "controller"
CLASS_SERVICE = "service"
CLASS_MANAGER = "manager"
CLASS_REPOSITORY = "repository"
CLASS_ADAPTER = "adapter"
CLASS_FACTORY = "factory"
CLASS_BUILDER = "builder"
CLASS_VALIDATOR = "validator"
CLASS_STRATEGY = "strategy"
CLASS_PROVIDER = "provider"
CLASS_MODEL = "model"
CLASS_DTO = "dto"
CLASS_ENTITY = "entity"
CLASS_UTILITY = "utility"
CLASS_OTHER = "other"

ALL_CLASS_KINDS = (
    CLASS_CONTROLLER, CLASS_SERVICE, CLASS_MANAGER, CLASS_REPOSITORY,
    CLASS_ADAPTER, CLASS_FACTORY, CLASS_BUILDER, CLASS_VALIDATOR,
    CLASS_STRATEGY, CLASS_PROVIDER, CLASS_MODEL, CLASS_DTO,
    CLASS_ENTITY, CLASS_UTILITY, CLASS_OTHER,
)

VIS_PUBLIC = "public"
VIS_PRIVATE = "private"
VIS_PROTECTED = "protected"

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

CONFLICT_DUPLICATE_NAME = "duplicate_name"
CONFLICT_BAD_INHERITANCE = "bad_inheritance"
CONFLICT_CIRCULAR_REF = "circular_reference"
CONFLICT_NAMING = "naming_violation"
CONFLICT_MISSING_INTERFACE = "missing_interface"

ALL_CONFLICT_TYPES = (
    CONFLICT_DUPLICATE_NAME, CONFLICT_BAD_INHERITANCE,
    CONFLICT_CIRCULAR_REF, CONFLICT_NAMING, CONFLICT_MISSING_INTERFACE,
)

RULE_NO_DUPLICATES = "no_duplicates"
RULE_NO_CIRCULARS = "no_circulars"
RULE_NAMING_OK = "naming_ok"
RULE_SKELETONS_ONLY = "skeletons_only"
RULE_ARCHITECTURE_ALIGNED = "architecture_aligned"
RULE_SUFFICIENT_CONFIDENCE = "sufficient_confidence"

ALL_QUALITY_RULES = (
    RULE_NO_DUPLICATES,
    RULE_NO_CIRCULARS,
    RULE_NAMING_OK,
    RULE_SKELETONS_ONLY,
    RULE_ARCHITECTURE_ALIGNED,
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
class MethodSignature:
    name: str
    params: List[str] = field(default_factory=list)
    return_type: str = "None"
    is_async: bool = False
    docstring: str = ""
    # Intentionally NO body — skeleton only

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "params": list(self.params),
            "return_type": self.return_type,
            "is_async": self.is_async,
            "docstring": self.docstring,
            "body": None,  # explicit: no implementation
        }


@dataclass
class PropertySpec:
    name: str
    type_hint: str = "Any"
    default: str = ""
    visibility: str = VIS_PUBLIC
    injected: bool = False  # True = constructor-injected dependency

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type_hint": self.type_hint,
            "default": self.default,
            "visibility": self.visibility,
            "injected": self.injected,
        }


@dataclass
class ClassDocSkeleton:
    description: str = ""
    purpose: str = ""
    responsibilities: List[str] = field(default_factory=list)
    dependencies_note: str = ""
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "purpose": self.purpose,
            "responsibilities": list(self.responsibilities),
            "dependencies_note": self.dependencies_note,
            "notes": self.notes,
        }


@dataclass
class ClassSkeleton:
    class_id: str
    name: str
    kind: str = CLASS_OTHER
    module_path: str = ""
    package: str = ""
    visibility: str = VIS_PUBLIC
    bases: List[str] = field(default_factory=list)
    interfaces: List[str] = field(default_factory=list)
    properties: List[PropertySpec] = field(default_factory=list)
    methods: List[MethodSignature] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    component_ref: str = ""
    docstring: ClassDocSkeleton = field(default_factory=ClassDocSkeleton)
    source_code: str = ""  # generated skeleton source (no bodies)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "class_id": self.class_id,
            "name": self.name,
            "kind": self.kind,
            "module_path": self.module_path,
            "package": self.package,
            "visibility": self.visibility,
            "bases": list(self.bases),
            "interfaces": list(self.interfaces),
            "properties": [p.to_dict() for p in self.properties],
            "methods": [m.to_dict() for m in self.methods],
            "dependencies": list(self.dependencies),
            "component_ref": self.component_ref,
            "docstring": self.docstring.to_dict(),
            "source_code": self.source_code,
            "metadata": dict(self.metadata),
        }


@dataclass
class ClassConflict:
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
class ClassFinding:
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
class ClassProvenance:
    engine_name: str = "class_generation"
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
class ClassGenerationReport:
    """Complete Class Generation Report with skeletons only."""

    report_id: str = ""
    classes: List[ClassSkeleton] = field(default_factory=list)
    conflicts: List[ClassConflict] = field(default_factory=list)
    findings: List[ClassFinding] = field(default_factory=list)
    class_count: int = 0
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: ClassProvenance = field(default_factory=ClassProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "classes": [c.to_dict() for c in self.classes],
            "conflicts": [c.to_dict() for c in self.conflicts],
            "findings": [f.to_dict() for f in self.findings],
            "class_count": self.class_count,
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_INITIALIZED_PROJECT", "SOURCE_COMPONENT_ARCHITECTURE",
    "SOURCE_INTERFACE_CONTRACT", "SOURCE_CODE_PLAN",
    "SOURCE_MODULE_ARCHITECTURE", "SOURCE_GENERATION_STRATEGY", "ALL_SOURCES",
    "CLASS_CONTROLLER", "CLASS_SERVICE", "CLASS_MANAGER", "CLASS_REPOSITORY",
    "CLASS_ADAPTER", "CLASS_FACTORY", "CLASS_BUILDER", "CLASS_VALIDATOR",
    "CLASS_STRATEGY", "CLASS_PROVIDER", "CLASS_MODEL", "CLASS_DTO",
    "CLASS_ENTITY", "CLASS_UTILITY", "CLASS_OTHER", "ALL_CLASS_KINDS",
    "VIS_PUBLIC", "VIS_PRIVATE", "VIS_PROTECTED",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW",
    "CONFLICT_DUPLICATE_NAME", "CONFLICT_BAD_INHERITANCE", "CONFLICT_CIRCULAR_REF",
    "CONFLICT_NAMING", "CONFLICT_MISSING_INTERFACE", "ALL_CONFLICT_TYPES",
    "RULE_NO_DUPLICATES", "RULE_NO_CIRCULARS", "RULE_NAMING_OK",
    "RULE_SKELETONS_ONLY", "RULE_ARCHITECTURE_ALIGNED", "RULE_SUFFICIENT_CONFIDENCE",
    "ALL_QUALITY_RULES",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "MethodSignature", "PropertySpec", "ClassDocSkeleton", "ClassSkeleton",
    "ClassConflict", "ClassFinding", "CacheInfo", "ClassProvenance",
    "ClassGenerationReport",
]
