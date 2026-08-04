"""
Dependency Resolution Report data model (Specification 009).

This module defines the :class:`DependencyResolutionReport` — the
complete, authoritative dependency map for every library, framework,
and tool that the generated Telegram bot project will use **before**
any code is written or any file is created on disk.  It is the single
artefact produced by the
:class:`~telegram_bot_engine.engines.generators.dependency_resolver.DependencyResolutionEngine`.

The report is built from **five** read-only artefacts:

1. the ``project_blueprint`` (produced by the Project Planning Engine),
2. the ``blueprint_validation_report`` (produced by the Blueprint
   Validator Engine),
3. the ``project_structure_map`` (produced by the Structure Generation
   Engine),
4. the ``component_registry`` (produced by the Component Detection
   Engine),
5. the ``file_generation_plan`` (produced by the File Generation
   Planning Engine).

The resolution engine is **forbidden** from reading the user's request.

Design principles
-----------------
* **Every dependency is known before construction begins.**  No
  library, framework, or tool is invented during code generation —
  they are all resolved here.
* **One responsibility per dependency.**  Each dependency entry carries
  a single, clear reason for existing.
* **No dependency without a reason.**  Every dependency entry records
  *why* it is needed (``reason``).
* **No dependency without a source.**  Every dependency is linked to
  at least one detected component or to the project infrastructure.
* **Version compatibility.**  Every dependency records its suggested
  version and the version constraints that make it compatible with the
  language, framework, operating system, and other dependencies.
* **Conflict detection.**  The report records every conflict found
  (version conflicts, duplicates, unused dependencies, circular
  dependencies, broken dependencies).
* **Security awareness.**  The report flags dependencies with bad
  reputation, untrusted sources, or known-vulnerable versions.
* **Optimization.**  The report records optimization notes (minimize
  libraries, prefer official, avoid abandoned/unstable).
* **Extensibility.**  New dependencies can be added to the report
  without redesigning the existing structure — the report is built to
  grow with the project.

The report is a plain data container — no logic lives here.  The
resolution engine and its helpers populate it; downstream consumers
(the code generators, the manager, tests) read it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------#
# Dependency-type constants
# ---------------------------------------------------------------------------#
#
# The set of dependency types the resolution engine recognises.  These
# classify the broad kind of each dependency so downstream engines can
# group and process them.

DEPENDENCY_TYPE_LIBRARY = "library"
DEPENDENCY_TYPE_FRAMEWORK = "framework"
DEPENDENCY_TYPE_TOOL = "tool"
DEPENDENCY_TYPE_RUNTIME = "runtime"
DEPENDENCY_TYPE_DEV = "dev"
DEPENDENCY_TYPE_TEST = "test"
DEPENDENCY_TYPE_BUILD = "build"

ALL_DEPENDENCY_TYPES = (
    DEPENDENCY_TYPE_LIBRARY,
    DEPENDENCY_TYPE_FRAMEWORK,
    DEPENDENCY_TYPE_TOOL,
    DEPENDENCY_TYPE_RUNTIME,
    DEPENDENCY_TYPE_DEV,
    DEPENDENCY_TYPE_TEST,
    DEPENDENCY_TYPE_BUILD,
)


# ---------------------------------------------------------------------------#
# Dependency-priority constants
# ---------------------------------------------------------------------------#
#
# The dependency priority determines the broad phase in which a
# dependency must be resolved and installed.  Lower values are resolved
# first.

DEPENDENCY_PRIORITY_INFRASTRUCTURE = 10
DEPENDENCY_PRIORITY_CORE = 20
DEPENDENCY_PRIORITY_DATABASE = 30
DEPENDENCY_PRIORITY_FEATURES = 40
DEPENDENCY_PRIORITY_WIRING = 50
DEPENDENCY_PRIORITY_ENTRY = 60
DEPENDENCY_PRIORITY_TESTS = 70
DEPENDENCY_PRIORITY_DEV = 80

ALL_DEPENDENCY_PRIORITIES = (
    DEPENDENCY_PRIORITY_INFRASTRUCTURE,
    DEPENDENCY_PRIORITY_CORE,
    DEPENDENCY_PRIORITY_DATABASE,
    DEPENDENCY_PRIORITY_FEATURES,
    DEPENDENCY_PRIORITY_WIRING,
    DEPENDENCY_PRIORITY_ENTRY,
    DEPENDENCY_PRIORITY_TESTS,
    DEPENDENCY_PRIORITY_DEV,
)


# ---------------------------------------------------------------------------#
# Dependency-source constants
# ---------------------------------------------------------------------------#
#
# The source of a dependency — where it came from in the planning
# artefacts.

SOURCE_BLUEPRINT = "blueprint"
SOURCE_COMPONENT = "component"
SOURCE_FILE_PLAN = "file_plan"
SOURCE_FRAMEWORK = "framework"
SOURCE_INFERENCE = "inference"

ALL_SOURCES = (
    SOURCE_BLUEPRINT,
    SOURCE_COMPONENT,
    SOURCE_FILE_PLAN,
    SOURCE_FRAMEWORK,
    SOURCE_INFERENCE,
)


# ---------------------------------------------------------------------------#
# Reputation / trust constants
# ---------------------------------------------------------------------------#

REPUTATION_GOOD = "good"
REPUTATION_NEUTRAL = "neutral"
REPUTATION_BAD = "bad"
REPUTATION_UNKNOWN = "unknown"

ALL_REPUTATIONS = (
    REPUTATION_GOOD,
    REPUTATION_NEUTRAL,
    REPUTATION_BAD,
    REPUTATION_UNKNOWN,
)

TRUST_OFFICIAL = "official"
TRUST_COMMUNITY = "community"
TRUST_UNTRUSTED = "untrusted"
TRUST_UNKNOWN = "unknown"

ALL_TRUST_LEVELS = (
    TRUST_OFFICIAL,
    TRUST_COMMUNITY,
    TRUST_UNTRUSTED,
    TRUST_UNKNOWN,
)


# ---------------------------------------------------------------------------#
# Stability constants
# ---------------------------------------------------------------------------#

STABILITY_STABLE = "stable"
STABILITY_BETA = "beta"
STABILITY_UNSTABLE = "unstable"
STABILITY_ABANDONED = "abandoned"
STABILITY_UNKNOWN = "unknown"

ALL_STABILITIES = (
    STABILITY_STABLE,
    STABILITY_BETA,
    STABILITY_UNSTABLE,
    STABILITY_ABANDONED,
    STABILITY_UNKNOWN,
)


# ---------------------------------------------------------------------------#
# Finding severity constants
# ---------------------------------------------------------------------------#

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"


# ---------------------------------------------------------------------------#
# A single dependency entry
# ---------------------------------------------------------------------------#

@dataclass
class DependencyEntry:
    """A single resolved dependency in the Dependency Resolution Report.

    This is the unit of the report.  Each entry describes a library,
    framework, or tool that the project will use — it is **not** the
    library itself, nor does it contain any code or installation
    instructions.

    Attributes:
        name: The dependency name (e.g. ``"python-telegram-bot"``,
            ``"SQLAlchemy"``).
        type: The dependency type (one of the
            ``DEPENDENCY_TYPE_*`` constants).
        suggested_version: The suggested version (e.g. ``"21.x"``,
            ``">=2.0,<3.0"``, ``"latest"``).
        version_constraint: The version constraint that must be
            satisfied for compatibility (e.g.
            ``">=2.0,<3.0"``).
        reason: A human-readable explanation of *why* this dependency
            is needed.
        source: Where this dependency was discovered (one of the
            ``SOURCE_*`` constants).
        source_components: The detected component names that require
            this dependency.
        priority: The broad resolution phase (one of the
            ``DEPENDENCY_PRIORITY_*`` constants).  Lower values are
            resolved first.
        depends_on: The names of other dependencies this one depends
            on.
        depended_by: The names of dependencies that depend on this
            one.
        load_order: The precise position in the installation/load
            sequence (lower first).  Assigned by the dependency graph
            builder.
        language: The programming language this dependency is for
            (e.g. ``"python"``).
        framework: The framework this dependency belongs to or
            requires (e.g. ``"python-telegram-bot"``).
        os_compatibility: The operating systems this dependency is
            compatible with (e.g. ``["linux", "windows", "macos"]``).
        reputation: The reputation of the dependency (one of the
            ``REPUTATION_*`` constants).
        trust: The trust level (one of the ``TRUST_*`` constants).
        stability: The stability level (one of the
            ``STABILITY_*`` constants).
        official: ``True`` when this is an official/maintained
            dependency.
        extensible: ``True`` when additional dependencies can be
            added later without redesign.
        metadata: Free-form extra information.
    """

    name: str
    type: str = DEPENDENCY_TYPE_LIBRARY
    suggested_version: str = "latest"
    version_constraint: str = ""
    reason: str = ""
    source: str = SOURCE_INFERENCE
    source_components: List[str] = field(default_factory=list)
    priority: int = DEPENDENCY_PRIORITY_CORE
    depends_on: List[str] = field(default_factory=list)
    depended_by: List[str] = field(default_factory=list)
    load_order: int = 0
    language: str = ""
    framework: str = ""
    os_compatibility: List[str] = field(default_factory=list)
    reputation: str = REPUTATION_UNKNOWN
    trust: str = TRUST_UNKNOWN
    stability: str = STABILITY_UNKNOWN
    official: bool = False
    extensible: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError(
                "DependencyEntry requires a non-empty name."
            )

    def add_dependency(self, name: str) -> None:
        """Record that this dependency depends on another (by name)."""
        # Never allow a dependency to depend on itself (self-cycle).
        if name and name != self.name and name not in self.depends_on:
            self.depends_on.append(name)

    def add_dependent(self, name: str) -> None:
        """Record that another dependency depends on this one."""
        if name and name != self.name and name not in self.depended_by:
            self.depended_by.append(name)

    def add_source_component(self, component: str) -> None:
        """Record that a component requires this dependency."""
        if component and component not in self.source_components:
            self.source_components.append(component)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "suggested_version": self.suggested_version,
            "version_constraint": self.version_constraint,
            "reason": self.reason,
            "source": self.source,
            "source_components": list(self.source_components),
            "priority": self.priority,
            "depends_on": list(self.depends_on),
            "depended_by": list(self.depended_by),
            "load_order": self.load_order,
            "language": self.language,
            "framework": self.framework,
            "os_compatibility": list(self.os_compatibility),
            "reputation": self.reputation,
            "trust": self.trust,
            "stability": self.stability,
            "official": self.official,
            "extensible": self.extensible,
            "metadata": dict(self.metadata),
        }


# ---------------------------------------------------------------------------#
# Dependency relationship
# ---------------------------------------------------------------------------#

@dataclass
class DependencyRelationship:
    """A directed relationship between two resolved dependencies.

    Relationships are **recorded but not linked** — they describe which
    dependencies depend on each other so that later engines can wire
    them up.  No imports, installations, or physical links are created
    at this stage.

    Attributes:
        source: The source dependency name.
        target: The target dependency name.
        kind: The relationship kind (``"depends_on"``,
            ``"requires"``, ``"extends"``, ``"conflicts_with"``,
            ``"replaces"``).
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
# Dependency order entry
# ---------------------------------------------------------------------------#

@dataclass
class DependencyOrderEntry:
    """A single entry in the dependency load order sequence.

    The load order tells later engines in which sequence the
    dependencies should be resolved and installed.  It is a
    topological sort of the dependency graph, adjusted by priority.

    Attributes:
        position: The 0-based position in the load sequence.
        dependency_name: The name of the dependency.
        dependency_type: The type of the dependency.
        priority: The dependency priority (lower first).
        source_components: The components that require this
            dependency.
    """

    position: int
    dependency_name: str
    dependency_type: str = DEPENDENCY_TYPE_LIBRARY
    priority: int = DEPENDENCY_PRIORITY_CORE
    source_components: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "position": self.position,
            "dependency_name": self.dependency_name,
            "dependency_type": self.dependency_type,
            "priority": self.priority,
            "source_components": list(self.source_components),
        }


# ---------------------------------------------------------------------------#
# Resolution finding (for the report)
# ---------------------------------------------------------------------------#

@dataclass
class ResolutionFinding:
    """A single finding produced during dependency resolution.

    Attributes:
        severity: ``"error"``, ``"warning"``, or ``"info"``.
        code: A short, machine-readable code (e.g.
            ``"version_conflict"``).
        message: A human-readable description.
        affected: The name of the affected dependency or component.
        resolution_hint: An optional suggestion on how to fix the
            issue.
        category: The finding category (``"conflict"``,
            ``"compatibility"``, ``"security"``, ``"optimization"``,
            ``"validation"``).
    """

    severity: str = SEVERITY_WARNING
    code: str = ""
    message: str = ""
    affected: str = ""
    resolution_hint: str = ""
    category: str = "validation"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "affected": self.affected,
            "resolution_hint": self.resolution_hint,
            "category": self.category,
        }


# ---------------------------------------------------------------------------#
# The full dependency resolution report
# ---------------------------------------------------------------------------#

@dataclass
class DependencyResolutionReport:
    """The complete, authoritative dependency map for the project.

    This is the **only** object the Dependency Resolution Engine
    produces.  It is stored in the generation context as the
    ``dependency_resolution_report`` artefact.

    The report is **read-only** for all downstream engines — no engine
    may modify it directly.  Any modification requires a dedicated
    engine.

    Attributes:
        project_name: The machine-friendly project name.
        language: The project's primary programming language.
        language_version: The project's language version.
        framework: The project's primary framework.
        dependencies: The list of :class:`DependencyEntry` objects —
            the complete list of every dependency to be resolved.
        relationships: The list of :class:`DependencyRelationship`
            objects describing the wiring between dependencies.
        load_order: The ordered list of
            :class:`DependencyOrderEntry` objects.
        source_blueprint: The name of the blueprint this report was
            built from.
        validation_status: The approval status of the blueprint at
            the time the report was built.
        source_structure_map: The name of the structure map this
            report was built from.
        source_component_registry: The name of the component registry
            this report was built from.
        source_file_generation_plan: The name of the file generation
            plan this report was built from.
        findings: The list of :class:`ResolutionFinding` objects
            produced during resolution (conflicts, compatibility,
            security, optimization, validation).
        summary: A human-readable summary.
        notes: General notes about the report.
        warnings: Warnings produced during resolution.
    """

    project_name: str = ""
    language: str = ""
    language_version: str = ""
    framework: str = ""
    dependencies: List[DependencyEntry] = field(default_factory=list)
    relationships: List[DependencyRelationship] = field(default_factory=list)
    load_order: List[DependencyOrderEntry] = field(default_factory=list)
    source_blueprint: str = ""
    validation_status: str = ""
    source_structure_map: str = ""
    source_component_registry: str = ""
    source_file_generation_plan: str = ""
    findings: List[ResolutionFinding] = field(default_factory=list)
    summary: str = ""
    notes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # -- convenience -------------------------------------------------------#

    @property
    def dependency_count(self) -> int:
        return len(self.dependencies)

    @property
    def is_empty(self) -> bool:
        return self.dependency_count == 0

    def dependency_names(self) -> List[str]:
        return [d.name for d in self.dependencies]

    def get_dependency(self, name: str) -> Optional[DependencyEntry]:
        for d in self.dependencies:
            if d.name == name:
                return d
        return None

    def has_dependency(self, name: str) -> bool:
        return self.get_dependency(name) is not None

    def dependencies_for_component(self, component_name: str) -> List[DependencyEntry]:
        return [
            d for d in self.dependencies
            if component_name in d.source_components
        ]

    def dependencies_by_type(self, dep_type: str) -> List[DependencyEntry]:
        return [d for d in self.dependencies if d.type == dep_type]

    def dependencies_by_priority(self, priority: int) -> List[DependencyEntry]:
        return [d for d in self.dependencies if d.priority == priority]

    def add_finding(
        self,
        severity: str,
        code: str,
        message: str,
        affected: str = "",
        resolution_hint: str = "",
        category: str = "validation",
    ) -> None:
        self.findings.append(ResolutionFinding(
            severity=severity,
            code=code,
            message=message,
            affected=affected,
            resolution_hint=resolution_hint,
            category=category,
        ))
        if severity == SEVERITY_WARNING:
            self.warnings.append(message)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_name": self.project_name,
            "language": self.language,
            "language_version": self.language_version,
            "framework": self.framework,
            "dependency_count": self.dependency_count,
            "source_blueprint": self.source_blueprint,
            "validation_status": self.validation_status,
            "source_structure_map": self.source_structure_map,
            "source_component_registry": self.source_component_registry,
            "source_file_generation_plan": self.source_file_generation_plan,
            "summary": self.summary,
            "notes": list(self.notes),
            "warnings": list(self.warnings),
            "dependencies": [d.to_dict() for d in self.dependencies],
            "relationships": [r.to_dict() for r in self.relationships],
            "load_order": [o.to_dict() for o in self.load_order],
            "findings": [f.to_dict() for f in self.findings],
        }


__all__ = [
    # Dependency-type constants
    "DEPENDENCY_TYPE_LIBRARY",
    "DEPENDENCY_TYPE_FRAMEWORK",
    "DEPENDENCY_TYPE_TOOL",
    "DEPENDENCY_TYPE_RUNTIME",
    "DEPENDENCY_TYPE_DEV",
    "DEPENDENCY_TYPE_TEST",
    "DEPENDENCY_TYPE_BUILD",
    "ALL_DEPENDENCY_TYPES",
    # Dependency-priority constants
    "DEPENDENCY_PRIORITY_INFRASTRUCTURE",
    "DEPENDENCY_PRIORITY_CORE",
    "DEPENDENCY_PRIORITY_DATABASE",
    "DEPENDENCY_PRIORITY_FEATURES",
    "DEPENDENCY_PRIORITY_WIRING",
    "DEPENDENCY_PRIORITY_ENTRY",
    "DEPENDENCY_PRIORITY_TESTS",
    "DEPENDENCY_PRIORITY_DEV",
    "ALL_DEPENDENCY_PRIORITIES",
    # Source constants
    "SOURCE_BLUEPRINT",
    "SOURCE_COMPONENT",
    "SOURCE_FILE_PLAN",
    "SOURCE_FRAMEWORK",
    "SOURCE_INFERENCE",
    "ALL_SOURCES",
    # Reputation constants
    "REPUTATION_GOOD",
    "REPUTATION_NEUTRAL",
    "REPUTATION_BAD",
    "REPUTATION_UNKNOWN",
    "ALL_REPUTATIONS",
    # Trust constants
    "TRUST_OFFICIAL",
    "TRUST_COMMUNITY",
    "TRUST_UNTRUSTED",
    "TRUST_UNKNOWN",
    "ALL_TRUST_LEVELS",
    # Stability constants
    "STABILITY_STABLE",
    "STABILITY_BETA",
    "STABILITY_UNSTABLE",
    "STABILITY_ABANDONED",
    "STABILITY_UNKNOWN",
    "ALL_STABILITIES",
    # Severity
    "SEVERITY_ERROR",
    "SEVERITY_WARNING",
    "SEVERITY_INFO",
    # Data model
    "DependencyEntry",
    "DependencyRelationship",
    "DependencyOrderEntry",
    "ResolutionFinding",
    "DependencyResolutionReport",
]
