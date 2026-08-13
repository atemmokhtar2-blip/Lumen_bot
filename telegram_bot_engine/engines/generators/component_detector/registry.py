"""
Component Registry \u2014 the data model for the output of the Component
Detection Engine (Specification 007).

The :class:`ComponentRegistry` is the **complete, authoritative** list
of every software component the generated Telegram bot project will
contain.  It is the single artefact that tells every downstream code
generator *which* components exist, *where* they live, *what* they are
responsible for, and *in what order* they must be built.

The registry is built by the
:class:`~telegram_bot_engine.engines.generators.component_detector.ComponentDetectionEngine`
from three read-only artefacts:

1. the ``project_blueprint`` (produced by the Project Planning Engine),
2. the ``blueprint_validation_report`` (produced by the Blueprint
   Validator Engine),
3. the ``project_structure_map`` (produced by the Structure Generation
   Engine).

The engine is **forbidden** from reading the user's request.

Design principles
-----------------
* **Every component is known before code is written.**  No component is
  invented during code generation \u2014 they are all detected here.
* **One responsibility per component.**  Each detected component carries
  a single, clear responsibility (Single Responsibility Principle).
* **No duplicates.**  The engine detects and merges components that
  perform the same function.
* **No unused components.**  Every detected component must be referenced
  by at least one other component or by the project entry point.
* **No circular dependencies.**  The registry records a dependency graph
  and rejects cycles.
* **Scalable and reusable.**  Components are described generically so
  they can be reused across projects.

The registry is a plain data container \u2014 no logic lives here.  The
detection engine and its helpers populate it; downstream consumers (the
code generators, the manager, tests) read it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------#
# Component-type constants
# ---------------------------------------------------------------------------#
#
# The set of component types the detection engine recognises.  These are
# the *software* component types \u2014 the roles a piece of code plays in
# the generated bot \u2014 not the InternalComponent kinds from the
# blueprint (which classify features vs. infrastructure).
#
# A single blueprint InternalComponent may map to several software
# components.  For example, a "store" feature component yields a Command
# handler, a Callback handler, a Service, a Repository, and a Database
# Model.

COMPONENT_TYPE_COMMAND = "command"
COMPONENT_TYPE_HANDLER = "handler"
COMPONENT_TYPE_ROUTER = "router"
COMPONENT_TYPE_SERVICE = "service"
COMPONENT_TYPE_MANAGER = "manager"
COMPONENT_TYPE_MIDDLEWARE = "middleware"
COMPONENT_TYPE_FILTER = "filter"
COMPONENT_TYPE_DECORATOR = "decorator"
COMPONENT_TYPE_UTILITY = "utility"
COMPONENT_TYPE_CONFIGURATION = "configuration"
COMPONENT_TYPE_ENVIRONMENT = "environment"
COMPONENT_TYPE_DATABASE_MODEL = "database_model"
COMPONENT_TYPE_REPOSITORY = "repository"
COMPONENT_TYPE_VALIDATOR = "validator"
COMPONENT_TYPE_KEYBOARD_BUILDER = "keyboard_builder"
COMPONENT_TYPE_MESSAGE_BUILDER = "message_builder"
COMPONENT_TYPE_CALLBACK_HANDLER = "callback_handler"
COMPONENT_TYPE_API_CLIENT = "api_client"
COMPONENT_TYPE_SCHEDULER = "scheduler"
COMPONENT_TYPE_BACKGROUND_TASK = "background_task"
COMPONENT_TYPE_CACHE_LAYER = "cache_layer"
COMPONENT_TYPE_LOCALIZATION = "localization"
COMPONENT_TYPE_LOGGING_SYSTEM = "logging_system"
COMPONENT_TYPE_PLUGIN = "plugin"
COMPONENT_TYPE_EXTENSION = "extension"
COMPONENT_TYPE_APPLICATION = "application"
COMPONENT_TYPE_SESSION = "session"

ALL_COMPONENT_TYPES = (
    COMPONENT_TYPE_COMMAND,
    COMPONENT_TYPE_HANDLER,
    COMPONENT_TYPE_ROUTER,
    COMPONENT_TYPE_SERVICE,
    COMPONENT_TYPE_MANAGER,
    COMPONENT_TYPE_MIDDLEWARE,
    COMPONENT_TYPE_FILTER,
    COMPONENT_TYPE_DECORATOR,
    COMPONENT_TYPE_UTILITY,
    COMPONENT_TYPE_CONFIGURATION,
    COMPONENT_TYPE_ENVIRONMENT,
    COMPONENT_TYPE_DATABASE_MODEL,
    COMPONENT_TYPE_REPOSITORY,
    COMPONENT_TYPE_VALIDATOR,
    COMPONENT_TYPE_KEYBOARD_BUILDER,
    COMPONENT_TYPE_MESSAGE_BUILDER,
    COMPONENT_TYPE_CALLBACK_HANDLER,
    COMPONENT_TYPE_API_CLIENT,
    COMPONENT_TYPE_SCHEDULER,
    COMPONENT_TYPE_BACKGROUND_TASK,
    COMPONENT_TYPE_CACHE_LAYER,
    COMPONENT_TYPE_LOCALIZATION,
    COMPONENT_TYPE_LOGGING_SYSTEM,
    COMPONENT_TYPE_PLUGIN,
    COMPONENT_TYPE_EXTENSION,
    COMPONENT_TYPE_APPLICATION,
    COMPONENT_TYPE_SESSION,
)


# ---------------------------------------------------------------------------#
# Importance levels
# ---------------------------------------------------------------------------#

IMPORTANCE_CRITICAL = "critical"
IMPORTANCE_HIGH = "high"
IMPORTANCE_NORMAL = "normal"
IMPORTANCE_LOW = "low"

ALL_IMPORTANCE_LEVELS = (
    IMPORTANCE_CRITICAL,
    IMPORTANCE_HIGH,
    IMPORTANCE_NORMAL,
    IMPORTANCE_LOW,
)

# Numeric importance for sorting and build-order tie-breaking.
_IMPORTANCE_WEIGHT: Dict[str, int] = {
    IMPORTANCE_CRITICAL: 0,
    IMPORTANCE_HIGH: 1,
    IMPORTANCE_NORMAL: 2,
    IMPORTANCE_LOW: 3,
}


# ---------------------------------------------------------------------------#
# A single detected component
# ---------------------------------------------------------------------------#

@dataclass
class DetectedComponent:
    """A single software component detected by the engine.

    This is the unit of the Component Registry.  Each detected component
    describes a piece of software that the code generators must produce
    later \u2014 it is **not** code itself.

    Attributes:
        name: The machine-friendly component name (unique within the
            registry).  e.g. ``"start_command"``,
            ``"product_repository"``, ``"database_session"``.
        type: The component type (one of the ``COMPONENT_TYPE_*``
            constants).  e.g. ``"command"``, ``"repository"``.
        purpose: A short description of what the component is for.
        responsibility: The single, clear responsibility of the
            component (Single Responsibility Principle).  This is the
            *one thing* the component does.
        source_blueprint_component: The name of the
            :class:`InternalComponent` in the blueprint that this
            detected component was derived from, if any.
        source_feature: The name of the :class:`FeatureUnit` this
            component belongs to, if any.
        location: The relative path (file or folder) within the project
            where this component will live.  e.g.
            ``"my_bot/handlers/start.py"``.
        building_engine: The engine that will build this component
            later (e.g. ``"code_generator"``, ``"database_engine"``).
        depends_on: The names of other detected components this one
            depends on.
        depended_by: The names of detected components that depend on
            this one.
        build_order: The position in the build sequence (lower first).
        importance: The importance level (one of the ``IMPORTANCE_*``
            constants).
        reusable: ``True`` when the component is generic enough to be
            reused across different projects.
        scalable: ``True`` when the component can be extended without
            restructuring.
        compatible: ``True`` when the component is compatible with the
            project's language, framework, and libraries.
        metadata: Free-form extra information.
    """

    name: str
    type: str = COMPONENT_TYPE_UTILITY
    purpose: str = ""
    responsibility: str = ""
    source_blueprint_component: str = ""
    source_feature: str = ""
    location: str = ""
    building_engine: str = "code_generator"
    depends_on: List[str] = field(default_factory=list)
    depended_by: List[str] = field(default_factory=list)
    build_order: int = 100
    importance: str = IMPORTANCE_NORMAL
    reusable: bool = False
    scalable: bool = True
    compatible: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("DetectedComponent requires a non-empty name.")

    @property
    def importance_weight(self) -> int:
        """Numeric weight for sorting by importance (lower first)."""
        return _IMPORTANCE_WEIGHT.get(self.importance, 2)

    def add_dependency(self, other: str) -> None:
        """Record that this component depends on *other*."""
        if other and other not in self.depends_on:
            self.depends_on.append(other)

    def add_dependent(self, other: str) -> None:
        """Record that *other* depends on this component."""
        if other and other not in self.depended_by:
            self.depended_by.append(other)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "purpose": self.purpose,
            "responsibility": self.responsibility,
            "source_blueprint_component": self.source_blueprint_component,
            "source_feature": self.source_feature,
            "location": self.location,
            "building_engine": self.building_engine,
            "depends_on": list(self.depends_on),
            "depended_by": list(self.depended_by),
            "build_order": self.build_order,
            "importance": self.importance,
            "reusable": self.reusable,
            "scalable": self.scalable,
            "compatible": self.compatible,
            "metadata": dict(self.metadata),
        }


# ---------------------------------------------------------------------------#
# Component relationship
# ---------------------------------------------------------------------------#

@dataclass
class ComponentDependencyEdge:
    """A directed relationship between two detected components.

    The relationship graph is recorded so that downstream engines know
    the wiring between components.  It mirrors the blueprint's
    :class:`ComponentRelationship` but operates at the detected-component
    level.

    Attributes:
        source: The source component name.
        target: The target component name.
        kind: The relationship kind (``"depends_on"``, ``"uses"``,
            ``"calls"``, ``"managed_by"``, ``"stored_in"``).
        description: A human-readable description.
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


# ---------------------------------------------------------------------------#
# Build-order entry
# ---------------------------------------------------------------------------#

@dataclass
class ComponentBuildOrderEntry:
    """A single entry in the component build order.

    Attributes:
        position: The 0-based position in the build sequence.
        component_name: The name of the detected component.
        component_type: The component type.
        building_engine: The engine that will build the component.
    """

    position: int
    component_name: str
    component_type: str = ""
    building_engine: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "position": self.position,
            "component_name": self.component_name,
            "component_type": self.component_type,
            "building_engine": self.building_engine,
        }


# ---------------------------------------------------------------------------#
# Detection finding (for the report)
# ---------------------------------------------------------------------------#

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"


@dataclass
class DetectionFinding:
    """A single finding produced during component detection.

    Attributes:
        severity: ``"error"`` or ``"warning"``.
        code: A short, machine-readable code (e.g.
            ``"duplicate_component"``).
        message: A human-readable description.
        affected: The name of the affected component.
        resolution_hint: An optional suggestion on how to fix the issue.
    """

    severity: str = SEVERITY_WARNING
    code: str = ""
    message: str = ""
    affected: str = ""
    resolution_hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "affected": self.affected,
            "resolution_hint": self.resolution_hint,
        }


# ---------------------------------------------------------------------------#
# The full component registry
# ---------------------------------------------------------------------------#

@dataclass
class ComponentRegistry:
    """The complete, authoritative list of every software component.

    This is the **only** object the Component Detection Engine produces.
    It is stored in the generation context as the
    ``component_registry`` artefact.

    The registry is **read-only** for all downstream engines \u2014 no
    engine may modify it directly.  Any modification requires a
    dedicated engine.

    Attributes:
        project_name: The machine-friendly project name.
        root_path: The root path of the generated project.
        components: The list of :class:`DetectedComponent` objects.
        relationships: The list of :class:`ComponentDependencyEdge`
            objects describing the wiring between components.
        build_order: The ordered list of
            :class:`ComponentBuildOrderEntry` objects.
        source_blueprint: The name of the blueprint this registry was
            built from.
        validation_status: The approval status of the blueprint at the
            time the registry was built.
        source_structure_map: The name of the structure map this
            registry was built from.
        findings: The list of :class:`DetectionFinding` objects
            produced during detection (duplicates, quality issues,
            scalability warnings, etc.).
        summary: A human-readable summary.
        notes: General notes about the detection.
        warnings: Warnings produced during detection.
    """

    project_name: str = ""
    root_path: str = ""
    components: List[DetectedComponent] = field(default_factory=list)
    relationships: List[ComponentDependencyEdge] = field(default_factory=list)
    build_order: List[ComponentBuildOrderEntry] = field(default_factory=list)
    source_blueprint: str = ""
    validation_status: str = ""
    source_structure_map: str = ""
    findings: List[DetectionFinding] = field(default_factory=list)
    summary: str = ""
    notes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # -- convenience -------------------------------------------------------#

    @property
    def component_count(self) -> int:
        return len(self.components)

    @property
    def is_empty(self) -> bool:
        return self.component_count == 0

    def component_names(self) -> List[str]:
        return [c.name for c in self.components]

    def component_types(self) -> List[str]:
        return sorted({c.type for c in self.components})

    def get(self, name: str) -> Optional[DetectedComponent]:
        for c in self.components:
            if c.name == name:
                return c
        return None

    def has(self, name: str) -> bool:
        return self.get(name) is not None

    def by_type(self, type_: str) -> List[DetectedComponent]:
        return [c for c in self.components if c.type == type_]

    def components_for_blueprint_component(
        self, blueprint_component: str,
    ) -> List[DetectedComponent]:
        return [
            c for c in self.components
            if c.source_blueprint_component == blueprint_component
        ]

    def add_finding(self, severity: str, code: str, message: str,
                    affected: str = "", resolution_hint: str = "") -> None:
        self.findings.append(DetectionFinding(
            severity=severity, code=code, message=message,
            affected=affected, resolution_hint=resolution_hint,
        ))
        if severity == SEVERITY_WARNING:
            self.warnings.append(message)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_name": self.project_name,
            "root_path": self.root_path,
            "component_count": self.component_count,
            "source_blueprint": self.source_blueprint,
            "validation_status": self.validation_status,
            "source_structure_map": self.source_structure_map,
            "summary": self.summary,
            "notes": list(self.notes),
            "warnings": list(self.warnings),
            "components": [c.to_dict() for c in self.components],
            "relationships": [r.to_dict() for r in self.relationships],
            "build_order": [b.to_dict() for b in self.build_order],
            "findings": [f.to_dict() for f in self.findings],
        }


__all__ = [
    # Component-type constants
    "COMPONENT_TYPE_COMMAND",
    "COMPONENT_TYPE_HANDLER",
    "COMPONENT_TYPE_ROUTER",
    "COMPONENT_TYPE_SERVICE",
    "COMPONENT_TYPE_MANAGER",
    "COMPONENT_TYPE_MIDDLEWARE",
    "COMPONENT_TYPE_FILTER",
    "COMPONENT_TYPE_DECORATOR",
    "COMPONENT_TYPE_UTILITY",
    "COMPONENT_TYPE_CONFIGURATION",
    "COMPONENT_TYPE_ENVIRONMENT",
    "COMPONENT_TYPE_DATABASE_MODEL",
    "COMPONENT_TYPE_REPOSITORY",
    "COMPONENT_TYPE_VALIDATOR",
    "COMPONENT_TYPE_KEYBOARD_BUILDER",
    "COMPONENT_TYPE_MESSAGE_BUILDER",
    "COMPONENT_TYPE_CALLBACK_HANDLER",
    "COMPONENT_TYPE_API_CLIENT",
    "COMPONENT_TYPE_SCHEDULER",
    "COMPONENT_TYPE_BACKGROUND_TASK",
    "COMPONENT_TYPE_CACHE_LAYER",
    "COMPONENT_TYPE_LOCALIZATION",
    "COMPONENT_TYPE_LOGGING_SYSTEM",
    "COMPONENT_TYPE_PLUGIN",
    "COMPONENT_TYPE_EXTENSION",
    "COMPONENT_TYPE_APPLICATION",
    "COMPONENT_TYPE_SESSION",
    "ALL_COMPONENT_TYPES",
    # Importance
    "IMPORTANCE_CRITICAL",
    "IMPORTANCE_HIGH",
    "IMPORTANCE_NORMAL",
    "IMPORTANCE_LOW",
    "ALL_IMPORTANCE_LEVELS",
    # Data model
    "DetectedComponent",
    "ComponentDependencyEdge",
    "ComponentBuildOrderEntry",
    "ComponentRegistry",
    # Findings
    "SEVERITY_ERROR",
    "SEVERITY_WARNING",
    "SEVERITY_INFO",
    "DetectionFinding",
]
