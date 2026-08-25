"""
File Determiner — determines the required files per component and
assigns metadata to each (Specification 008).

The :class:`FileDeterminer` is a stateless helper that the
:class:`FileGenerationPlanningEngine` calls during the *file
determination* phase.  It takes the
:class:`ComponentAnalysisResult` produced by the
:class:`ComponentAnalyzer` and converts each structure-map
:class:`FileEntry` into a :class:`FilePlanEntry` — the planned-file
object that records the full metadata the spec requires:

* name
* extension
* file type
* purpose (the single, clear responsibility of the file)
* responsible engine (the engine that will build this file later)
* generation priority (the broad generation phase)
* folder (the folder this file belongs to)
* source component (the detected component this file belongs to)
* reason for existence (why this file exists)
* contains code (whether the file will contain executable code)

The determiner enforces the **Single Responsibility Principle** at the
file level: each file entry is derived from exactly one component and
carries a single, clear purpose.  It does **not** create new files that
do not exist in the structure map — it only enriches the existing file
entries with planning metadata.

Data source
-----------
The determiner reads **only**:

1. the :class:`ComponentAnalysisResult` (from the
   :class:`ComponentAnalyzer`), and
2. the :class:`ProjectStructureMap` (for folder lookup).

It does **not** read the user's request.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

from ..structure_generator.structure_map import (
    FileEntry,
    FolderEntry,
    ProjectStructureMap,
    BUILD_ORDER_CORE,
    BUILD_ORDER_DATABASE,
    BUILD_ORDER_DOCS,
    BUILD_ORDER_ENTRY,
    BUILD_ORDER_FEATURES,
    BUILD_ORDER_INFRASTRUCTURE,
    BUILD_ORDER_TESTS,
    BUILD_ORDER_WIRING,
    FILE_TYPE_DOCKERFILE,
    FILE_TYPE_ENV,
    FILE_TYPE_JSON,
    FILE_TYPE_MARKDOWN,
    FILE_TYPE_PYTHON_MODULE,
    FILE_TYPE_PYTHON_PACKAGE,
    FILE_TYPE_REQUIREMENTS,
    FILE_TYPE_SQL,
    FILE_TYPE_TEXT,
    FILE_TYPE_YAML,
)
from .component_analyzer import ComponentAnalysisResult
from .plan_data import (
    EXTENSION_DOCKERFILE,
    EXTENSION_ENV,
    EXTENSION_JSON,
    EXTENSION_MARKDOWN,
    EXTENSION_PYTHON,
    EXTENSION_SQL,
    EXTENSION_TEXT,
    EXTENSION_YAML,
    EXTENSION_YML,
    FilePlanEntry,
    GENERATION_PRIORITY_CORE,
    GENERATION_PRIORITY_DATABASE,
    GENERATION_PRIORITY_DOCS,
    GENERATION_PRIORITY_ENTRY,
    GENERATION_PRIORITY_FEATURES,
    GENERATION_PRIORITY_INFRASTRUCTURE,
    GENERATION_PRIORITY_TESTS,
    GENERATION_PRIORITY_WIRING,
)


# ---------------------------------------------------------------------------#
# Build-order → generation-priority mapping
# ---------------------------------------------------------------------------#
#
# The structure map assigns each file a ``build_order`` value (one of
# the ``BUILD_ORDER_*`` constants).  The file planner translates this
# to a ``generation_priority`` value so the plan is self-contained
# without depending on the structure map's constants.

_BUILD_ORDER_TO_PRIORITY: Dict[int, int] = {
    BUILD_ORDER_INFRASTRUCTURE: GENERATION_PRIORITY_INFRASTRUCTURE,
    BUILD_ORDER_CORE: GENERATION_PRIORITY_CORE,
    BUILD_ORDER_DATABASE: GENERATION_PRIORITY_DATABASE,
    BUILD_ORDER_FEATURES: GENERATION_PRIORITY_FEATURES,
    BUILD_ORDER_WIRING: GENERATION_PRIORITY_WIRING,
    BUILD_ORDER_ENTRY: GENERATION_PRIORITY_ENTRY,
    BUILD_ORDER_DOCS: GENERATION_PRIORITY_DOCS,
    BUILD_ORDER_TESTS: GENERATION_PRIORITY_TESTS,
}


# ---------------------------------------------------------------------------#
# Extension → file-type mapping
# ---------------------------------------------------------------------------#
#
# Maps a file's extension to its file type.  The file type is derived
# from the extension when the structure map's file type is generic
# (e.g. ``"text"``) or empty.

_EXTENSION_TO_FILE_TYPE: Dict[str, str] = {
    EXTENSION_PYTHON: FILE_TYPE_PYTHON_MODULE,
    EXTENSION_YAML: FILE_TYPE_YAML,
    EXTENSION_YML: FILE_TYPE_YAML,
    EXTENSION_ENV: FILE_TYPE_ENV,
    EXTENSION_JSON: FILE_TYPE_JSON,
    EXTENSION_SQL: FILE_TYPE_SQL,
    EXTENSION_MARKDOWN: FILE_TYPE_MARKDOWN,
    EXTENSION_TEXT: FILE_TYPE_TEXT,
    EXTENSION_DOCKERFILE: FILE_TYPE_DOCKERFILE,
}


class FileDeterminer:
    """Stateless helper that determines required files per component.

    The determiner is called by the
    :class:`FileGenerationPlanningEngine` after the
    :class:`ComponentAnalyzer` has grouped the structure map's files
    by component.  It converts each :class:`FileEntry` into a
    :class:`FilePlanEntry` with the full planning metadata.

    The determiner is **pure**: it does not modify the structure map,
    the component registry, or the analysis result.  It produces a new
    list of :class:`FilePlanEntry` objects.
    """

    def determine(
        self,
        analysis: ComponentAnalysisResult,
        structure_map: ProjectStructureMap,
    ) -> List[FilePlanEntry]:
        """Determine the required files and their metadata.

        Parameters:
            analysis: The component analysis result (from the
                :class:`ComponentAnalyzer`).
            structure_map: The project structure map (for folder
                lookup).

        Returns:
            A list of :class:`FilePlanEntry` objects — one per file
            in the structure map, enriched with planning metadata.
        """
        # Build a folder lookup for resolving folder paths.
        folders_by_path: Dict[str, FolderEntry] = {
            f.path: f for f in structure_map.folders
        }

        # Build a component-name → component lookup for assigning
        # source_component.
        # (The analysis result already has the component per file
        # grouped, so we use that.)

        # Map from file path → component name.
        file_to_component: Dict[str, str] = {}
        for comp_name, comp_analysis in analysis.analyses.items():
            for f in comp_analysis.files:
                file_to_component[f.path] = comp_name

        entries: List[FilePlanEntry] = []

        # Process every file in the structure map.
        for f in structure_map.files:
            entry = self._make_entry(
                f,
                structure_map,
                folders_by_path,
                file_to_component,
            )
            entries.append(entry)

        return entries

    # -----------------------------------------------------------------#
    # Internal helpers
    # -----------------------------------------------------------------#

    def _make_entry(
        self,
        file_entry: FileEntry,
        structure_map: ProjectStructureMap,
        folders_by_path: Dict[str, FolderEntry],
        file_to_component: Dict[str, str],
    ) -> FilePlanEntry:
        """Build a single :class:`FilePlanEntry` from a file entry."""
        # Derive the extension from the file name.
        extension = self._derive_extension(file_entry.name)

        # Derive the file type — use the structure map's file type if
        # it is specific enough, otherwise derive from the extension.
        file_type = self._derive_file_type(file_entry.file_type, extension)

        # Derive the generation priority from the build order.
        generation_priority = self._derive_priority(file_entry.build_order)

        # Resolve the folder path.
        folder = file_entry.folder or self._derive_folder(
            file_entry.path, folders_by_path,
        )

        # Resolve the source component.
        source_component = file_to_component.get(
            file_entry.path, file_entry.source_component or "",
        )

        # Resolve the responsible engine.
        responsible_engine = file_entry.building_engine or "code_generator"

        # Build the reason for existence.
        reason = self._build_reason(
            file_entry, source_component, file_type,
        )

        return FilePlanEntry(
            name=file_entry.name,
            path=file_entry.path,
            extension=extension,
            file_type=file_type,
            purpose=file_entry.purpose or reason,
            responsible_engine=responsible_engine,
            generation_priority=generation_priority,
            folder=folder,
            source_component=source_component,
            reason_for_existence=reason,
            contains_code=file_entry.contains_code,
            scalable=True,
        )

    @staticmethod
    def _derive_extension(name: str) -> str:
        """Derive the file extension from the file name.

        Returns ``""`` for files without an extension (e.g.
        ``Dockerfile``).
        """
        # Handle special cases.
        lower = name.lower()
        if lower == "dockerfile":
            return EXTENSION_DOCKERFILE
        if lower in ("requirements", "requirements.txt"):
            return EXTENSION_TEXT

        _, ext = os.path.splitext(name)
        return ext

    @staticmethod
    def _derive_file_type(existing_type: str, extension: str) -> str:
        """Derive the file type from the existing type or extension."""
        # If the structure map already has a specific type, use it.
        if existing_type and existing_type != FILE_TYPE_TEXT:
            return existing_type

        # Derive from the extension.
        return _EXTENSION_TO_FILE_TYPE.get(extension, FILE_TYPE_TEXT)

    @staticmethod
    def _derive_priority(build_order: int) -> int:
        """Derive the generation priority from the build order."""
        return _BUILD_ORDER_TO_PRIORITY.get(
            build_order, GENERATION_PRIORITY_CORE,
        )

    @staticmethod
    def _derive_folder(
        path: str,
        folders_by_path: Dict[str, FolderEntry],
    ) -> str:
        """Derive the folder path from the file path."""
        parts = path.strip("/").split("/")
        if len(parts) <= 1:
            return ""

        parent = "/".join(parts[:-1])

        # If the parent is a known folder, return it.
        if parent in folders_by_path:
            return parent

        # Return the parent path even if it's not a registered folder.
        return parent

    @staticmethod
    def _build_reason(
        file_entry: FileEntry,
        source_component: str,
        file_type: str,
    ) -> str:
        """Build a human-readable reason for the file's existence."""
        purpose = file_entry.purpose or "provides a single responsibility"
        if source_component:
            return (
                f"File '{file_entry.name}' exists to {purpose} "
                f"for component '{source_component}'."
            )
        return (
            f"File '{file_entry.name}' exists to {purpose}."
        )


__all__ = ["FileDeterminer"]
