"""
Component Analyzer — analyzes all detected components to determine the
files each one requires (Specification 008).

The :class:`ComponentAnalyzer` is a stateless helper that the
:class:`FileGenerationPlanningEngine` calls during the *analysis* phase.
It reads the :class:`ComponentRegistry` and the
:class:`ProjectStructureMap` and produces an intermediate analysis
result: a mapping from each detected component to the files it already
has in the structure map, plus a list of components that have **no**
files in the structure map (which is a quality violation).

The analyzer does **not** create :class:`FilePlanEntry` objects — that
is the job of the :class:`FileDeterminer`.  It only analyses and groups
the data so the determiner can work efficiently.

Data source
-----------
The analyzer reads **only**:

1. the ``ComponentRegistry`` (``DetectedComponent`` objects), and
2. the ``ProjectStructureMap`` (``FileEntry``, ``FolderEntry``
   objects).

It does **not** read the user's request.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set

from ..component_detector.registry import (
    ComponentRegistry,
    DetectedComponent,
    SEVERITY_WARNING,
)
from ..structure_generator.structure_map import (
    FileEntry,
    FolderEntry,
    ProjectStructureMap,
)
from .plan_data import PlanFinding


@dataclass
class ComponentFileAnalysis:
    """The analysis result for a single detected component.

    Attributes:
        component: The detected component.
        files: The file entries from the structure map that belong
            to this component.
        folder: The folder entry that holds this component's files,
            if any.
    """

    component: DetectedComponent
    files: List[FileEntry] = field(default_factory=list)
    folder: FolderEntry = None  # type: ignore[assignment]

    @property
    def has_files(self) -> bool:
        return len(self.files) > 0


@dataclass
class ComponentAnalysisResult:
    """The complete analysis result for all components.

    Attributes:
        analyses: A mapping from component name to
            :class:`ComponentFileAnalysis`.
        component_names: The ordered list of all component names.
        components_without_files: The names of components that have
            no files in the structure map.
        all_files: All file entries from the structure map (for
            cross-referencing).
        all_folders: All folder entries from the structure map.
    """

    analyses: Dict[str, ComponentFileAnalysis] = field(default_factory=dict)
    component_names: List[str] = field(default_factory=list)
    components_without_files: List[str] = field(default_factory=list)
    all_files: List[FileEntry] = field(default_factory=list)
    all_folders: List[FolderEntry] = field(default_factory=list)

    def get(self, component_name: str) -> ComponentFileAnalysis:
        return self.analyses.get(
            component_name,
            ComponentFileAnalysis(
                component=DetectedComponent(name=component_name),
            ),
        )

    @property
    def component_count(self) -> int:
        return len(self.analyses)


class ComponentAnalyzer:
    """Stateless helper that analyses all detected components.

    The analyzer is called by the
    :class:`FileGenerationPlanningEngine` during the analysis phase.
    It groups the structure map's files by their source component and
    cross-references them with the component registry.  It returns a
    :class:`ComponentAnalysisResult` and a list of warnings for
    components that have no files.

    The analyzer is **pure**: it does not modify the registry, the
    structure map, or any other artefact.  It only reads and groups.
    """

    def analyze(
        self,
        registry: ComponentRegistry,
        structure_map: ProjectStructureMap,
    ) -> ComponentAnalysisResult:
        """Analyse all components and group their files.

        Parameters:
            registry: The component registry.
            structure_map: The project structure map.

        Returns:
            A :class:`ComponentAnalysisResult` containing the analysis
            for every detected component.
        """
        result = ComponentAnalysisResult(
            all_files=list(structure_map.files),
            all_folders=list(structure_map.folders),
        )

        # Build a lookup of files by source_component name.
        files_by_source: Dict[str, List[FileEntry]] = {}
        for f in structure_map.files:
            key = f.source_component or ""
            files_by_source.setdefault(key, []).append(f)

        # Build a lookup of folders by path.
        folders_by_path: Dict[str, FolderEntry] = {
            folder.path: folder for folder in structure_map.folders
        }

        # Analyse each component in the registry.
        for comp in registry.components:
            analysis = ComponentFileAnalysis(component=comp)

            # Find files that belong to this component.
            comp_files = files_by_source.get(comp.name, [])
            if not comp_files:
                # Try the source_blueprint_component as a fallback key.
                comp_files = files_by_source.get(
                    comp.source_blueprint_component, [],
                )
            analysis.files = list(comp_files)

            # Find the folder that holds this component's files.
            if comp_files:
                for f in comp_files:
                    if f.folder and f.folder in folders_by_path:
                        analysis.folder = folders_by_path[f.folder]
                        break
            if analysis.folder is None and comp.location:
                # Try the component's location as a folder path.
                if comp.location in folders_by_path:
                    analysis.folder = folders_by_path[comp.location]

            result.analyses[comp.name] = analysis
            result.component_names.append(comp.name)

            if not analysis.has_files:
                result.components_without_files.append(comp.name)

        return result

    def findings_for_missing_files(
        self,
        result: ComponentAnalysisResult,
    ) -> List[PlanFinding]:
        """Produce warnings for components that have no files.

        Parameters:
            result: The analysis result.

        Returns:
            A list of :class:`PlanFinding` objects (one per
            component without files).
        """
        findings: List[PlanFinding] = []
        for name in result.components_without_files:
            findings.append(PlanFinding(
                severity=SEVERITY_WARNING,
                code="component_without_files",
                message=(
                    f"Component '{name}' has no files in the "
                    f"structure map."
                ),
                affected=name,
                resolution_hint=(
                    f"Ensure the structure map includes at least one "
                    f"file for component '{name}'."
                ),
            ))
        return findings


__all__ = [
    "ComponentAnalyzer",
    "ComponentFileAnalysis",
    "ComponentAnalysisResult",
]
