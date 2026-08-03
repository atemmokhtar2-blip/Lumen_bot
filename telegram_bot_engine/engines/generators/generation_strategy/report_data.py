"""
Generation Strategy Blueprint data model (Specification 026).

Builds the complete strategy for generating the project before any file is written.
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
SOURCE_RESOURCE_DEPENDENCY = "resource_dependency_blueprint"

ALL_SOURCES = (
    SOURCE_EXECUTION_PLAN,
    SOURCE_PROJECT_STRUCTURE,
    SOURCE_MODULE_ARCHITECTURE,
    SOURCE_COMPONENT_ARCHITECTURE,
    SOURCE_INTERFACE_CONTRACT,
    SOURCE_DATA_FLOW,
    SOURCE_RESOURCE_DEPENDENCY,
)

STAGE_FOUNDATION = "foundation"
STAGE_CORE = "core"
STAGE_FEATURES = "features"
STAGE_INTEGRATION = "integration"
STAGE_CONFIGURATION = "configuration"
STAGE_TESTING = "testing"
STAGE_DOCUMENTATION = "documentation"

ALL_STAGES = (
    STAGE_FOUNDATION, STAGE_CORE, STAGE_FEATURES, STAGE_INTEGRATION,
    STAGE_CONFIGURATION, STAGE_TESTING, STAGE_DOCUMENTATION,
)

ITEM_FOLDER = "folder"
ITEM_FILE = "file"
ITEM_MODULE = "module"
ITEM_COMPONENT = "component"
ITEM_INTERFACE = "interface"
ITEM_CONFIG = "config"
ITEM_TEST = "test"
ITEM_DOC = "documentation"

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

CONFLICT_ORDER = "order_violation"
CONFLICT_MISSING_STAGE = "missing_stage"
CONFLICT_DUPLICATE_ITEM = "duplicate_item"
CONFLICT_ORPHAN = "orphan_item"

ALL_CONFLICT_TYPES = (
    CONFLICT_ORDER, CONFLICT_MISSING_STAGE, CONFLICT_DUPLICATE_ITEM, CONFLICT_ORPHAN,
)

RULE_NO_CRITICAL_CONFLICTS = "no_critical_conflicts"
RULE_ALL_STAGES_PRESENT = "all_stages_present"
RULE_ORDER_VALID = "order_valid"
RULE_NO_EMPTY_FILES = "no_empty_file_plan"
RULE_ARCHITECTURE_COMPLETE = "architecture_complete"
RULE_SUFFICIENT_CONFIDENCE = "sufficient_confidence"

ALL_QUALITY_RULES = (
    RULE_NO_CRITICAL_CONFLICTS,
    RULE_ALL_STAGES_PRESENT,
    RULE_ORDER_VALID,
    RULE_NO_EMPTY_FILES,
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
class GenerationItem:
    item_id: str
    name: str
    item_type: str = ITEM_FILE
    stage: str = STAGE_FOUNDATION
    depends_on: List[str] = field(default_factory=list)
    order: int = 0
    path: str = ""
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "name": self.name,
            "item_type": self.item_type,
            "stage": self.stage,
            "depends_on": list(self.depends_on),
            "order": self.order,
            "path": self.path,
            "description": self.description,
        }


@dataclass
class GenerationStage:
    stage_id: str
    name: str
    order: int = 0
    description: str = ""
    item_ids: List[str] = field(default_factory=list)
    prerequisites: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "name": self.name,
            "order": self.order,
            "description": self.description,
            "item_ids": list(self.item_ids),
            "prerequisites": list(self.prerequisites),
        }


@dataclass
class GenerationRule:
    rule_id: str
    description: str
    enforced: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "description": self.description,
            "enforced": self.enforced,
        }


@dataclass
class RollbackPoint:
    point_id: str
    after_stage: str
    description: str = ""
    restore_actions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "point_id": self.point_id,
            "after_stage": self.after_stage,
            "description": self.description,
            "restore_actions": list(self.restore_actions),
        }


@dataclass
class OptimizationStep:
    step_id: str
    description: str
    benefit: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "description": self.description,
            "benefit": self.benefit,
        }


@dataclass
class StrategyConflict:
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
class StrategyFinding:
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
class StrategyProvenance:
    engine_name: str = "generation_strategy"
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
class GenerationStrategyBlueprint:
    """Complete Generation Strategy Blueprint."""

    blueprint_id: str = ""
    stages: List[GenerationStage] = field(default_factory=list)
    items: List[GenerationItem] = field(default_factory=list)
    generation_order: List[str] = field(default_factory=list)
    rules: List[GenerationRule] = field(default_factory=list)
    rollback_points: List[RollbackPoint] = field(default_factory=list)
    optimizations: List[OptimizationStep] = field(default_factory=list)
    conflicts: List[StrategyConflict] = field(default_factory=list)
    findings: List[StrategyFinding] = field(default_factory=list)
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: StrategyProvenance = field(default_factory=StrategyProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "blueprint_id": self.blueprint_id,
            "stages": [s.to_dict() for s in self.stages],
            "items": [i.to_dict() for i in self.items],
            "generation_order": list(self.generation_order),
            "rules": [r.to_dict() for r in self.rules],
            "rollback_points": [r.to_dict() for r in self.rollback_points],
            "optimizations": [o.to_dict() for o in self.optimizations],
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
    "SOURCE_COMPONENT_ARCHITECTURE", "SOURCE_INTERFACE_CONTRACT", "SOURCE_DATA_FLOW",
    "SOURCE_RESOURCE_DEPENDENCY", "ALL_SOURCES",
    "STAGE_FOUNDATION", "STAGE_CORE", "STAGE_FEATURES", "STAGE_INTEGRATION",
    "STAGE_CONFIGURATION", "STAGE_TESTING", "STAGE_DOCUMENTATION", "ALL_STAGES",
    "ITEM_FOLDER", "ITEM_FILE", "ITEM_MODULE", "ITEM_COMPONENT", "ITEM_INTERFACE",
    "ITEM_CONFIG", "ITEM_TEST", "ITEM_DOC",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW",
    "CONFLICT_ORDER", "CONFLICT_MISSING_STAGE", "CONFLICT_DUPLICATE_ITEM", "CONFLICT_ORPHAN",
    "ALL_CONFLICT_TYPES",
    "RULE_NO_CRITICAL_CONFLICTS", "RULE_ALL_STAGES_PRESENT", "RULE_ORDER_VALID",
    "RULE_NO_EMPTY_FILES", "RULE_ARCHITECTURE_COMPLETE", "RULE_SUFFICIENT_CONFIDENCE",
    "ALL_QUALITY_RULES",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "GenerationItem", "GenerationStage", "GenerationRule", "RollbackPoint",
    "OptimizationStep", "StrategyConflict", "StrategyFinding",
    "CacheInfo", "StrategyProvenance", "GenerationStrategyBlueprint",
]
