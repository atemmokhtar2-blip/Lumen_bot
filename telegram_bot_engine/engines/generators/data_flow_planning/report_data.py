"""
Data Flow Blueprint data model (Specification 024).

Designs all data movement paths inside the project before generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


SOURCE_EXECUTION_PLAN = "execution_plan"
SOURCE_PROJECT_STRUCTURE = "project_structure_blueprint"
SOURCE_MODULE_ARCHITECTURE = "module_architecture_blueprint"
SOURCE_COMPONENT_ARCHITECTURE = "component_architecture_blueprint"
SOURCE_INTERFACE_CONTRACT = "interface_contract_blueprint"
SOURCE_NORMALIZED_REQUIREMENTS = "requirement_normalization_report"

ALL_SOURCES = (
    SOURCE_EXECUTION_PLAN,
    SOURCE_PROJECT_STRUCTURE,
    SOURCE_MODULE_ARCHITECTURE,
    SOURCE_COMPONENT_ARCHITECTURE,
    SOURCE_INTERFACE_CONTRACT,
    SOURCE_NORMALIZED_REQUIREMENTS,
)

# Input source kinds
SRC_USER_INPUT = "user_input"
SRC_TELEGRAM_UPDATE = "telegram_update"
SRC_CONFIG = "configuration"
SRC_ENV = "environment"
SRC_EXTERNAL_API = "external_api"
SRC_DATABASE = "database"
SRC_CACHE = "cache"
SRC_IMPORT = "imported_project"
SRC_KNOWLEDGE = "knowledge_base"
SRC_OTHER = "other"

ALL_SRC_KINDS = (
    SRC_USER_INPUT, SRC_TELEGRAM_UPDATE, SRC_CONFIG, SRC_ENV,
    SRC_EXTERNAL_API, SRC_DATABASE, SRC_CACHE, SRC_IMPORT, SRC_KNOWLEDGE, SRC_OTHER,
)

# Transformation kinds
XFORM_CLEAN = "clean"
XFORM_CONVERT = "convert"
XFORM_NORMALIZE = "normalize"
XFORM_VALIDATE = "validate"
XFORM_FILTER = "filter"
XFORM_ENCRYPT = "encrypt"
XFORM_DECRYPT = "decrypt"
XFORM_OTHER = "other"

# Sensitivity
SENSITIVITY_PUBLIC = "public"
SENSITIVITY_INTERNAL = "internal"
SENSITIVITY_SENSITIVE = "sensitive"
SENSITIVITY_SECRET = "secret"

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

CONFLICT_MISSING_PATH = "missing_path"
CONFLICT_INFINITE_LOOP = "infinite_loop"
CONFLICT_DUPLICATE_FLOW = "duplicate_flow"
CONFLICT_UNAUTHORIZED = "unauthorized_transfer"
CONFLICT_TYPE_MISMATCH = "type_mismatch"
CONFLICT_ORPHAN_SOURCE = "orphan_source"

ALL_CONFLICT_TYPES = (
    CONFLICT_MISSING_PATH, CONFLICT_INFINITE_LOOP, CONFLICT_DUPLICATE_FLOW,
    CONFLICT_UNAUTHORIZED, CONFLICT_TYPE_MISMATCH, CONFLICT_ORPHAN_SOURCE,
)

RULE_NO_CRITICAL_CONFLICTS = "no_critical_conflicts"
RULE_NO_LOOPS = "no_infinite_loops"
RULE_ALL_PATHS_COMPLETE = "all_paths_complete"
RULE_NO_UNAUTHORIZED = "no_unauthorized_transfers"
RULE_ARCHITECTURE_COMPLETE = "architecture_complete"
RULE_SUFFICIENT_CONFIDENCE = "sufficient_confidence"

ALL_QUALITY_RULES = (
    RULE_NO_CRITICAL_CONFLICTS,
    RULE_NO_LOOPS,
    RULE_ALL_PATHS_COMPLETE,
    RULE_NO_UNAUTHORIZED,
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
class DataSource:
    source_id: str
    name: str
    kind: str = SRC_OTHER
    description: str = ""
    data_types: List[str] = field(default_factory=list)
    sensitivity: str = SENSITIVITY_INTERNAL
    producer_id: str = ""  # component that produces it

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "name": self.name,
            "kind": self.kind,
            "description": self.description,
            "data_types": list(self.data_types),
            "sensitivity": self.sensitivity,
            "producer_id": self.producer_id,
        }


@dataclass
class DataDestination:
    destination_id: str
    name: str
    description: str = ""
    consumer_id: str = ""
    accepted_types: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "destination_id": self.destination_id,
            "name": self.name,
            "description": self.description,
            "consumer_id": self.consumer_id,
            "accepted_types": list(self.accepted_types),
        }


@dataclass
class TransformationStep:
    step_id: str
    kind: str = XFORM_OTHER
    description: str = ""
    component_id: str = ""
    input_type: str = ""
    output_type: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "kind": self.kind,
            "description": self.description,
            "component_id": self.component_id,
            "input_type": self.input_type,
            "output_type": self.output_type,
        }


@dataclass
class DataFlowPath:
    path_id: str
    name: str
    source_id: str
    destination_id: str
    steps: List[str] = field(default_factory=list)  # ordered component/step ids
    transformations: List[TransformationStep] = field(default_factory=list)
    sensitivity: str = SENSITIVITY_INTERNAL
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path_id": self.path_id,
            "name": self.name,
            "source_id": self.source_id,
            "destination_id": self.destination_id,
            "steps": list(self.steps),
            "transformations": [t.to_dict() for t in self.transformations],
            "sensitivity": self.sensitivity,
            "description": self.description,
        }


@dataclass
class ValidationRule:
    rule_id: str
    description: str
    applies_to: str = ""  # source/path/destination id
    check: str = ""       # completeness / format / type / range

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "description": self.description,
            "applies_to": self.applies_to,
            "check": self.check,
        }


@dataclass
class SecurityRule:
    rule_id: str
    description: str
    sensitivity: str = SENSITIVITY_SENSITIVE
    action: str = "restrict"  # restrict / encrypt / mask / audit
    applies_to: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "description": self.description,
            "sensitivity": self.sensitivity,
            "action": self.action,
            "applies_to": list(self.applies_to),
        }


@dataclass
class ErrorFlow:
    error_id: str
    name: str
    origin_path_id: str = ""
    handler_component_id: str = ""
    propagation: str = "stop"  # stop / bubble / convert
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_id": self.error_id,
            "name": self.name,
            "origin_path_id": self.origin_path_id,
            "handler_component_id": self.handler_component_id,
            "propagation": self.propagation,
            "description": self.description,
        }


@dataclass
class DataFlowConflict:
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
class DataFlowFinding:
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
class DataFlowProvenance:
    engine_name: str = "data_flow_planning"
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
class DataFlowBlueprint:
    """Complete Data Flow Blueprint."""

    blueprint_id: str = ""
    sources: List[DataSource] = field(default_factory=list)
    destinations: List[DataDestination] = field(default_factory=list)
    paths: List[DataFlowPath] = field(default_factory=list)
    validation_rules: List[ValidationRule] = field(default_factory=list)
    security_rules: List[SecurityRule] = field(default_factory=list)
    error_flows: List[ErrorFlow] = field(default_factory=list)
    conflicts: List[DataFlowConflict] = field(default_factory=list)
    findings: List[DataFlowFinding] = field(default_factory=list)
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: DataFlowProvenance = field(default_factory=DataFlowProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "blueprint_id": self.blueprint_id,
            "sources": [s.to_dict() for s in self.sources],
            "destinations": [d.to_dict() for d in self.destinations],
            "paths": [p.to_dict() for p in self.paths],
            "validation_rules": [v.to_dict() for v in self.validation_rules],
            "security_rules": [s.to_dict() for s in self.security_rules],
            "error_flows": [e.to_dict() for e in self.error_flows],
            "conflicts": [c.to_dict() for c in self.conflicts],
            "findings": [f.to_dict() for f in self.findings],
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_EXECUTION_PLAN", "SOURCE_PROJECT_STRUCTURE", "SOURCE_MODULE_ARCHITECTURE",
    "SOURCE_COMPONENT_ARCHITECTURE", "SOURCE_INTERFACE_CONTRACT", "SOURCE_NORMALIZED_REQUIREMENTS",
    "ALL_SOURCES",
    "SRC_USER_INPUT", "SRC_TELEGRAM_UPDATE", "SRC_CONFIG", "SRC_ENV", "SRC_EXTERNAL_API",
    "SRC_DATABASE", "SRC_CACHE", "SRC_IMPORT", "SRC_KNOWLEDGE", "SRC_OTHER", "ALL_SRC_KINDS",
    "XFORM_CLEAN", "XFORM_CONVERT", "XFORM_NORMALIZE", "XFORM_VALIDATE", "XFORM_FILTER",
    "XFORM_ENCRYPT", "XFORM_DECRYPT", "XFORM_OTHER",
    "SENSITIVITY_PUBLIC", "SENSITIVITY_INTERNAL", "SENSITIVITY_SENSITIVE", "SENSITIVITY_SECRET",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW",
    "CONFLICT_MISSING_PATH", "CONFLICT_INFINITE_LOOP", "CONFLICT_DUPLICATE_FLOW",
    "CONFLICT_UNAUTHORIZED", "CONFLICT_TYPE_MISMATCH", "CONFLICT_ORPHAN_SOURCE",
    "ALL_CONFLICT_TYPES",
    "RULE_NO_CRITICAL_CONFLICTS", "RULE_NO_LOOPS", "RULE_ALL_PATHS_COMPLETE",
    "RULE_NO_UNAUTHORIZED", "RULE_ARCHITECTURE_COMPLETE", "RULE_SUFFICIENT_CONFIDENCE",
    "ALL_QUALITY_RULES",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "DataSource", "DataDestination", "TransformationStep", "DataFlowPath",
    "ValidationRule", "SecurityRule", "ErrorFlow",
    "DataFlowConflict", "DataFlowFinding", "CacheInfo", "DataFlowProvenance",
    "DataFlowBlueprint",
]
