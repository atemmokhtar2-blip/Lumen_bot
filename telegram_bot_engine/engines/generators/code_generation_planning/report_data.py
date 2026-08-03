"""
Intelligent Code Generation Plan data model (Specification 029 v2.0).

Last planning engine before actual code writing. Builds a complete intelligent
plan: context, units, adaptive queue, rules, style, simulation, rollback, score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


SOURCE_READINESS = "generation_readiness_report"
SOURCE_EXECUTION_PLAN = "execution_plan"
SOURCE_PROJECT_STRUCTURE = "project_structure_blueprint"
SOURCE_MODULE_ARCHITECTURE = "module_architecture_blueprint"
SOURCE_COMPONENT_ARCHITECTURE = "component_architecture_blueprint"
SOURCE_INTERFACE_CONTRACT = "interface_contract_blueprint"
SOURCE_RESOURCE_DEPENDENCY = "resource_dependency_blueprint"
SOURCE_GENERATION_STRATEGY = "generation_strategy_blueprint"
SOURCE_SESSION = "generation_session_report"

ALL_SOURCES = (
    SOURCE_READINESS,
    SOURCE_EXECUTION_PLAN,
    SOURCE_PROJECT_STRUCTURE,
    SOURCE_MODULE_ARCHITECTURE,
    SOURCE_COMPONENT_ARCHITECTURE,
    SOURCE_INTERFACE_CONTRACT,
    SOURCE_RESOURCE_DEPENDENCY,
    SOURCE_GENERATION_STRATEGY,
    SOURCE_SESSION,
)

UNIT_FILE = "file"
UNIT_CLASS = "class"
UNIT_FUNCTION = "function"
UNIT_INTERFACE = "interface"
UNIT_CONFIG = "config"
UNIT_TEST = "test"
UNIT_CONSTANT = "constant"
UNIT_RESOURCE = "resource"
UNIT_DOC = "documentation"

ALL_UNIT_KINDS = (
    UNIT_FILE, UNIT_CLASS, UNIT_FUNCTION, UNIT_INTERFACE,
    UNIT_CONFIG, UNIT_TEST, UNIT_CONSTANT, UNIT_RESOURCE, UNIT_DOC,
)

RULE_CLEAN_CODE = "clean_code"
RULE_SOLID = "solid"
RULE_DRY = "dry"
RULE_KISS = "kiss"
RULE_YAGNI = "yagni"
RULE_CLEAN_ARCH = "clean_architecture"
RULE_LAYER_SEP = "layer_separation"
RULE_DI = "dependency_injection"
RULE_NAMING = "naming_convention"
RULE_ERROR_HANDLING = "error_handling"
RULE_LOGGING = "logging"
RULE_DOCS = "documentation"
RULE_TESTING = "testing"
RULE_SECURITY = "security"
RULE_PERFORMANCE = "performance"

ALL_GEN_RULES = (
    RULE_CLEAN_CODE, RULE_SOLID, RULE_DRY, RULE_KISS, RULE_YAGNI,
    RULE_CLEAN_ARCH, RULE_LAYER_SEP, RULE_DI, RULE_NAMING,
    RULE_ERROR_HANDLING, RULE_LOGGING, RULE_DOCS, RULE_TESTING,
    RULE_SECURITY, RULE_PERFORMANCE,
)

SCORE_MAINTAINABILITY = "maintainability"
SCORE_SCALABILITY = "scalability"
SCORE_SECURITY = "security"
SCORE_PERFORMANCE = "performance"
SCORE_COMPLEXITY = "complexity"
SCORE_RELIABILITY = "reliability"
SCORE_ARCHITECTURE = "architecture_quality"

ALL_SCORE_DIMS = (
    SCORE_MAINTAINABILITY, SCORE_SCALABILITY, SCORE_SECURITY,
    SCORE_PERFORMANCE, SCORE_COMPLEXITY, SCORE_RELIABILITY, SCORE_ARCHITECTURE,
)

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

CONFLICT_ORDER = "order_violation"
CONFLICT_MISSING_DEP = "missing_dependency"
CONFLICT_CIRCULAR = "circular_dependency"
CONFLICT_DUPLICATE = "duplicate_unit"
CONFLICT_EMPTY = "empty_unit"
CONFLICT_SIMULATION = "simulation_failure"

ALL_CONFLICT_TYPES = (
    CONFLICT_ORDER, CONFLICT_MISSING_DEP, CONFLICT_CIRCULAR,
    CONFLICT_DUPLICATE, CONFLICT_EMPTY, CONFLICT_SIMULATION,
)

RULE_QUEUE_COMPLETE = "queue_complete"
RULE_NO_CIRCULARS = "no_circulars"
RULE_NO_ORDER_VIOLATIONS = "no_order_violations"
RULE_SIMULATION_PASSED = "simulation_passed"
RULE_SCORE_ADEQUATE = "score_adequate"
RULE_SUFFICIENT_CONFIDENCE = "sufficient_confidence"

ALL_QUALITY_RULES = (
    RULE_QUEUE_COMPLETE,
    RULE_NO_CIRCULARS,
    RULE_NO_ORDER_VIOLATIONS,
    RULE_SIMULATION_PASSED,
    RULE_SCORE_ADEQUATE,
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

MIN_INTELLIGENCE_SCORE = 70.0

VERDICT_READY = "ready"
VERDICT_READY_WITH_WARNINGS = "ready_with_warnings"
VERDICT_NOT_READY = "not_ready"

ALL_VERDICTS = (VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY)


@dataclass
class GenerationContext:
    """Full context injected into every generation unit."""

    project_goal: str = ""
    modules: List[str] = field(default_factory=list)
    components: List[str] = field(default_factory=list)
    interfaces: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    prior_files: List[str] = field(default_factory=list)
    upcoming_files: List[str] = field(default_factory=list)
    architecture_style: str = ""
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_goal": self.project_goal,
            "modules": list(self.modules),
            "components": list(self.components),
            "interfaces": list(self.interfaces),
            "dependencies": list(self.dependencies),
            "prior_files": list(self.prior_files),
            "upcoming_files": list(self.upcoming_files),
            "architecture_style": self.architecture_style,
            "notes": self.notes,
        }


@dataclass
class GenerationUnit:
    unit_id: str
    name: str
    kind: str = UNIT_FILE
    path: str = ""
    purpose: str = ""
    responsibility: str = ""
    contents: List[str] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)
    related_files: List[str] = field(default_factory=list)
    order: int = 0
    phase: str = ""
    extension_points: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "name": self.name,
            "kind": self.kind,
            "path": self.path,
            "purpose": self.purpose,
            "responsibility": self.responsibility,
            "contents": list(self.contents),
            "depends_on": list(self.depends_on),
            "related_files": list(self.related_files),
            "order": self.order,
            "phase": self.phase,
            "extension_points": list(self.extension_points),
        }


@dataclass
class QueueEntry:
    entry_id: str
    unit_id: str
    position: int = 0
    waits_for: List[str] = field(default_factory=list)
    estimated_complexity: str = "medium"
    adaptive: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "unit_id": self.unit_id,
            "position": self.position,
            "waits_for": list(self.waits_for),
            "estimated_complexity": self.estimated_complexity,
            "adaptive": self.adaptive,
        }


@dataclass
class GenerationRule:
    rule_id: str
    name: str
    description: str = ""
    enforced: bool = True
    category: str = "general"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "description": self.description,
            "enforced": self.enforced,
            "category": self.category,
        }


@dataclass
class StyleRules:
    project_shape: str = "layered"
    code_style: str = "pep8"
    import_style: str = "isort-compatible"
    class_style: str = "PascalCase"
    function_style: str = "snake_case"
    constant_style: str = "UPPER_SNAKE"
    comment_style: str = "google-docstring"
    file_layout: str = "stdlib / third-party / local"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_shape": self.project_shape,
            "code_style": self.code_style,
            "import_style": self.import_style,
            "class_style": self.class_style,
            "function_style": self.function_style,
            "constant_style": self.constant_style,
            "comment_style": self.comment_style,
            "file_layout": self.file_layout,
        }


@dataclass
class SimulationFinding:
    finding_id: str
    severity: str = SEVERITY_MEDIUM
    message: str = ""
    unit_id: str = ""
    resolution_hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "severity": self.severity,
            "message": self.message,
            "unit_id": self.unit_id,
            "resolution_hint": self.resolution_hint,
        }


@dataclass
class SimulationReport:
    passed: bool = False
    findings: List[SimulationFinding] = field(default_factory=list)
    units_simulated: int = 0
    errors_found: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "findings": [f.to_dict() for f in self.findings],
            "units_simulated": self.units_simulated,
            "errors_found": self.errors_found,
        }


@dataclass
class RollbackPoint:
    point_id: str
    after_unit_id: str
    description: str = ""
    position: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "point_id": self.point_id,
            "after_unit_id": self.after_unit_id,
            "description": self.description,
            "position": self.position,
        }


@dataclass
class IntelligenceScore:
    dimension: str
    score: float = 0.0  # 0–100
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dimension": self.dimension,
            "score": self.score,
            "notes": self.notes,
        }


@dataclass
class PlanConflict:
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
class PlanFinding:
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
class PlanProvenance:
    engine_name: str = "code_generation_planning"
    engine_version: str = "2.0.0"
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
class IntelligentCodeGenerationPlan:
    """Complete Intelligent Code Generation Plan (Spec 029 v2.0)."""

    plan_id: str = ""
    context: GenerationContext = field(default_factory=GenerationContext)
    units: List[GenerationUnit] = field(default_factory=list)
    queue: List[QueueEntry] = field(default_factory=list)
    generation_order: List[str] = field(default_factory=list)
    rules: List[GenerationRule] = field(default_factory=list)
    style: StyleRules = field(default_factory=StyleRules)
    simulation: SimulationReport = field(default_factory=SimulationReport)
    rollback_points: List[RollbackPoint] = field(default_factory=list)
    intelligence_scores: List[IntelligenceScore] = field(default_factory=list)
    overall_intelligence_score: float = 0.0
    conflicts: List[PlanConflict] = field(default_factory=list)
    findings: List[PlanFinding] = field(default_factory=list)
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: PlanProvenance = field(default_factory=PlanProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "context": self.context.to_dict(),
            "units": [u.to_dict() for u in self.units],
            "queue": [q.to_dict() for q in self.queue],
            "generation_order": list(self.generation_order),
            "rules": [r.to_dict() for r in self.rules],
            "style": self.style.to_dict(),
            "simulation": self.simulation.to_dict(),
            "rollback_points": [r.to_dict() for r in self.rollback_points],
            "intelligence_scores": [s.to_dict() for s in self.intelligence_scores],
            "overall_intelligence_score": self.overall_intelligence_score,
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
    "SOURCE_READINESS", "SOURCE_EXECUTION_PLAN", "SOURCE_PROJECT_STRUCTURE",
    "SOURCE_MODULE_ARCHITECTURE", "SOURCE_COMPONENT_ARCHITECTURE",
    "SOURCE_INTERFACE_CONTRACT", "SOURCE_RESOURCE_DEPENDENCY",
    "SOURCE_GENERATION_STRATEGY", "SOURCE_SESSION", "ALL_SOURCES",
    "UNIT_FILE", "UNIT_CLASS", "UNIT_FUNCTION", "UNIT_INTERFACE",
    "UNIT_CONFIG", "UNIT_TEST", "UNIT_CONSTANT", "UNIT_RESOURCE", "UNIT_DOC",
    "ALL_UNIT_KINDS",
    "RULE_CLEAN_CODE", "RULE_SOLID", "RULE_DRY", "RULE_KISS", "RULE_YAGNI",
    "RULE_CLEAN_ARCH", "RULE_LAYER_SEP", "RULE_DI", "RULE_NAMING",
    "RULE_ERROR_HANDLING", "RULE_LOGGING", "RULE_DOCS", "RULE_TESTING",
    "RULE_SECURITY", "RULE_PERFORMANCE", "ALL_GEN_RULES",
    "SCORE_MAINTAINABILITY", "SCORE_SCALABILITY", "SCORE_SECURITY",
    "SCORE_PERFORMANCE", "SCORE_COMPLEXITY", "SCORE_RELIABILITY",
    "SCORE_ARCHITECTURE", "ALL_SCORE_DIMS",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW",
    "CONFLICT_ORDER", "CONFLICT_MISSING_DEP", "CONFLICT_CIRCULAR",
    "CONFLICT_DUPLICATE", "CONFLICT_EMPTY", "CONFLICT_SIMULATION",
    "ALL_CONFLICT_TYPES",
    "RULE_QUEUE_COMPLETE", "RULE_NO_CIRCULARS", "RULE_NO_ORDER_VIOLATIONS",
    "RULE_SIMULATION_PASSED", "RULE_SCORE_ADEQUATE", "RULE_SUFFICIENT_CONFIDENCE",
    "ALL_QUALITY_RULES",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "MIN_INTELLIGENCE_SCORE",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "GenerationContext", "GenerationUnit", "QueueEntry", "GenerationRule",
    "StyleRules", "SimulationFinding", "SimulationReport", "RollbackPoint",
    "IntelligenceScore", "PlanConflict", "PlanFinding",
    "CacheInfo", "PlanProvenance", "IntelligentCodeGenerationPlan",
]
