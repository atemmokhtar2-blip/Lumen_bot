"""
Folder Planner — builds a complete folder map before any folder is
created (Specification 006).

The :class:`FolderPlanner` is a stateless helper that analyses the
:class:`ProjectBlueprint` and determines every folder the generated
project needs.  It follows the specification's architecture rules:

* **Single responsibility per folder.**  Each folder has exactly one
  purpose.
* **No unnecessary folders for small projects.**  Only the folders the
  project actually needs are created.
* **Split large projects into independent packages.**  When the
  blueprint contains many components, components are grouped into
  independent package folders.
* **Scalable.**  Folders are marked as scalable so they can grow
  without restructuring.

The planner returns a list of :class:`FolderEntry` objects with their
paths, purposes, parent relationships, and subfolder lists.  It does
**not** create the folders on disk — that is the
:class:`DirectoryBuilder`'s job, performed later by the engine.

Data source
-----------
The planner reads **only** the :class:`ProjectBlueprint`.  It does not
read the user's request or the analysis report.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ..project_planner.blueprint import (
    InternalComponent,
    ProjectBlueprint,
)
from .naming_engine import NamingEngine
from .structure_map import (
    BUILD_ORDER_CORE,
    BUILD_ORDER_DATABASE,
    BUILD_ORDER_DOCS,
    BUILD_ORDER_FEATURES,
    BUILD_ORDER_INFRASTRUCTURE,
    BUILD_ORDER_TESTS,
    FolderEntry,
)


# Threshold: number of components above which the project is considered
# "large" and components are split into independent package folders.
_LARGE_PROJECT_THRESHOLD = 8

# Component kinds that map to infrastructure folders.
_INFRASTRUCTURE_KINDS = frozenset({"infrastructure"})

# Component kinds that map to integration folders.
_INTEGRATION_KINDS = frozenset({"integration"})


class FolderPlanner:
    """Stateless helper that builds the complete folder map.

    The planner is the single place that decides which folders the
    project will have.  It is called by the
    :class:`StructureGenerationEngine` and returns a list of
    :class:`FolderEntry` objects.
    """

    def plan(self, blueprint: ProjectBlueprint,
             root_package: str) -> List[FolderEntry]:
        """Build the complete folder map from the blueprint.

        Parameters:
            blueprint: The project blueprint (the only data source).
            root_package: The root package name (the project's top-level
                directory).

        Returns:
            An ordered list of :class:`FolderEntry` objects.  The
            order follows the build sequence: root → infrastructure →
            component folders.
        """
        folders: List[FolderEntry] = []
        component_to_folder: Dict[str, str] = {}

        is_large = len(blueprint.components) >= _LARGE_PROJECT_THRESHOLD

        # -- root package -------------------------------------------------
        root_folder = FolderEntry(
            name=root_package,
            path=root_package,
            purpose="Root package for the generated Telegram bot.",
            parent="",
            build_order=BUILD_ORDER_INFRASTRUCTURE,
            reason="Every project needs a root package.",
        )
        folders.append(root_folder)

        # -- core/infrastructure folder -----------------------------------
        core_path = NamingEngine.join_path(root_package, "core")
        core_folder = FolderEntry(
            name="core",
            path=core_path,
            purpose="Core bot logic, entry point, and shared utilities.",
            parent=root_package,
            build_order=BUILD_ORDER_CORE,
            reason="Holds the main bot entry point and core logic.",
        )
        folders.append(core_folder)

        # -- database folder (only when the project has a database) -----
        if blueprint.identity.database:
            db_path = NamingEngine.join_path(root_package, "database")
            db_folder = FolderEntry(
                name="database",
                path=db_path,
                purpose="Database connection, models, and migrations.",
                parent=root_package,
                build_order=BUILD_ORDER_DATABASE,
                reason=f"Blueprint specifies database: {blueprint.identity.database}.",
            )
            folders.append(db_folder)

            migrations_path = NamingEngine.join_path(db_path, "migrations")
            migrations_folder = FolderEntry(
                name="migrations",
                path=migrations_path,
                purpose="Database migration scripts.",
                parent=db_path,
                build_order=BUILD_ORDER_DATABASE,
                reason="Migrations are separated from models.",
            )
            folders.append(migrations_folder)
            db_folder.subfolders.append("migrations")

        # -- component folders --------------------------------------------
        component_folders = self._plan_component_folders(
            blueprint, root_package, is_large,
        )
        for folder, comp_name in component_folders:
            folders.append(folder)
            component_to_folder[comp_name] = folder.path

        # -- config folder (always present for a real project) -----------
        config_path = NamingEngine.join_path(root_package, "config")
        config_folder = FolderEntry(
            name="config",
            path=config_path,
            purpose="Configuration files and settings.",
            parent=root_package,
            build_order=BUILD_ORDER_INFRASTRUCTURE,
            reason="Every project needs a dedicated config location.",
        )
        folders.append(config_folder)

        # -- integrations folder (only when integrations exist) ---------
        has_integrations = any(
            c.kind in _INTEGRATION_KINDS for c in blueprint.components
        )
        if has_integrations:
            integ_path = NamingEngine.join_path(root_package, "integrations")
            integ_folder = FolderEntry(
                name="integrations",
                path=integ_path,
                purpose="External service integrations and API clients.",
                parent=root_package,
                build_order=BUILD_ORDER_FEATURES,
                reason="Blueprint contains integration components.",
            )
            folders.append(integ_folder)

        # -- tests folder (always present) --------------------------------
        tests_path = NamingEngine.join_path(root_package, "tests")
        tests_folder = FolderEntry(
            name="tests",
            path=tests_path,
            purpose="Unit and integration tests for the bot.",
            parent=root_package,
            build_order=BUILD_ORDER_TESTS,
            reason="Every project needs a tests directory.",
        )
        folders.append(tests_folder)

        # -- docs folder (always present) ---------------------------------
        docs_path = NamingEngine.join_path(root_package, "docs")
        docs_folder = FolderEntry(
            name="docs",
            path=docs_path,
            purpose="Project documentation.",
            parent=root_package,
            build_order=BUILD_ORDER_DOCS,
            reason="Every project needs a documentation directory.",
        )
        folders.append(docs_folder)

        # -- record relationships -----------------------------------------
        self._record_relationships(folders, root_package)

        return folders

    # ------------------------------------------------------------------#
    # Component folder planning
    # ------------------------------------------------------------------#

    def _plan_component_folders(
        self,
        blueprint: ProjectBlueprint,
        root_package: str,
        is_large: bool,
    ) -> List[Tuple[FolderEntry, str]]:
        """Plan a folder for each relevant internal component.

        For small projects, component folders are placed directly under
        the root package.  For large projects, they are grouped under
        ``components/`` to keep the root clean.
        """
        results: List[Tuple[FolderEntry, str]] = []
        # Sort components by priority (lower first) then by name.
        components = sorted(
            blueprint.components,
            key=lambda c: (c.priority, c.name),
        )

        for component in components:
            folder = self._folder_for_component(
                component, root_package, is_large,
            )
            if folder is not None:
                results.append((folder, component.name))

        return results

    def _folder_for_component(
        self,
        component: InternalComponent,
        root_package: str,
        is_large: bool,
    ) -> Optional[FolderEntry]:
        """Create a folder entry for a single component.

        Infrastructure and integration components are handled by the
        dedicated infrastructure/integration folders.  Only feature
        components get their own folders.
        """
        # Skip components that are handled by dedicated folders.
        if component.kind in _INFRASTRUCTURE_KINDS:
            return None
        if component.kind in _INTEGRATION_KINDS:
            return None
        # Skip database components — they live in the database/ folder.
        if component.name in ("database", "db", "database_manager"):
            return None
        # Skip logger/logging components — they are infrastructure.
        if component.name in ("logger", "logging", "log"):
            return None

        folder_name = NamingEngine.folder_name(component.name)

        if is_large:
            parent_path = NamingEngine.join_path(root_package, "components")
            folder_path = NamingEngine.join_path(parent_path, folder_name)
        else:
            parent_path = root_package
            folder_path = NamingEngine.join_path(root_package, folder_name)

        purpose = (
            component.description
            if component.description
            else f"Holds the {component.display_name or component.name} component."
        )

        return FolderEntry(
            name=folder_name,
            path=folder_path,
            purpose=purpose,
            parent=parent_path,
            build_order=BUILD_ORDER_FEATURES,
            reason=(
                f"Component '{component.name}' (kind: {component.kind}, "
                f"priority: {component.priority})."
            ),
        )

    # ------------------------------------------------------------------#
    # Relationship recording
    # ------------------------------------------------------------------#

    @staticmethod
    def _record_relationships(folders: List[FolderEntry],
                               root_package: str) -> None:
        """Record parent-child relationships between folders.

        Each folder gets a ``contains`` relationship to its parent, and
        the root folder gets a ``contains`` relationship to each
        top-level folder.
        """
        root = None
        for f in folders:
            if f.path == root_package:
                root = f
                break

        for f in folders:
            if f.parent and f.parent != root_package:
                # Subfolder relationship.
                parent_folder = next(
                    (pf for pf in folders if pf.path == f.parent),
                    None,
                )
                if parent_folder:
                    parent_folder.subfolders.append(f.name)
                    f.add_relationship(
                        target=f.parent,
                        kind="child_of",
                        description=f"{f.name} is a subfolder of {f.parent}.",
                    )
            elif f.parent == root_package and root is not None:
                root.subfolders.append(f.name)
                f.add_relationship(
                    target=root_package,
                    kind="child_of",
                    description=f"{f.name} is a top-level folder under {root_package}.",
                )


__all__ = ["FolderPlanner"]
