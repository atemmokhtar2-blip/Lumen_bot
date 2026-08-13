"""
File Planner — determines every file the project needs before creating
any file (Specification 006).

The :class:`FilePlanner` is a stateless helper that analyses the
:class:`ProjectBlueprint` and the folder map (produced by the
:class:`FolderPlanner`) and determines every file the generated project
needs.  For each file, the planner decides:

* its **name** and **path**,
* its **file type** (Python module, config, markdown, etc.),
* its **purpose** (single responsibility),
* which **building engine** will build it later,
* its **build order** position,
* and its **relationships** with other files/folders.

The planner does **not** write file contents — no code, no functions,
no classes, no database definitions.  It only plans the file's
identity and purpose.

Data source
-----------
The planner reads **only** the :class:`ProjectBlueprint` and the folder
map.  It does not read the user's request or the analysis report.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from ..project_planner.blueprint import (
    InternalComponent,
    ProjectBlueprint,
)
from .naming_engine import NamingEngine
from .structure_map import (
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
    FILE_TYPE_MARKDOWN,
    FILE_TYPE_PYTHON_MODULE,
    FILE_TYPE_PYTHON_PACKAGE,
    FILE_TYPE_REQUIREMENTS,
    FILE_TYPE_TEXT,
    FILE_TYPE_TOML,
    FileEntry,
    FolderEntry,
)


class FilePlanner:
    """Stateless helper that builds the complete file map.

    The planner is the single place that decides which files the project
    will have.  It is called by the :class:`StructureGenerationEngine`
    and returns a list of :class:`FileEntry` objects.
    """

    def plan(self, blueprint: ProjectBlueprint,
             folders: List[FolderEntry],
             root_package: str,
             component_to_folder: Dict[str, str]) -> List[FileEntry]:
        """Build the complete file map from the blueprint and folder map.

        Parameters:
            blueprint: The project blueprint (the only data source).
            folders: The folder map produced by the
                :class:`FolderPlanner`.
            root_package: The root package name.
            component_to_folder: Mapping from component name to folder
                path.

        Returns:
            An ordered list of :class:`FileEntry` objects.  The order
            follows the build sequence: infrastructure → core → database
            → component files → wiring → entry → docs → tests.
        """
        files: List[FileEntry] = []
        folder_map: Dict[str, FolderEntry] = {f.path: f for f in folders}

        # -- root package __init__.py --------------------------------------
        files.append(self._package_init(root_package))

        # -- core files ----------------------------------------------------
        core_path = NamingEngine.join_path(root_package, "core")
        if core_path in folder_map:
            files.append(self._package_init(core_path))
            files.append(self._main_entry(core_path))
            files.append(self._bot_entry(core_path))
            files.append(self._core_init_entry(core_path))
            files.append(self._constants_entry(core_path))
            files.append(self._exceptions_entry(core_path))

        # -- config files --------------------------------------------------
        config_path = NamingEngine.join_path(root_package, "config")
        if config_path in folder_map:
            files.append(self._package_init(config_path))
            files.append(self._config_entry(config_path))
            files.append(self._env_example_entry(config_path))

        # -- database files ------------------------------------------------
        if blueprint.identity.database:
            db_path = NamingEngine.join_path(root_package, "database")
            if db_path in folder_map:
                files.append(self._package_init(db_path))
                files.append(self._db_connection_entry(db_path))
                files.append(self._db_models_entry(db_path))
                files.append(self._db_schema_entry(db_path))

                migrations_path = NamingEngine.join_path(db_path, "migrations")
                if migrations_path in folder_map:
                    files.append(self._package_init(migrations_path))
                    files.append(self._migration_entry(migrations_path))

        # -- component files -----------------------------------------------
        for component in sorted(blueprint.components,
                                 key=lambda c: (c.priority, c.name)):
            file = self._component_files(
                component, component_to_folder, folder_map,
            )
            files.extend(file)

        # -- integrations files --------------------------------------------
        has_integrations = any(
            c.kind == "integration" for c in blueprint.components
        )
        if has_integrations:
            integ_path = NamingEngine.join_path(root_package, "integrations")
            if integ_path in folder_map:
                files.append(self._package_init(integ_path))
                for comp in blueprint.components:
                    if comp.kind == "integration":
                        files.append(self._integration_entry(
                            integ_path, comp,
                        ))

        # -- tests files ---------------------------------------------------
        tests_path = NamingEngine.join_path(root_package, "tests")
        if tests_path in folder_map:
            files.append(self._package_init(tests_path))
            files.append(self._test_main_entry(tests_path))

        # -- docs files ----------------------------------------------------
        docs_path = NamingEngine.join_path(root_package, "docs")
        if docs_path in folder_map:
            files.append(self._readme_entry(root_package))
            files.append(self._docs_readme_entry(docs_path))
            files.append(self._architecture_entry(docs_path))

        # -- project-level files -------------------------------------------
        files.append(self._requirements_entry())
        files.append(self._toml_entry())
        files.append(self._dockerfile_entry())
        files.append(self._dockerignore_entry())
        files.append(self._gitignore_entry())

        # -- record relationships ------------------------------------------
        self._record_relationships(files, folders, root_package)

        return files

    # ------------------------------------------------------------------#
    # Individual file creators
    # ------------------------------------------------------------------#

    def _package_init(self, folder_path: str) -> FileEntry:
        """Create a __init__.py file entry for a package folder."""
        return FileEntry(
            name="__init__.py",
            path=NamingEngine.join_path(folder_path, "__init__.py"),
            file_type=FILE_TYPE_PYTHON_PACKAGE,
            purpose=f"Package init for {folder_path}.",
            folder=folder_path,
            building_engine="file_builder",
            build_order=BUILD_ORDER_INFRASTRUCTURE,
            contains_code=True,
        )

    def _main_entry(self, core_path: str) -> FileEntry:
        return FileEntry(
            name="main.py",
            path=NamingEngine.join_path(core_path, "main.py"),
            file_type=FILE_TYPE_PYTHON_MODULE,
            purpose="Bot entry point — initialises and starts the bot.",
            folder=core_path,
            building_engine="code_generator",
            build_order=BUILD_ORDER_ENTRY,
            source_component="core",
            contains_code=True,
        )

    def _bot_entry(self, core_path: str) -> FileEntry:
        return FileEntry(
            name="bot.py",
            path=NamingEngine.join_path(core_path, "bot.py"),
            file_type=FILE_TYPE_PYTHON_MODULE,
            purpose="Bot application setup and configuration.",
            folder=core_path,
            building_engine="code_generator",
            build_order=BUILD_ORDER_CORE,
            source_component="core",
            contains_code=True,
        )

    def _core_init_entry(self, core_path: str) -> FileEntry:
        return FileEntry(
            name="config.py",
            path=NamingEngine.join_path(core_path, "config.py"),
            file_type=FILE_TYPE_PYTHON_MODULE,
            purpose="Core configuration loader for the bot.",
            folder=core_path,
            building_engine="code_generator",
            build_order=BUILD_ORDER_CORE,
            source_component="core",
            contains_code=True,
        )

    def _constants_entry(self, core_path: str) -> FileEntry:
        return FileEntry(
            name="constants.py",
            path=NamingEngine.join_path(core_path, "constants.py"),
            file_type=FILE_TYPE_PYTHON_MODULE,
            purpose="Shared constants used across the bot.",
            folder=core_path,
            building_engine="code_generator",
            build_order=BUILD_ORDER_CORE,
            source_component="core",
            contains_code=True,
        )

    def _exceptions_entry(self, core_path: str) -> FileEntry:
        return FileEntry(
            name="exceptions.py",
            path=NamingEngine.join_path(core_path, "exceptions.py"),
            file_type=FILE_TYPE_PYTHON_MODULE,
            purpose="Custom exception classes for the bot.",
            folder=core_path,
            building_engine="code_generator",
            build_order=BUILD_ORDER_CORE,
            source_component="core",
            contains_code=True,
        )

    def _config_entry(self, config_path: str) -> FileEntry:
        return FileEntry(
            name="settings.yaml",
            path=NamingEngine.join_path(config_path, "settings.yaml"),
            file_type=FILE_TYPE_TEXT,
            purpose="Project configuration settings in YAML format.",
            folder=config_path,
            building_engine="file_builder",
            build_order=BUILD_ORDER_INFRASTRUCTURE,
            contains_code=False,
        )

    def _env_example_entry(self, config_path: str) -> FileEntry:
        return FileEntry(
            name=".env.example",
            path=NamingEngine.join_path(config_path, ".env.example"),
            file_type=FILE_TYPE_ENV,
            purpose="Example environment variables file.",
            folder=config_path,
            building_engine="file_builder",
            build_order=BUILD_ORDER_INFRASTRUCTURE,
            contains_code=False,
        )

    def _db_connection_entry(self, db_path: str) -> FileEntry:
        return FileEntry(
            name="connection.py",
            path=NamingEngine.join_path(db_path, "connection.py"),
            file_type=FILE_TYPE_PYTHON_MODULE,
            purpose="Database connection setup and session management.",
            folder=db_path,
            building_engine="database_engine",
            build_order=BUILD_ORDER_DATABASE,
            source_component="database",
            contains_code=True,
        )

    def _db_models_entry(self, db_path: str) -> FileEntry:
        return FileEntry(
            name="models.py",
            path=NamingEngine.join_path(db_path, "models.py"),
            file_type=FILE_TYPE_PYTHON_MODULE,
            purpose="Database model definitions.",
            folder=db_path,
            building_engine="database_engine",
            build_order=BUILD_ORDER_DATABASE,
            source_component="database",
            contains_code=True,
        )

    def _db_schema_entry(self, db_path: str) -> FileEntry:
        return FileEntry(
            name="schema.py",
            path=NamingEngine.join_path(db_path, "schema.py"),
            file_type=FILE_TYPE_PYTHON_MODULE,
            purpose="Database schema definitions and helpers.",
            folder=db_path,
            building_engine="database_engine",
            build_order=BUILD_ORDER_DATABASE,
            source_component="database",
            contains_code=True,
        )

    def _migration_entry(self, migrations_path: str) -> FileEntry:
        return FileEntry(
            name="initial_migration.py",
            path=NamingEngine.join_path(migrations_path, "initial_migration.py"),
            file_type=FILE_TYPE_PYTHON_MODULE,
            purpose="Initial database migration script.",
            folder=migrations_path,
            building_engine="database_engine",
            build_order=BUILD_ORDER_DATABASE,
            source_component="database",
            contains_code=True,
        )

    def _component_files(
        self,
        component: InternalComponent,
        component_to_folder: Dict[str, str],
        folder_map: Dict[str, FolderEntry],
    ) -> List[FileEntry]:
        """Create file entries for a single component.

        Each feature component gets a __init__.py and a main module file.
        Infrastructure and integration components are handled by the
        dedicated infrastructure/integration folders.
        """
        files: List[FileEntry] = []

        # Skip components handled by dedicated folders.
        if component.kind in ("infrastructure", "integration"):
            return files
        if component.name in ("database", "db", "database_manager",
                               "logger", "logging", "log"):
            return files

        folder_path = component_to_folder.get(component.name)
        if folder_path is None or folder_path not in folder_map:
            return files

        # Package init.
        files.append(self._package_init(folder_path))

        # Main module for this component.
        module_name = NamingEngine.python_module_name(component.name)
        module_file = FileEntry(
            name=f"{module_name}.py",
            path=NamingEngine.join_path(folder_path, f"{module_name}.py"),
            file_type=FILE_TYPE_PYTHON_MODULE,
            purpose=(
                component.description
                if component.description
                else f"Implements the {component.display_name or component.name} component."
            ),
            folder=folder_path,
            building_engine="code_generator",
            build_order=BUILD_ORDER_FEATURES,
            source_component=component.name,
            contains_code=True,
        )
        files.append(module_file)

        return files

    def _integration_entry(self, integ_path: str,
                            component: InternalComponent) -> FileEntry:
        module_name = NamingEngine.python_module_name(component.name)
        return FileEntry(
            name=f"{module_name}.py",
            path=NamingEngine.join_path(integ_path, f"{module_name}.py"),
            file_type=FILE_TYPE_PYTHON_MODULE,
            purpose=(
                component.description
                if component.description
                else f"Integration for {component.display_name or component.name}."
            ),
            folder=integ_path,
            building_engine="code_generator",
            build_order=BUILD_ORDER_FEATURES,
            source_component=component.name,
            contains_code=True,
        )

    def _test_main_entry(self, tests_path: str) -> FileEntry:
        return FileEntry(
            name="test_main.py",
            path=NamingEngine.join_path(tests_path, "test_main.py"),
            file_type=FILE_TYPE_PYTHON_MODULE,
            purpose="Tests for the bot's main entry point.",
            folder=tests_path,
            building_engine="file_builder",
            build_order=BUILD_ORDER_TESTS,
            contains_code=True,
        )

    def _readme_entry(self, root_package: str) -> FileEntry:
        return FileEntry(
            name="README.md",
            path="README.md",
            file_type=FILE_TYPE_MARKDOWN,
            purpose="Project README with setup and usage instructions.",
            folder="",
            building_engine="file_builder",
            build_order=BUILD_ORDER_DOCS,
            contains_code=False,
        )

    def _docs_readme_entry(self, docs_path: str) -> FileEntry:
        return FileEntry(
            name="README.md",
            path=NamingEngine.join_path(docs_path, "README.md"),
            file_type=FILE_TYPE_MARKDOWN,
            purpose="Documentation index.",
            folder=docs_path,
            building_engine="file_builder",
            build_order=BUILD_ORDER_DOCS,
            contains_code=False,
        )

    def _architecture_entry(self, docs_path: str) -> FileEntry:
        return FileEntry(
            name="ARCHITECTURE.md",
            path=NamingEngine.join_path(docs_path, "ARCHITECTURE.md"),
            file_type=FILE_TYPE_MARKDOWN,
            purpose="Project architecture documentation.",
            folder=docs_path,
            building_engine="file_builder",
            build_order=BUILD_ORDER_DOCS,
            contains_code=False,
        )

    def _requirements_entry(self) -> FileEntry:
        return FileEntry(
            name="requirements.txt",
            path="requirements.txt",
            file_type=FILE_TYPE_REQUIREMENTS,
            purpose="Python dependencies for the project.",
            folder="",
            building_engine="file_builder",
            build_order=BUILD_ORDER_INFRASTRUCTURE,
            contains_code=False,
        )

    def _toml_entry(self) -> FileEntry:
        return FileEntry(
            name="pyproject.toml",
            path="pyproject.toml",
            file_type=FILE_TYPE_TOML,
            purpose="Python project configuration (build, linting, etc.).",
            folder="",
            building_engine="file_builder",
            build_order=BUILD_ORDER_INFRASTRUCTURE,
            contains_code=False,
        )

    def _dockerfile_entry(self) -> FileEntry:
        return FileEntry(
            name="Dockerfile",
            path="Dockerfile",
            file_type=FILE_TYPE_DOCKERFILE,
            purpose="Docker container definition for the bot.",
            folder="",
            building_engine="file_builder",
            build_order=BUILD_ORDER_INFRASTRUCTURE,
            contains_code=False,
        )

    def _dockerignore_entry(self) -> FileEntry:
        return FileEntry(
            name=".dockerignore",
            path=".dockerignore",
            file_type=FILE_TYPE_TEXT,
            purpose="Files to exclude from the Docker build context.",
            folder="",
            building_engine="file_builder",
            build_order=BUILD_ORDER_INFRASTRUCTURE,
            contains_code=False,
        )

    def _gitignore_entry(self) -> FileEntry:
        return FileEntry(
            name=".gitignore",
            path=".gitignore",
            file_type=FILE_TYPE_TEXT,
            purpose="Files to exclude from version control.",
            folder="",
            building_engine="file_builder",
            build_order=BUILD_ORDER_INFRASTRUCTURE,
            contains_code=False,
        )

    # ------------------------------------------------------------------#
    # Relationship recording
    # ------------------------------------------------------------------#

    @staticmethod
    def _record_relationships(files: List[FileEntry],
                               folders: List[FolderEntry],
                               root_package: str) -> None:
        """Record relationships between files and their folders.

        Each file gets a ``stored_in`` relationship to its folder.  The
        main.py file gets a ``imports`` relationship to the bot module.
        """
        folder_paths = {f.path for f in folders}

        for file in files:
            if file.folder:
                file.add_relationship(
                    target=file.folder,
                    kind="stored_in",
                    description=f"{file.name} is stored in {file.folder}.",
                )

            # main.py depends on bot.py
            if file.name == "main.py":
                bot_path = NamingEngine.join_path(
                    NamingEngine.parent_path(file.path), "bot.py"
                )
                if any(f.path == bot_path for f in files):
                    file.add_relationship(
                        target=bot_path,
                        kind="imports",
                        description="main.py imports the bot application.",
                    )

            # Component modules depend on their package init
            if file.folder and file.name != "__init__.py":
                init_path = NamingEngine.join_path(file.folder, "__init__.py")
                file.add_relationship(
                    target=init_path,
                    kind="depends_on",
                    description=(
                        f"{file.name} is part of the package at "
                        f"{file.folder}."
                    ),
                )


__all__ = ["FilePlanner"]
