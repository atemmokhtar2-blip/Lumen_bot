"""
Project Structure Generation Engine (Specification 006).

The :class:`StructureGenerationEngine` is the first engine that starts
building the project **physically**.  It creates the professional
project structure — the folder/file map — but it does **not** write
code, functions, classes, or databases.  Its sole function is to create
the project structure (folder/file map) that later engines will fill.

Data source
-----------
The engine reads **only** two artefacts from the generation context:

1. ``project_blueprint`` — produced by the
   :class:`~telegram_bot_engine.engines.generators.project_planner.ProjectPlanningEngine`.
2. ``blueprint_validation_report`` — produced by the
   :class:`~telegram_bot_engine.engines.generators.blueprint_validator.BlueprintValidatorEngine`.

It is **forbidden** from reading the user's request or the analysis
report.  It does not analyse the project itself — it uses the
blueprint's structure, components, and the validation report's verdict
to build the structure map.

Responsibility
--------------
* Analyse the blueprint to determine all components, packages,
  modules, and resources.
* Build a complete folder map (name, purpose, parent, subfolders,
  relationships) before creating any folder.
* Build a complete file map (name, file type, purpose, building engine,
  relationships) before creating any file.
* Validate the structure map (no duplicates, no conflicts, no empty
  folders without reason, no files without responsibility).
* Produce a :class:`ProjectStructureMap` stored as the
  ``project_structure_map`` artefact.

What this engine does NOT do
----------------------------
* It does **not** write code inside files.
* It does **not** create databases.
* It does **not** build bot logic.
* It does **not** add files not in the Project Structure Map.
* It does **not** physically create the folders on disk — that is the
  :class:`DirectoryBuilder`'s job, which is called by the engine when
  appropriate.  However, per Specification 006, the primary output is
  the *map*, not the physical directories.

Output
------
The final output is a
:class:`ProjectStructureMap`, stored in the context as the
``project_structure_map`` artefact.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from ..blueprint_validator.validation_report import (
    BlueprintValidationReport,
    STATUS_APPROVED,
    STATUS_REJECTED,
)
from ..project_planner.blueprint import ProjectBlueprint
from .file_planner import FilePlanner
from .folder_planner import FolderPlanner
from .naming_engine import NamingEngine
from .structure_map import (
    BuildOrderEntry,
    ProjectStructureMap,
)
from .structure_validator import StructureValidator


class StructureGenerationEngine(BaseEngine):
    """The engine that builds the project structure map.

    This engine is the first engine that physically describes the
    project.  It reads the ``project_blueprint`` and
    ``blueprint_validation_report`` artefacts, analyses the blueprint's
    components, builds a complete folder and file map, validates it, and
    produces a :class:`ProjectStructureMap` stored as the
    ``project_structure_map`` artefact.

    The engine is forbidden from reading the user's request or the
    analysis report.  It reads only the blueprint and the validation
    report.
    """

    def __init__(self) -> None:
        super().__init__(
            name="structure_generator",
            version="1.0.0",
            description=(
                "Builds the project structure map (folders and files) "
                "from the Project Blueprint and Blueprint Validation "
                "Report.  Does not write code, functions, classes, or "
                "databases.  Produces a ProjectStructureMap artefact."
            ),
            tags=["generation", "structure"],
            metadata={"phase": "create_structure"},
        )
        self._naming = NamingEngine()
        self._folder_planner = FolderPlanner()
        self._file_planner = FilePlanner()
        self._validator = StructureValidator()

    # -----------------------------------------------------------------#
    # Main entry point
    # -----------------------------------------------------------------#

    def execute(self, context: GenerationContext) -> StageResult:
        """Build the project structure map from the blueprint.

        Steps:
            1. Obtain the blueprint and validation report from the context.
            2. Determine the root package name.
            3. Build the complete folder map.
            4. Build the component-to-folder mapping.
            5. Build the complete file map.
            6. Compute the build order.
            7. Validate the structure map.
            8. Store the structure map in the context.
        """
        gen_start = time.perf_counter()

        # Step 1: obtain the blueprint and validation report.
        blueprint = context.get("project_blueprint")
        if blueprint is None:
            return self.failed([
                "No 'project_blueprint' artefact found. The Structure "
                "Generation Engine requires the Project Planning Engine "
                "to have run first. The structure engine does not read "
                "the raw request."
            ])

        validation_report = context.get("blueprint_validation_report")
        if validation_report is None:
            return self.failed([
                "No 'blueprint_validation_report' artefact found. The "
                "Structure Generation Engine requires the Blueprint "
                "Validator Engine to have run first."
            ])

        self._log.info(
            "Starting structure generation",
            {
                "blueprint_name": blueprint.identity.name,
                "components": len(blueprint.components),
                "features": len(blueprint.features),
                "validation_status": (
                    validation_report.status
                    if isinstance(validation_report, BlueprintValidationReport)
                    else "unknown"
                ),
            },
        )

        # Step 2: determine the root package name.
        root_package = self._determine_root_package(blueprint)
        self._log.info(
            "Root package determined",
            {"root_package": root_package},
        )

        # Step 3: build the complete folder map.
        folders = self._folder_planner.plan(blueprint, root_package)
        self._log.info(
            "Folder map built",
            {"folder_count": len(folders)},
        )

        # Step 4: build the component-to-folder mapping.
        component_to_folder = self._build_component_to_folder(
            blueprint, folders, root_package,
        )

        # Step 5: build the complete file map.
        files = self._file_planner.plan(
            blueprint, folders, root_package, component_to_folder,
        )
        self._log.info(
            "File map built",
            {"file_count": len(files)},
        )

        # Step 6: compute the build order.
        build_order = self._compute_build_order(folders, files)
        self._log.info(
            "Build order computed",
            {"entries": len(build_order)},
        )

        # Build the structure map.
        validation_status = (
            validation_report.status
            if isinstance(validation_report, BlueprintValidationReport)
            else "unknown"
        )
        structure_map = ProjectStructureMap(
            project_name=blueprint.identity.name or root_package,
            root_path=root_package,
            folders=folders,
            files=files,
            build_order=build_order,
            source_blueprint=blueprint.identity.name or "unnamed",
            validation_status=validation_status,
            component_to_folder=component_to_folder,
        )

        # Step 7: validate the structure map.
        validation = self._validator.validate(structure_map)
        self._log.info(
            "Structure validation complete",
            {
                "valid": validation.valid,
                "errors": validation.error_count,
                "warnings": validation.warning_count,
            },
        )

        if validation.has_errors:
            error_messages = [
                f"[{issue.code}] {issue.message}"
                for issue in validation.issues
                if issue.severity == "error"
            ]
            structure_map.warnings = [
                issue.message for issue in validation.issues
                if issue.severity == "warning"
            ]
            return self.failed(
                errors=error_messages,
                outputs={"project_structure_map": structure_map},
                warnings=structure_map.warnings,
            )

        # Record warnings in the structure map.
        structure_map.warnings = [
            issue.message for issue in validation.issues
            if issue.severity == "warning"
        ]

        # Build a summary.
        total_duration_ms = (time.perf_counter() - gen_start) * 1000
        structure_map.summary = self._build_summary(
            structure_map, total_duration_ms,
        )
        structure_map.notes.append(
            f"Structure generated at "
            f"{datetime.now(timezone.utc).isoformat()}."
        )
        structure_map.notes.append(
            f"Source blueprint: {structure_map.source_blueprint}."
        )
        structure_map.notes.append(
            f"Validation status: {structure_map.validation_status}."
        )

        # Step 8: store the structure map in the context.
        context.set("project_structure_map", structure_map)
        context.metadata["project_structure_map"] = structure_map

        self._log.info(
            "Structure generation complete",
            {
                "project_name": structure_map.project_name,
                "folders": structure_map.folder_count,
                "files": structure_map.file_count,
                "build_order_entries": len(structure_map.build_order),
                "validation_warnings": len(structure_map.warnings),
                "duration_ms": round(total_duration_ms, 2),
            },
        )

        return self.ok(
            outputs={"project_structure_map": structure_map},
            metadata={
                "project_name": structure_map.project_name,
                "root_path": structure_map.root_path,
                "folder_count": structure_map.folder_count,
                "file_count": structure_map.file_count,
                "validation_warnings": len(structure_map.warnings),
                "duration_ms": round(total_duration_ms, 2),
            },
        )

    # -----------------------------------------------------------------#
    # Helpers
    # -----------------------------------------------------------------#

    def _determine_root_package(self, blueprint: ProjectBlueprint) -> str:
        """Determine the root package name from the blueprint identity."""
        if blueprint.identity.name:
            return self._naming.root_package_name(blueprint.identity.name)
        if blueprint.structure.root:
            return self._naming.root_package_name(blueprint.structure.root)
        return "telegram_bot"

    @staticmethod
    def _build_component_to_folder(blueprint: ProjectBlueprint,
                                     folders: List,
                                     root_package: str) -> Dict[str, str]:
        """Build a mapping from component name to folder path.

        Each feature component is mapped to its folder in the structure.
        Infrastructure, integration, database, and logger components are
        mapped to their dedicated folders.
        """
        from .naming_engine import NamingEngine as _NE

        mapping: Dict[str, str] = {}
        folder_paths = {f.path for f in folders}

        for component in blueprint.components:
            if component.kind in ("infrastructure", "integration"):
                continue
            if component.name in ("database", "db", "database_manager",
                                    "logger", "logging", "log"):
                continue

            folder_name = _NE.folder_name(component.name)
            # Try both the direct path and the components/ path.
            direct_path = _NE.join_path(root_package, folder_name)
            components_path = _NE.join_path(
                root_package, "components", folder_name,
            )

            if direct_path in folder_paths:
                mapping[component.name] = direct_path
            elif components_path in folder_paths:
                mapping[component.name] = components_path
            else:
                # Search by matching the last segment.
                for folder_path in folder_paths:
                    if folder_path.split("/")[-1] == folder_name:
                        mapping[component.name] = folder_path
                        break

        return mapping

    @staticmethod
    def _compute_build_order(folders: List, files: List) -> List[BuildOrderEntry]:
        """Compute the build order for all folders and files.

        Folders are built first (sorted by build_order, then path).
        Files are built after their containing folder (sorted by
        build_order, then path).
        """
        entries: List[BuildOrderEntry] = []
        position = 0

        # Folders first, sorted by build_order then path.
        for folder in sorted(folders, key=lambda f: (f.build_order, f.path)):
            entries.append(BuildOrderEntry(
                position=position,
                path=folder.path,
                kind="folder",
                building_engine="directory_builder",
            ))
            position += 1

        # Files after, sorted by build_order then path.
        for file in sorted(files, key=lambda f: (f.build_order, f.path)):
            entries.append(BuildOrderEntry(
                position=position,
                path=file.path,
                kind="file",
                building_engine=file.building_engine,
            ))
            position += 1

        return entries

    @staticmethod
    def _build_summary(structure_map: ProjectStructureMap,
                       duration_ms: float) -> str:
        """Build a human-readable summary of the structure map."""
        return (
            f"Project '{structure_map.project_name}': "
            f"{structure_map.folder_count} folder(s), "
            f"{structure_map.file_count} file(s), "
            f"{len(structure_map.build_order)} build-order entries. "
            f"Generated in {round(duration_ms, 2)} ms."
        )


__all__ = ["StructureGenerationEngine"]
