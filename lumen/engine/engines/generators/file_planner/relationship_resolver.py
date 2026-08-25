"""
Relationship Resolver — determines the relationships and dependencies
between planned files (Specification 008).

The :class:`RelationshipResolver` is a stateless helper that the
:class:`FileGenerationPlanningEngine` calls during the *relationship*
phase.  It takes the list of :class:`FilePlanEntry` objects produced by
the :class:`FileDeterminer` and:

1. derives file-to-file dependencies from the component dependency
   graph (if file A belongs to a component that depends on file B's
   component, then file A depends on file B),
2. records the reverse ``depended_by`` links on each file,
3. produces a list of :class:`FileRelationship` objects describing the
   wiring between files,
4. handles package-init (``__init__.py``) relationships — a package
   init file is depended on by all modules in its folder.

The resolver does **not** create new files.  It only wires the existing
planned files together by recording their dependency relationships.

Data source
-----------
The resolver reads **only**:

1. the list of :class:`FilePlanEntry` objects (from the
   :class:`FileDeterminer`), and
2. the :class:`ComponentRegistry` (for the component dependency graph).

It does **not** read the user's request.
"""

from __future__ import annotations

from typing import Dict, List, Set, Tuple

from ..component_detector.registry import (
    ComponentRegistry,
    DetectedComponent,
)
from .plan_data import FilePlanEntry, FileRelationship


class RelationshipResolver:
    """Stateless helper that resolves file relationships and dependencies.

    The resolver is called by the
    :class:`FileGenerationPlanningEngine` after the
    :class:`FileDeterminer` has produced the list of planned files.
    It wires the files together by recording their dependency
    relationships.

    The resolver is **pure**: it does not modify the component
    registry.  It may update the ``depends_on`` and ``depended_by``
    lists on the :class:`FilePlanEntry` objects (these are the plan's
    own data, not the registry's).
    """

    def resolve(
        self,
        files: List[FilePlanEntry],
        registry: ComponentRegistry,
    ) -> Tuple[List[FileRelationship], List[str]]:
        """Resolve the relationships between planned files.

        Parameters:
            files: The list of planned file entries.
            registry: The component registry (for the component
                dependency graph).

        Returns:
            A tuple ``(relationships, warnings)`` where:

            * ``relationships`` is the list of
              :class:`FileRelationship` objects.
            * ``warnings`` is a list of warning messages about
              dangling file dependencies or missing components.
        """
        relationships: List[FileRelationship] = []
        warnings: List[str] = []

        # Build a path → file lookup.
        files_by_path: Dict[str, FilePlanEntry] = {
            f.path: f for f in files
        }

        # Build a component-name → list-of-files lookup.
        files_by_component: Dict[str, List[FilePlanEntry]] = {}
        for f in files:
            if f.source_component:
                files_by_component.setdefault(
                    f.source_component, [],
                ).append(f)

        # Build a component-name → component lookup from the registry.
        comp_by_name: Dict[str, DetectedComponent] = {
            c.name: c for c in registry.components
        }

        # -- Component-based dependencies ----------------------------------
        # If component A depends on component B, then every file
        # belonging to A depends on the primary file of B (the first
        # file in B's list).

        for f in files:
            if not f.source_component:
                continue

            comp = comp_by_name.get(f.source_component)
            if comp is None:
                continue

            for dep_name in comp.depends_on:
                dep_files = files_by_component.get(dep_name, [])
                if not dep_files:
                    # The dependency component has no files — this is
                    # a potential issue but not a hard error.
                    warnings.append(
                        f"File '{f.path}' belongs to component "
                        f"'{f.source_component}' which depends on "
                        f"'{dep_name}', but '{dep_name}' has no "
                        f"planned files."
                    )
                    continue

                # Depend on the first file of the dependency component.
                dep_file = dep_files[0]
                if dep_file.path == f.path:
                    continue  # don't self-depend

                if dep_file.path not in f.depends_on:
                    f.add_dependency(dep_file.path)
                if f.path not in dep_file.depended_by:
                    dep_file.add_dependent(f.path)

                relationships.append(FileRelationship(
                    source=f.path,
                    target=dep_file.path,
                    kind="depends_on",
                    description=(
                        f"File '{f.name}' depends on "
                        f"'{dep_file.name}' (component "
                        f"'{f.source_component}' depends on "
                        f"'{dep_name}')."
                    ),
                ))

        # -- Package-init relationships -------------------------------------
        # A package __init__.py file is depended on by all other
        # modules in the same folder.  This ensures the init is
        # generated before the modules.

        self._resolve_package_init(files, files_by_path, relationships)

        return relationships, warnings

    # -----------------------------------------------------------------#
    # Internal helpers
    # -----------------------------------------------------------------#

    @staticmethod
    def _resolve_package_init(
        files: List[FilePlanEntry],
        files_by_path: Dict[str, FilePlanEntry],
        relationships: List[FileRelationship],
    ) -> None:
        """Wire package __init__.py files to the modules in their folder.

        Each ``__init__.py`` file is depended on by all other
        modules in the same folder.  This ensures the init is created
        first when the folder is materialised.
        """
        # Group files by folder.
        files_by_folder: Dict[str, List[FilePlanEntry]] = {}
        for f in files:
            folder = f.folder or ""
            files_by_folder.setdefault(folder, []).append(f)

        for folder, folder_files in files_by_folder.items():
            # Find the __init__.py in this folder.
            init_file: FilePlanEntry = None  # type: ignore[assignment]
            for f in folder_files:
                if f.name == "__init__.py":
                    init_file = f
                    break

            if init_file is None:
                continue

            # Wire all other modules in the folder to depend on the
            # init file.
            for f in folder_files:
                if f.path == init_file.path:
                    continue
                if not f.path.endswith(".py"):
                    continue  # only Python modules depend on the init

                if init_file.path not in f.depends_on:
                    f.add_dependency(init_file.path)
                if f.path not in init_file.depended_by:
                    init_file.add_dependent(f.path)

                relationships.append(FileRelationship(
                    source=f.path,
                    target=init_file.path,
                    kind="imports",
                    description=(
                        f"Module '{f.name}' imports the package "
                        f"init '{init_file.name}' in folder "
                        f"'{folder}'."
                    ),
                ))


__all__ = ["RelationshipResolver"]
