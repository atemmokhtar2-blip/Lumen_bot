"""
Component Analyzer — analyzes all detected components to determine the
dependencies each one requires (Specification 009).

The :class:`ComponentAnalyzer` is a stateless helper that the
:class:`DependencyResolutionEngine` calls during the *analysis* phase.
It reads the :class:`ComponentRegistry`, the
:class:`ProjectStructureMap`, and the :class:`FileGenerationPlan`, and
produces an intermediate analysis result: a mapping from each detected
component to the libraries, frameworks, and tools it requires, plus a
list of components that have **no** determined dependencies (which is a
quality concern).

The analyzer does **not** create :class:`DependencyEntry` objects — that
is the job of the :class:`LibraryDeterminer`.  It only analyses and
groups the data so the determiner can work efficiently.

Data source
-----------
The analyzer reads **only**:

1. the ``ComponentRegistry`` (``DetectedComponent`` objects),
2. the ``ProjectStructureMap`` (for file-type context), and
3. the ``FileGenerationPlan`` (for file-level context).

It does **not** read the user's request.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from ..component_detector.registry import (
    ComponentRegistry,
    DetectedComponent,
)
from ..file_planner.plan_data import FileGenerationPlan
from ..structure_generator.structure_map import ProjectStructureMap
from .report_data import ResolutionFinding, SEVERITY_WARNING


# ---------------------------------------------------------------------------#
# Known component-type → suggested dependency mapping
# ---------------------------------------------------------------------------#
#
# This table maps each detected component type to the libraries and
# tools it typically requires.  The determiner uses this to assign
# dependencies to components when the blueprint does not specify them
# explicitly.

_COMPONENT_TYPE_DEPENDENCIES: Dict[str, List[str]] = {
    "command": ["python-telegram-bot"],
    "handler": ["python-telegram-bot"],
    "router": ["python-telegram-bot"],
    "callback_handler": ["python-telegram-bot"],
    "keyboard_builder": ["python-telegram-bot"],
    "message_builder": ["python-telegram-bot"],
    "service": [],
    "manager": [],
    "middleware": ["python-telegram-bot"],
    "filter": ["python-telegram-bot"],
    "decorator": [],
    "utility": [],
    "configuration": [],
    "environment": [],
    "database_model": [],
    "repository": [],
    "validator": [],
    "api_client": [],
    "scheduler": [],
    "background_task": [],
    "cache_layer": [],
    "localization": [],
    "logging_system": [],
    "plugin": [],
    "extension": [],
    "application": ["python-telegram-bot"],
    "session": [],
}


@dataclass
class ComponentDependencyAnalysis:
    """The analysis result for a single detected component.

    Attributes:
        component: The detected component.
        required_libraries: The library names this component
            requires (derived from its type, metadata, and file
            plan).
        required_tools: The tool names this component requires.
        file_count: The number of files in the file plan that
            belong to this component.
    """

    component: DetectedComponent
    required_libraries: List[str] = field(default_factory=list)
    required_tools: List[str] = field(default_factory=list)
    file_count: int = 0

    @property
    def has_requirements(self) -> bool:
        return (
            len(self.required_libraries) > 0
            or len(self.required_tools) > 0
        )


@dataclass
class ComponentAnalysisResult:
    """The complete analysis result for all components.

    Attributes:
        analyses: A mapping from component name to
            :class:`ComponentDependencyAnalysis`.
        component_names: The ordered list of all component names.
        components_without_requirements: The names of components
            that have no determined dependencies.
        all_required_libraries: The complete set of library names
            required across all components.
        all_required_tools: The complete set of tool names
            required across all components.
    """

    analyses: Dict[str, ComponentDependencyAnalysis] = field(default_factory=dict)
    component_names: List[str] = field(default_factory=list)
    components_without_requirements: List[str] = field(default_factory=list)
    all_required_libraries: List[str] = field(default_factory=list)
    all_required_tools: List[str] = field(default_factory=list)

    def get(self, component_name: str) -> ComponentDependencyAnalysis:
        return self.analyses.get(
            component_name,
            ComponentDependencyAnalysis(
                component=DetectedComponent(name=component_name),
            ),
        )

    @property
    def component_count(self) -> int:
        return len(self.analyses)


class ComponentAnalyzer:
    """Stateless helper that analyses all detected components.

    The analyzer is called by the
    :class:`DependencyResolutionEngine` during the analysis phase.  It
    groups the components' required libraries by their type and
    cross-references them with the file generation plan.  It returns a
    :class:`ComponentAnalysisResult` and a list of warnings for
    components that have no determined dependencies.

    The analyzer is **pure**: it does not modify the registry, the
    structure map, or the file plan.  It only reads and groups.
    """

    def analyze(
        self,
        registry: ComponentRegistry,
        structure_map: ProjectStructureMap,
        file_plan: FileGenerationPlan,
    ) -> ComponentAnalysisResult:
        """Analyse all components and determine their dependencies.

        Parameters:
            registry: The component registry.
            structure_map: The project structure map.
            file_plan: The file generation plan.

        Returns:
            A :class:`ComponentAnalysisResult` containing the analysis
            for every detected component.
        """
        result = ComponentAnalysisResult()

        # Build a file-count-per-component lookup from the file plan.
        file_counts: Dict[str, int] = {}
        for f in file_plan.files:
            if f.source_component:
                file_counts[f.source_component] = (
                    file_counts.get(f.source_component, 0) + 1
                )

        # Analyse each component in the registry.
        for comp in registry.components:
            analysis = ComponentDependencyAnalysis(
                component=comp,
                file_count=file_counts.get(comp.name, 0),
            )

            # Derive required libraries from the component type.
            type_libs = _COMPONENT_TYPE_DEPENDENCIES.get(comp.type, [])
            analysis.required_libraries = list(type_libs)

            # Derive extra libraries from the component metadata, if any.
            meta_libs = comp.metadata.get("required_libraries", [])
            if isinstance(meta_libs, list):
                for lib in meta_libs:
                    if lib not in analysis.required_libraries:
                        analysis.required_libraries.append(lib)

            # Derive required tools from the component metadata.
            meta_tools = comp.metadata.get("required_tools", [])
            if isinstance(meta_tools, list):
                analysis.required_tools = list(meta_tools)

            # Database components may require an ORM/driver.
            if comp.type in ("database_model", "repository"):
                if comp.metadata.get("database") == "postgres":
                    if "psycopg2" not in analysis.required_libraries:
                        analysis.required_libraries.append("psycopg2")
                    if "SQLAlchemy" not in analysis.required_libraries:
                        analysis.required_libraries.append("SQLAlchemy")
                elif comp.metadata.get("database") == "sqlite":
                    if "SQLAlchemy" not in analysis.required_libraries:
                        analysis.required_libraries.append("SQLAlchemy")
                elif comp.metadata.get("orm") == "sqlalchemy":
                    if "SQLAlchemy" not in analysis.required_libraries:
                        analysis.required_libraries.append("SQLAlchemy")

            result.analyses[comp.name] = analysis
            result.component_names.append(comp.name)

            # Accumulate the global sets.
            for lib in analysis.required_libraries:
                if lib not in result.all_required_libraries:
                    result.all_required_libraries.append(lib)
            for tool in analysis.required_tools:
                if tool not in result.all_required_tools:
                    result.all_required_tools.append(tool)

            if not analysis.has_requirements:
                result.components_without_requirements.append(comp.name)

        return result

    def findings_for_missing_requirements(
        self,
        result: ComponentAnalysisResult,
    ) -> List[ResolutionFinding]:
        """Produce warnings for components that have no requirements.

        Parameters:
            result: The analysis result.

        Returns:
            A list of :class:`ResolutionFinding` objects (one per
            component without determined dependencies).
        """
        findings: List[ResolutionFinding] = []
        for name in result.components_without_requirements:
            findings.append(ResolutionFinding(
                severity=SEVERITY_WARNING,
                code="component_without_requirements",
                message=(
                    f"Component '{name}' has no determined "
                    f"dependencies.  It may not require any external "
                    f"libraries, but this should be confirmed."
                ),
                affected=name,
                resolution_hint=(
                    f"Confirm that component '{name}' needs no "
                    f"external libraries, or add its requirements to "
                    f"the blueprint."
                ),
                category="validation",
            ))
        return findings


__all__ = [
    "ComponentAnalyzer",
    "ComponentDependencyAnalysis",
    "ComponentAnalysisResult",
]
