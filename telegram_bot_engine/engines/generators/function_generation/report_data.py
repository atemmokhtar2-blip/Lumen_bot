"""
Generated Method Skeletons data model (Specification 032).

Builds full function/method signatures without any business logic or bodies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


SOURCE_CLASS_GENERATION = "class_generation_report"
SOURCE_COMPONENT_ARCHITECTURE = "component_architecture_blueprint"
SOURCE_INTERFACE_CONTRACT = "interface_contract_blueprint"
SOURCE_CODE_PLAN = "code_generation_plan"
SOURCE_MODULE_ARCHITECTURE = "module_architecture_blueprint"

ALL_SOURCES = (
    SOURCE_CLASS_GENERATION,
    SOURCE_COMPONENT_ARCHITECTURE,
    SOURCE_INTERFACE_CONTRACT,
    SOURCE_CODE_PLAN,
    SOURCE_MODULE_ARCHITECTURE,
)

VIS_PUBLIC = "public"
VIS_PRIVATE = "private"
VIS_PROTECTED = "protected"
VIS_ABSTRACT = "abstract"

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

CONFLICT_DUPLICATE_METHOD = "duplicate_method"
CONFLICT_SIGNATURE_CLASH = "signature_clash"
CONFLICT_MISSING_METHOD = "missing_method"
CONFLICT_NAMING = "naming_violation"

ALL_CONFLICT_TYPES = (
    CONFLICT_DUPLICATE_METHOD, CONFLICT_SIGNATURE_CLASH,
    CONFLICT_MISSING_METHOD, CONFLICT_NAMING,
)

RULE_NO_DUPLICATES = "no_duplicates"
RULE_NO_SIGNATURE_CLASH = "no_signature_clash"
RULE_SKELETONS_ONLY = "skeletons_only"
RULE_ALL_CLASSES_COVERED = "all_classes_covered"
RULE_SUFFICIENT_CONFIDENCE = "sufficient_confidence"

ALL_QUALITY_RULES = (
    RULE_NO_DUPLICATES,
    RULE_NO_SIGNATURE_CLASH,
    RULE_SKELETONS_ONLY,
    RULE_ALL_CLASSES_COVERED,
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
class ParamSpec:
    name: str
    type_hint: str = "Any"
    default: str = ""
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type_hint": self.type_hint,
            "default": self.default,
            "description": self.description,
        }


@dataclass
class MethodDocSkeleton:
    description: str = ""
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    exceptions: List[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "exceptions": list(self.exceptions),
            "notes": self.notes,
        }


@dataclass
class MethodSkeleton:
    method_id: str
    name: str
    class_id: str = ""
    class_name: str = ""
    visibility: str = VIS_PUBLIC
    is_async: bool = False
    is_abstract: bool = False
    is_constructor: bool = False
    is_classmethod: bool = False
    is_staticmethod: bool = False
    params: List[ParamSpec] = field(default_factory=list)
    return_type: str = "None"
    exceptions: List[str] = field(default_factory=list)
    decorators: List[str] = field(default_factory=list)
    purpose: str = ""
    dependencies: List[str] = field(default_factory=list)
    docstring: MethodDocSkeleton = field(default_factory=MethodDocSkeleton)
    source_signature: str = ""  # signature line only, no body
    body: None = None  # explicit: never implemented

    def to_dict(self) -> Dict[str, Any]:
        return {
            "method_id": self.method_id,
            "name": self.name,
            "class_id": self.class_id,
            "class_name": self.class_name,
            "visibility": self.visibility,
            "is_async": self.is_async,
            "is_abstract": self.is_abstract,
            "is_constructor": self.is_constructor,
            "is_classmethod": self.is_classmethod,
            "is_staticmethod": self.is_staticmethod,
            "params": [p.to_dict() for p in self.params],
            "return_type": self.return_type,
            "exceptions": list(self.exceptions),
            "decorators": list(self.decorators),
            "purpose": self.purpose,
            "dependencies": list(self.dependencies),
            "docstring": self.docstring.to_dict(),
            "source_signature": self.source_signature,
            "body": None,
        }


@dataclass
class MethodConflict:
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
class MethodFinding:
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
class MethodProvenance:
    engine_name: str = "function_generation"
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
class FunctionGenerationReport:
    """Complete Function / Method Generation Report (skeletons only)."""

    report_id: str = ""
    methods: List[MethodSkeleton] = field(default_factory=list)
    method_registry: Dict[str, List[str]] = field(default_factory=dict)  # class_id -> method_ids
    conflicts: List[MethodConflict] = field(default_factory=list)
    findings: List[MethodFinding] = field(default_factory=list)
    method_count: int = 0
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: MethodProvenance = field(default_factory=MethodProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "methods": [m.to_dict() for m in self.methods],
            "method_registry": {k: list(v) for k, v in self.method_registry.items()},
            "conflicts": [c.to_dict() for c in self.conflicts],
            "findings": [f.to_dict() for f in self.findings],
            "method_count": self.method_count,
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_CLASS_GENERATION", "SOURCE_COMPONENT_ARCHITECTURE",
    "SOURCE_INTERFACE_CONTRACT", "SOURCE_CODE_PLAN", "SOURCE_MODULE_ARCHITECTURE",
    "ALL_SOURCES",
    "VIS_PUBLIC", "VIS_PRIVATE", "VIS_PROTECTED", "VIS_ABSTRACT",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW",
    "CONFLICT_DUPLICATE_METHOD", "CONFLICT_SIGNATURE_CLASH",
    "CONFLICT_MISSING_METHOD", "CONFLICT_NAMING", "ALL_CONFLICT_TYPES",
    "RULE_NO_DUPLICATES", "RULE_NO_SIGNATURE_CLASH", "RULE_SKELETONS_ONLY",
    "RULE_ALL_CLASSES_COVERED", "RULE_SUFFICIENT_CONFIDENCE", "ALL_QUALITY_RULES",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "ParamSpec", "MethodDocSkeleton", "MethodSkeleton",
    "MethodConflict", "MethodFinding", "CacheInfo", "MethodProvenance",
    "FunctionGenerationReport",
]
