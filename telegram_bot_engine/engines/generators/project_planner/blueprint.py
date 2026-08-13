"""
Project Blueprint \u2014 the formal plan produced by the Project Planning
Engine (Specification 004).

The :class:`ProjectBlueprint` is the **single, authoritative** plan for
building a Telegram bot.  Every generation engine that runs after the
Project Planning Engine must read this blueprint instead of the raw
request or the analysis report.

The blueprint is the product of the Project Planning Engine.  It is
**read-only** for all downstream engines \u2014 no engine may modify it
directly.  Any future modification must go through a dedicated engine.

The blueprint aggregates several sub-models, each with a single
responsibility:

* :class:`ProjectBlueprint` \u2014 the root container.
* :class:`ProjectIdentity` \u2014 name, type, language, libraries,
  database.
* :class:`ExpectedStructure` \u2014 the expected folder/file layout.
* :class:`FeatureUnit` \u2014 a single feature broken down into an
  independent planning unit (see :mod:`.feature_unit`).
* :class:`InternalComponent` \u2014 a single internal component with a
  priority.
* :class:`ComponentRelationship` \u2014 a relationship between two
  components.
* :class:`RequiredEngine` \u2014 a generator engine that must run.
* :class:`DependencyGraph` \u2014 the full dependency map (see
  :mod:`.dependency_graph`).
* :class:`ExecutionPlan` \u2014 the phased execution plan (see
  :mod:`.execution_plan`).

This module re-exports the heavy sub-models from their own modules so
that callers can import everything from one place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .feature_unit import FeatureUnit
from .dependency_graph import DependencyGraph, DependencyNode
from .execution_plan import (
    ExecutionPlan,
    ExecutionPhase,
    PhaseStatus,
    DEFAULT_PHASES,
)


# ---------------------------------------------------------------------------
# Project identity
# ---------------------------------------------------------------------------

@dataclass
class ProjectIdentity:
    """High-level identity of the project being planned.

    Attributes:
        name: The project name (machine-friendly slug).
        display_name: The human-readable project name.
        bot_type: The detected bot type (e.g. ``"store"``,
            ``"group_admin"``, ``"ai_assistant"``).
        language: The programming language (default ``"python"``).
        language_version: The language version (e.g. ``"3.11"``).
        framework: The Telegram bot framework (e.g.
            ``"python-telegram-bot"``).
        libraries: The list of required libraries (with versions when
            known).
        database: The chosen database backend (e.g. ``"sqlite"``,
            ``"postgres"``) or empty string when no database is needed.
    """

    name: str = ""
    display_name: str = ""
    bot_type: str = "general"
    language: str = "python"
    language_version: str = "3.11"
    framework: str = "python-telegram-bot"
    libraries: List[str] = field(default_factory=list)
    database: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "bot_type": self.bot_type,
            "language": self.language,
            "language_version": self.language_version,
            "framework": self.framework,
            "libraries": list(self.libraries),
            "database": self.database,
        }


# ---------------------------------------------------------------------------
# Expected project structure
# ---------------------------------------------------------------------------

@dataclass
class StructureEntry:
    """A single entry in the expected project structure.

    Attributes:
        path: The relative path within the project (e.g.
            ``"src/handlers/"``, ``"main.py"``).
        kind: ``"directory"`` or ``"file"``.
        description: What this entry is for.
    """

    path: str
    kind: str = "file"  # "directory" | "file"
    description: str = ""


@dataclass
class ExpectedStructure:
    """The expected folder/file layout of the generated project.

    Attributes:
        root: The root package name (e.g. ``"my_store_bot"``).
        entries: The ordered list of :class:`StructureEntry` objects.
    """

    root: str = ""
    entries: List[StructureEntry] = field(default_factory=list)

    def directories(self) -> List[StructureEntry]:
        return [e for e in self.entries if e.kind == "directory"]

    def files(self) -> List[StructureEntry]:
        return [e for e in self.entries if e.kind == "file"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "root": self.root,
            "entries": [
                {"path": e.path, "kind": e.kind, "description": e.description}
                for e in self.entries
            ],
        }


# ---------------------------------------------------------------------------
# Internal components
# ---------------------------------------------------------------------------

@dataclass
class InternalComponent:
    """A single internal component of the project.

    Attributes:
        name: The component name (e.g. ``"database"``,
            ``"admin_panel"``, ``"logger"``).
        display_name: The human-readable name.
        kind: The component kind (``"feature"``, ``"infrastructure"``,
            ``"integration"``).
        priority: Build priority.  Lower values are built first.
        description: What the component does.
        source_feature: The feature unit this component was derived
            from, if any.
        dependencies: The names of other components this one depends
            on.
    """

    name: str
    display_name: str = ""
    kind: str = "feature"
    priority: int = 100
    description: str = ""
    source_feature: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "kind": self.kind,
            "priority": self.priority,
            "description": self.description,
            "source_feature": self.source_feature,
            "dependencies": list(self.dependencies),
        }


@dataclass
class ComponentRelationship:
    """A relationship between two internal components.

    Attributes:
        source: The source component name.
        target: The target component name.
        kind: The relationship kind (``"depends_on"``, ``"uses"``,
            ``"managed_by"``, ``"stored_in"``, ``"calls"``).
        description: Human-readable description.
    """

    source: str
    target: str
    kind: str = "depends_on"
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "kind": self.kind,
            "description": self.description,
        }


# ---------------------------------------------------------------------------
# Required generation engines
# ---------------------------------------------------------------------------

@dataclass
class RequiredEngine:
    """A generation engine that must run to build this project.

    Attributes:
        engine_id: The engine identifier (matches the manager's ID).
        name: The human-readable engine name.
        purpose: What this engine will produce.
        phase: The execution phase this engine belongs to.
        priority: Run priority within the phase.
    """

    engine_id: str
    name: str = ""
    purpose: str = ""
    phase: str = ""
    priority: int = 100

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "name": self.name,
            "purpose": self.purpose,
            "phase": self.phase,
            "priority": self.priority,
        }


# ---------------------------------------------------------------------------
# Risk and validation summary
# ---------------------------------------------------------------------------

@dataclass
class BlueprintRisk:
    """A risk detected in the plan before it is finalised.

    Attributes:
        kind: ``"conflict"``, ``"missing"``, ``"missing_phase"``,
            ``"incomplete_dependency"``.
        description: What the risk is.
        severity: ``"error"`` or ``"warning"``.
        affected: The component/feature/phase affected.
        resolution_hint: A suggested way to resolve the risk.
    """

    kind: str
    description: str
    severity: str = "warning"
    affected: str = ""
    resolution_hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "description": self.description,
            "severity": self.severity,
            "affected": self.affected,
            "resolution_hint": self.resolution_hint,
        }


@dataclass
class BlueprintValidation:
    """The validation verdict for the blueprint.

    The plan is **not adopted** unless ``valid`` is ``True``.  The
    three required conditions are:

    1. All features are connected (each feature is reachable from the
       dependency graph).
    2. All dependencies are valid (no dangling references, no cycles).
    3. All execution phases are complete (every phase has at least one
       task and the phases are contiguous).

    Attributes:
        valid: ``True`` when the blueprint passed all checks.
        all_features_connected: Result of the feature-connection check.
        dependencies_valid: Result of the dependency-validity check.
        phases_complete: Result of the phase-completeness check.
        errors: Error messages from failed checks.
        warnings: Warning messages.
    """

    valid: bool = False
    all_features_connected: bool = False
    dependencies_valid: bool = False
    phases_complete: bool = False
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "all_features_connected": self.all_features_connected,
            "dependencies_valid": self.dependencies_valid,
            "phases_complete": self.phases_complete,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


# ---------------------------------------------------------------------------
# Root container
# ---------------------------------------------------------------------------

@dataclass
class ProjectBlueprint:
    """The complete, authoritative plan for building a Telegram bot.

    This is the **only** object downstream generation engines should
    read.  It is produced by the :class:`ProjectPlanningEngine` from the
    :class:`~telegram_bot_engine.engines.generators.analyzer.AnalysisReport`
    \u2014 it never reads the raw user request.

    The blueprint is **immutable in spirit**: no downstream engine may
    modify it directly.  Any modification requires a dedicated engine.

    Attributes:
        identity: The :class:`ProjectIdentity`.
        structure: The :class:`ExpectedStructure`.
        features: The list of :class:`FeatureUnit` objects (one per
            feature, broken down into independent units).
        components: The list of :class:`InternalComponent` objects.
        relationships: The :class:`ComponentRelationship` objects.
        required_engines: The :class:`RequiredEngine` objects.
        dependency_graph: The :class:`DependencyGraph`.
        execution_plan: The :class:`ExecutionPlan`.
        risks: The :class:`BlueprintRisk` objects detected before
            finalising.
        validation: The :class:`BlueprintValidation` verdict.
        ready: ``True`` when the blueprint is valid and ready to drive
            generation.
        notes: General planning notes.
        warnings: Planning warnings.
    """

    identity: ProjectIdentity = field(default_factory=ProjectIdentity)
    structure: ExpectedStructure = field(default_factory=ExpectedStructure)
    features: List[FeatureUnit] = field(default_factory=list)
    components: List[InternalComponent] = field(default_factory=list)
    relationships: List[ComponentRelationship] = field(default_factory=list)
    required_engines: List[RequiredEngine] = field(default_factory=list)
    dependency_graph: DependencyGraph = field(default_factory=DependencyGraph)
    execution_plan: ExecutionPlan = field(default_factory=ExecutionPlan)
    risks: List[BlueprintRisk] = field(default_factory=list)
    validation: BlueprintValidation = field(default_factory=BlueprintValidation)
    ready: bool = False
    notes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # -- convenience -------------------------------------------------------

    @property
    def is_valid(self) -> bool:
        """``True`` when the blueprint passed validation."""
        return self.validation.valid

    @property
    def has_errors(self) -> bool:
        return any(r.severity == "error" for r in self.risks)

    @property
    def feature_names(self) -> List[str]:
        return [f.name for f in self.features]

    @property
    def component_names(self) -> List[str]:
        return [c.name for c in self.components]

    def get_component(self, name: str) -> Optional[InternalComponent]:
        for c in self.components:
            if c.name == name:
                return c
        return None

    def get_feature(self, name: str) -> Optional[FeatureUnit]:
        for f in self.features:
            if f.name == name:
                return f
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain-dict representation for serialisation."""
        return {
            "identity": self.identity.to_dict(),
            "structure": self.structure.to_dict(),
            "features": [f.to_dict() for f in self.features],
            "components": [c.to_dict() for c in self.components],
            "relationships": [r.to_dict() for r in self.relationships],
            "required_engines": [e.to_dict() for e in self.required_engines],
            "dependency_graph": self.dependency_graph.to_dict(),
            "execution_plan": self.execution_plan.to_dict(),
            "risks": [r.to_dict() for r in self.risks],
            "validation": self.validation.to_dict(),
            "ready": self.ready,
            "notes": list(self.notes),
            "warnings": list(self.warnings),
        }


__all__ = [
    "ProjectBlueprint",
    "ProjectIdentity",
    "ExpectedStructure",
    "StructureEntry",
    "InternalComponent",
    "ComponentRelationship",
    "RequiredEngine",
    "BlueprintRisk",
    "BlueprintValidation",
    # re-exported from sub-modules
    "FeatureUnit",
    "DependencyGraph",
    "DependencyNode",
    "ExecutionPlan",
    "ExecutionPhase",
    "PhaseStatus",
    "DEFAULT_PHASES",
]
