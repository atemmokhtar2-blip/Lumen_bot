"""
Type Detector — classifies blueprint components and structure-map files
into concrete software component types (Specification 007).

The :class:`TypeDetector` is a stateless helper that the
:class:`ComponentDetectionEngine` calls during the *scan* phase.  It
reads the :class:`ProjectBlueprint`'s ``InternalComponent`` objects and
the :class:`ProjectStructureMap`'s :class:`FileEntry` objects and
produces a list of :class:`DetectedComponent` objects — one per
*software component* the code generators will eventually build.

A single blueprint ``InternalComponent`` may map to *several* software
components.  For example, a ``"store"`` feature component yields a
Command, a Callback Handler, a Service, a Repository, and a Database
Model — each is a separate detected component with its own type and
responsibility.

The detector does **not** write code, create files, or invent
components that are not present in the blueprint or the structure map.
It only classifies what the upstream engines already declared.

Data source
-----------
The detector reads **only**:

1. the ``ProjectBlueprint`` (``InternalComponent`` objects,
   ``FeatureUnit`` objects, ``ComponentRelationship`` objects), and
2. the ``ProjectStructureMap`` (``FileEntry`` objects,
   ``FolderEntry`` objects).

It does **not** read the user's request.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ..project_planner.blueprint import (
    InternalComponent,
    ProjectBlueprint,
)
from ..structure_generator.structure_map import (
    FileEntry,
    FolderEntry,
    ProjectStructureMap,
)
from .registry import (
    COMPONENT_TYPE_API_CLIENT,
    COMPONENT_TYPE_APPLICATION,
    COMPONENT_TYPE_BACKGROUND_TASK,
    COMPONENT_TYPE_CACHE_LAYER,
    COMPONENT_TYPE_CALLBACK_HANDLER,
    COMPONENT_TYPE_COMMAND,
    COMPONENT_TYPE_CONFIGURATION,
    COMPONENT_TYPE_DATABASE_MODEL,
    COMPONENT_TYPE_ENVIRONMENT,
    COMPONENT_TYPE_FILTER,
    COMPONENT_TYPE_HANDLER,
    COMPONENT_TYPE_KEYBOARD_BUILDER,
    COMPONENT_TYPE_LOCALIZATION,
    COMPONENT_TYPE_LOGGING_SYSTEM,
    COMPONENT_TYPE_MANAGER,
    COMPONENT_TYPE_MESSAGE_BUILDER,
    COMPONENT_TYPE_MIDDLEWARE,
    COMPONENT_TYPE_REPOSITORY,
    COMPONENT_TYPE_ROUTER,
    COMPONENT_TYPE_SCHEDULER,
    COMPONENT_TYPE_SERVICE,
    COMPONENT_TYPE_SESSION,
    COMPONENT_TYPE_UTILITY,
    COMPONENT_TYPE_VALIDATOR,
    DetectedComponent,
    IMPORTANCE_CRITICAL,
    IMPORTANCE_HIGH,
    IMPORTANCE_LOW,
    IMPORTANCE_NORMAL,
)


# ---------------------------------------------------------------------------#
# Infrastructure component detection table
# ---------------------------------------------------------------------------#
#
# Maps the *name* of a known infrastructure component to the
# :class:`DetectedComponent` specification.  The key is the blueprint
# component name (lower-cased).  The value is a tuple of
# (type, purpose, responsibility, importance, reusable).
#
# Infrastructure components are recognised by well-known names that the
# Project Planning Engine produces (config, logger, database, etc.).

_INFRA_TABLE: Dict[str, Tuple[str, str, str, str, bool]] = {
    "config": (
        COMPONENT_TYPE_CONFIGURATION,
        "Loads and provides configuration values for the bot.",
        "Manage all configuration settings and environment variables.",
        IMPORTANCE_CRITICAL, True,
    ),
    "config_loader": (
        COMPONENT_TYPE_CONFIGURATION,
        "Loads and provides configuration values for the bot.",
        "Manage all configuration settings and environment variables.",
        IMPORTANCE_CRITICAL, True,
    ),
    "settings": (
        COMPONENT_TYPE_CONFIGURATION,
        "Loads and provides configuration values for the bot.",
        "Manage all configuration settings and environment variables.",
        IMPORTANCE_CRITICAL, True,
    ),
    "logger": (
        COMPONENT_TYPE_LOGGING_SYSTEM,
        "Provides structured logging across the entire bot.",
        "Record log messages for debugging, monitoring, and auditing.",
        IMPORTANCE_CRITICAL, True,
    ),
    "logging": (
        COMPONENT_TYPE_LOGGING_SYSTEM,
        "Provides structured logging across the entire bot.",
        "Record log messages for debugging, monitoring, and auditing.",
        IMPORTANCE_CRITICAL, True,
    ),
    "log": (
        COMPONENT_TYPE_LOGGING_SYSTEM,
        "Provides structured logging across the entire bot.",
        "Record log messages for debugging, monitoring, and auditing.",
        IMPORTANCE_CRITICAL, True,
    ),
    "database": (
        COMPONENT_TYPE_SESSION,
        "Manages the database connection and session lifecycle.",
        "Provide a database session and connection pool.",
        IMPORTANCE_CRITICAL, True,
    ),
    "db": (
        COMPONENT_TYPE_SESSION,
        "Manages the database connection and session lifecycle.",
        "Provide a database session and connection pool.",
        IMPORTANCE_CRITICAL, True,
    ),
    "database_manager": (
        COMPONENT_TYPE_SESSION,
        "Manages the database connection and session lifecycle.",
        "Provide a database session and connection pool.",
        IMPORTANCE_CRITICAL, True,
    ),
    "cache": (
        COMPONENT_TYPE_CACHE_LAYER,
        "Provides caching for frequently accessed data.",
        "Store and retrieve cached values to reduce database load.",
        IMPORTANCE_HIGH, True,
    ),
    "cache_layer": (
        COMPONENT_TYPE_CACHE_LAYER,
        "Provides caching for frequently accessed data.",
        "Store and retrieve cached values to reduce database load.",
        IMPORTANCE_HIGH, True,
    ),
    "i18n": (
        COMPONENT_TYPE_LOCALIZATION,
        "Provides internationalisation and multilingual support.",
        "Translate user-facing messages into multiple languages.",
        IMPORTANCE_NORMAL, True,
    ),
    "localization": (
        COMPONENT_TYPE_LOCALIZATION,
        "Provides internationalisation and multilingual support.",
        "Translate user-facing messages into multiple languages.",
        IMPORTANCE_NORMAL, True,
    ),
    "scheduler": (
        COMPONENT_TYPE_SCHEDULER,
        "Schedules and runs periodic background jobs.",
        "Run tasks on a fixed schedule (cron-like).",
        IMPORTANCE_NORMAL, True,
    ),
    "task_runner": (
        COMPONENT_TYPE_BACKGROUND_TASK,
        "Runs asynchronous background tasks.",
        "Execute long-running operations without blocking the bot.",
        IMPORTANCE_NORMAL, True,
    ),
    "background_task": (
        COMPONENT_TYPE_BACKGROUND_TASK,
        "Runs asynchronous background tasks.",
        "Execute long-running operations without blocking the bot.",
        IMPORTANCE_NORMAL, True,
    ),
}


# ---------------------------------------------------------------------------#
# Keyword → component-type classification for feature components
# ---------------------------------------------------------------------------#
#
# When a feature component's name or description contains one of these
# keywords, the detector infers the additional software component types
# it will yield.  For example, a component named ``"admin_panel"`` whose
# description mentions ``"callback"`` yields both a Command and a
# Callback Handler.
#
# Each entry is (keyword, component_type, purpose_template,
# responsibility_template, importance).
#
# The templates use ``{name}`` as a placeholder for the component's
# display name.

_FEATURE_KEYWORDS: List[Tuple[str, str, str, str, str]] = [
    (
        "command", COMPONENT_TYPE_COMMAND,
        "Handles the {name} command.",
        "Process the /command and produce a response.",
        IMPORTANCE_HIGH,
    ),
    (
        "callback", COMPONENT_TYPE_CALLBACK_HANDLER,
        "Handles callback queries for the {name}.",
        "Process inline-keyboard callback queries.",
        IMPORTANCE_HIGH,
    ),
    (
        "handler", COMPONENT_TYPE_HANDLER,
        "Handles messages or updates for the {name}.",
        "Process incoming Telegram updates for the {name}.",
        IMPORTANCE_HIGH,
    ),
    (
        "router", COMPONENT_TYPE_ROUTER,
        "Routes updates to the correct handler for the {name}.",
        "Dispatch updates to the appropriate handler.",
        IMPORTANCE_HIGH,
    ),
    (
        "service", COMPONENT_TYPE_SERVICE,
        "Contains business logic for the {name}.",
        "Implement the business rules for the {name}.",
        IMPORTANCE_HIGH,
    ),
    (
        "keyboard", COMPONENT_TYPE_KEYBOARD_BUILDER,
        "Builds inline or reply keyboards for the {name}.",
        "Construct Telegram keyboard markups.",
        IMPORTANCE_NORMAL,
    ),
    (
        "menu", COMPONENT_TYPE_KEYBOARD_BUILDER,
        "Builds menu keyboards for the {name}.",
        "Construct Telegram menu keyboard markups.",
        IMPORTANCE_NORMAL,
    ),
    (
        "message", COMPONENT_TYPE_MESSAGE_BUILDER,
        "Builds formatted messages for the {name}.",
        "Construct formatted Telegram messages.",
        IMPORTANCE_NORMAL,
    ),
    (
        "repository", COMPONENT_TYPE_REPOSITORY,
        "Provides data-access logic for the {name}.",
        "Persist and retrieve {name} data from the database.",
        IMPORTANCE_HIGH,
    ),
    (
        "model", COMPONENT_TYPE_DATABASE_MODEL,
        "Defines the database model for the {name}.",
        "Represent the {name} data structure in the database.",
        IMPORTANCE_HIGH,
    ),
    (
        "validator", COMPONENT_TYPE_VALIDATOR,
        "Validates input data for the {name}.",
        "Validate user input before processing.",
        IMPORTANCE_NORMAL,
    ),
    (
        "middleware", COMPONENT_TYPE_MIDDLEWARE,
        "Middleware that intercepts updates for the {name}.",
        "Intercept and pre-process updates before handlers.",
        IMPORTANCE_NORMAL,
    ),
    (
        "filter", COMPONENT_TYPE_FILTER,
        "Filters updates for the {name}.",
        "Filter updates based on criteria before processing.",
        IMPORTANCE_NORMAL,
    ),
    (
        "api", COMPONENT_TYPE_API_CLIENT,
        "External API client for the {name}.",
        "Communicate with external APIs on behalf of the {name}.",
        IMPORTANCE_HIGH,
    ),
    (
        "integration", COMPONENT_TYPE_API_CLIENT,
        "External integration for the {name}.",
        "Integrate with external services.",
        IMPORTANCE_HIGH,
    ),
    (
        "webhook", COMPONENT_TYPE_API_CLIENT,
        "Webhook handler for the {name}.",
        "Receive and process webhook callbacks.",
        IMPORTANCE_HIGH,
    ),
    (
        "plugin", COMPONENT_TYPE_UTILITY,
        "Plugin extension for the {name}.",
        "Provide an extensible plugin interface.",
        IMPORTANCE_LOW,
    ),
    (
        "extension", COMPONENT_TYPE_UTILITY,
        "Extension module for the {name}.",
        "Provide additional functionality for the {name}.",
        IMPORTANCE_LOW,
    ),
]


# ---------------------------------------------------------------------------#
# Default software components for every feature component
# ---------------------------------------------------------------------------#
#
# Every feature component yields at least these software components.
# The type detector adds them automatically and then layers on top any
# extra components inferred from keywords.

_DEFAULT_FEATURE_COMPONENTS: List[Tuple[str, str, str, str]] = [
    (
        COMPONENT_TYPE_COMMAND,
        "Handles the {name} command.",
        "Process the /{slug} command and produce a response.",
        IMPORTANCE_HIGH,
    ),
    (
        COMPONENT_TYPE_HANDLER,
        "Handles messages and updates for the {name}.",
        "Process incoming Telegram updates for the {name}.",
        IMPORTANCE_HIGH,
    ),
    (
        COMPONENT_TYPE_SERVICE,
        "Contains business logic for the {name}.",
        "Implement the business rules for the {name}.",
        IMPORTANCE_HIGH,
    ),
]


class TypeDetector:
    """Stateless helper that classifies components into software types.

    The detector is called by the
    :class:`ComponentDetectionEngine` during the scan phase.  It
    produces a list of :class:`DetectedComponent` objects — one per
    software component the code generators will build.

    The detector is **pure**: it does not modify the blueprint or the
    structure map, and it does not write to disk.  It only classifies.
    """

    def detect(
        self,
        blueprint: ProjectBlueprint,
        structure_map: ProjectStructureMap,
    ) -> List[DetectedComponent]:
        """Detect all software components from the blueprint and structure map.

        Parameters:
            blueprint: The project blueprint.
            structure_map: The project structure map.

        Returns:
            A list of :class:`DetectedComponent` objects.  The list is
            ordered: infrastructure components first, then feature
            components in blueprint priority order.
        """
        components: List[DetectedComponent] = []

        # Build a lookup of file entries by source_component name.
        files_by_source: Dict[str, List[FileEntry]] = {}
        for f in structure_map.files:
            key = f.source_component or ""
            files_by_source.setdefault(key, []).append(f)

        # Build a lookup of folders by path.
        folders_by_path: Dict[str, FolderEntry] = {
            f.path: f for f in structure_map.folders
        }

        # Detect infrastructure components.
        components.extend(
            self._detect_infrastructure(blueprint, structure_map,
                                        files_by_source, folders_by_path)
        )

        # Detect feature and integration components.
        for ic in sorted(blueprint.components, key=lambda c: (c.priority, c.name)):
            if ic.kind == "infrastructure":
                continue
            if ic.name.lower() in _INFRA_TABLE:
                continue
            components.extend(
                self._detect_feature_component(
                    ic, blueprint, files_by_source, folders_by_path,
                    structure_map,
                )
            )

        return components

    # -----------------------------------------------------------------#
    # Infrastructure detection
    # -----------------------------------------------------------------#

    def _detect_infrastructure(
        self,
        blueprint: ProjectBlueprint,
        structure_map: ProjectStructureMap,
        files_by_source: Dict[str, List[FileEntry]],
        folders_by_path: Dict[str, FolderEntry],
    ) -> List[DetectedComponent]:
        """Detect infrastructure components (config, logger, database, etc.)."""
        components: List[DetectedComponent] = []

        for ic in blueprint.components:
            if ic.kind != "infrastructure":
                continue
            key = ic.name.lower()
            if key not in _INFRA_TABLE:
                continue
            comp_type, purpose, responsibility, importance, reusable = (
                _INFRA_TABLE[key]
            )

            location = self._find_location(ic, files_by_source, folders_by_path)
            building_engine = self._find_building_engine(ic, files_by_source)

            components.append(DetectedComponent(
                name=ic.name,
                type=comp_type,
                purpose=purpose,
                responsibility=responsibility,
                source_blueprint_component=ic.name,
                source_feature=ic.source_feature or "",
                location=location,
                building_engine=building_engine,
                depends_on=list(ic.dependencies),
                importance=importance,
                reusable=reusable,
                scalable=True,
                compatible=True,
                metadata={"blueprint_kind": ic.kind},
            ))

        # Detect database model and repository when a database is configured.
        if blueprint.identity.database:
            components.extend(
                self._detect_database_components(
                    blueprint, structure_map, files_by_source,
                    folders_by_path,
                )
            )

        # Detect the application / bot entry point.
        components.extend(
            self._detect_application(structure_map, files_by_source)
        )

        return components

    def _detect_database_components(
        self,
        blueprint: ProjectBlueprint,
        structure_map: ProjectStructureMap,
        files_by_source: Dict[str, List[FileEntry]],
        folders_by_path: Dict[str, FolderEntry],
    ) -> List[DetectedComponent]:
        """Detect the database model and repository components."""
        components: List[DetectedComponent] = []

        db_files = files_by_source.get("database", [])
        db_folder = self._find_folder_for_files(db_files, folders_by_path)

        # Database Model
        model_file = self._find_file(db_files, "models.py")
        if model_file:
            components.append(DetectedComponent(
                name="database_model",
                type=COMPONENT_TYPE_DATABASE_MODEL,
                purpose="Defines the database models (tables, columns).",
                responsibility="Represent the data schema in the database.",
                source_blueprint_component="database",
                location=model_file.path,
                building_engine=model_file.building_engine,
                depends_on=["database"],
                importance=IMPORTANCE_HIGH,
                reusable=True,
                scalable=True,
                compatible=True,
                metadata={"database": blueprint.identity.database},
            ))

        # Database Repository
        repo_file = self._find_file(db_files, "schema.py") or \
            self._find_file(db_files, "connection.py")
        if repo_file:
            components.append(DetectedComponent(
                name="database_repository",
                type=COMPONENT_TYPE_REPOSITORY,
                purpose="Provides data access and persistence logic.",
                responsibility="Persist and retrieve data from the database.",
                source_blueprint_component="database",
                location=repo_file.path,
                building_engine=repo_file.building_engine,
                depends_on=["database_model"],
                importance=IMPORTANCE_HIGH,
                reusable=True,
                scalable=True,
                compatible=True,
                metadata={"database": blueprint.identity.database},
            ))

        return components

    def _detect_application(
        self,
        structure_map: ProjectStructureMap,
        files_by_source: Dict[str, List[FileEntry]],
    ) -> List[DetectedComponent]:
        """Detect the bot application and entry-point components."""
        components: List[DetectedComponent] = []

        core_files = files_by_source.get("core", [])
        main_file = self._find_file(core_files, "main.py")
        bot_file = self._find_file(core_files, "bot.py")

        if bot_file:
            components.append(DetectedComponent(
                name="bot_application",
                type=COMPONENT_TYPE_APPLICATION,
                purpose="Bot application setup, dispatcher, and lifecycle.",
                responsibility="Initialise and run the Telegram bot.",
                source_blueprint_component="core",
                location=bot_file.path,
                building_engine=bot_file.building_engine,
                depends_on=[],
                importance=IMPORTANCE_CRITICAL,
                reusable=False,
                scalable=True,
                compatible=True,
            ))

        if main_file:
            components.append(DetectedComponent(
                name="entry_point",
                type=COMPONENT_TYPE_APPLICATION,
                purpose="Project entry point — starts the bot.",
                responsibility="Bootstrap and start the bot application.",
                source_blueprint_component="core",
                location=main_file.path,
                building_engine=main_file.building_engine,
                depends_on=["bot_application"] if bot_file else [],
                importance=IMPORTANCE_CRITICAL,
                reusable=False,
                scalable=False,
                compatible=True,
            ))

        # Detect the environment / configuration loader.
        config_files = files_by_source.get("core", [])
        config_file = self._find_file(config_files, "config.py")
        if config_file:
            components.append(DetectedComponent(
                name="environment_config",
                type=COMPONENT_TYPE_ENVIRONMENT,
                purpose="Loads environment variables and configuration.",
                responsibility="Provide typed configuration from env/files.",
                source_blueprint_component="core",
                location=config_file.path,
                building_engine=config_file.building_engine,
                depends_on=[],
                importance=IMPORTANCE_CRITICAL,
                reusable=True,
                scalable=True,
                compatible=True,
            ))

        return components

    # -----------------------------------------------------------------#
    # Feature component detection
    # -----------------------------------------------------------------#

    def _detect_feature_component(
        self,
        ic: InternalComponent,
        blueprint: ProjectBlueprint,
        files_by_source: Dict[str, List[FileEntry]],
        folders_by_path: Dict[str, FolderEntry],
        structure_map: ProjectStructureMap,
    ) -> List[DetectedComponent]:
        """Detect software components for a single feature component."""
        components: List[DetectedComponent] = []
        display_name = ic.display_name or ic.name

        # Find the location for this component.
        location = self._find_location(ic, files_by_source, folders_by_path)
        building_engine = self._find_building_engine(ic, files_by_source)

        # Determine whether this component uses a database.
        feature = blueprint.get_feature(ic.source_feature) if ic.source_feature else None
        requires_database = bool(feature and feature.requires_database)

        # Build the set of component types this feature yields.
        # Start with the default set, then add keyword-based types.
        types_seen: set = set()
        ordered_types: List[Tuple[str, str, str, str]] = []

        for comp_type, purpose_tmpl, resp_tmpl, importance in (
            _DEFAULT_FEATURE_COMPONENTS
        ):
            if comp_type not in types_seen:
                types_seen.add(comp_type)
                ordered_types.append(
                    (comp_type, purpose_tmpl, resp_tmpl, importance)
                )

        # Scan the component name and description for keywords.
        search_text = f"{ic.name} {ic.description or ''}".lower()
        for keyword, comp_type, purpose_tmpl, resp_tmpl, importance in (
            _FEATURE_KEYWORDS
        ):
            if keyword in search_text and comp_type not in types_seen:
                types_seen.add(comp_type)
                ordered_types.append(
                    (comp_type, purpose_tmpl, resp_tmpl, importance)
                )

        # If the feature requires a database, add a repository and model.
        if requires_database:
            if COMPONENT_TYPE_REPOSITORY not in types_seen:
                types_seen.add(COMPONENT_TYPE_REPOSITORY)
                ordered_types.append((
                    COMPONENT_TYPE_REPOSITORY,
                    "Provides data-access logic for the {name}.",
                    "Persist and retrieve {name} data from the database.",
                    IMPORTANCE_HIGH,
                ))

        # Create a DetectedComponent for each type.
        for comp_type, purpose_tmpl, resp_tmpl, importance in ordered_types:
            slug = ic.name.replace(" ", "_")
            comp_name = f"{ic.name}_{comp_type}" if comp_type != COMPONENT_TYPE_COMMAND else f"{ic.name}_command"

            # For commands, use the feature name directly.
            if comp_type == COMPONENT_TYPE_COMMAND:
                comp_name = f"{ic.name}_command"
            elif comp_type == COMPONENT_TYPE_HANDLER:
                comp_name = f"{ic.name}_handler"
            elif comp_type == COMPONENT_TYPE_CALLBACK_HANDLER:
                comp_name = f"{ic.name}_callback_handler"
            elif comp_type == COMPONENT_TYPE_SERVICE:
                comp_name = f"{ic.name}_service"
            elif comp_type == COMPONENT_TYPE_REPOSITORY:
                comp_name = f"{ic.name}_repository"
            elif comp_type == COMPONENT_TYPE_DATABASE_MODEL:
                comp_name = f"{ic.name}_model"
            elif comp_type == COMPONENT_TYPE_KEYBOARD_BUILDER:
                comp_name = f"{ic.name}_keyboard"
            elif comp_type == COMPONENT_TYPE_MESSAGE_BUILDER:
                comp_name = f"{ic.name}_message_builder"
            elif comp_type == COMPONENT_TYPE_VALIDATOR:
                comp_name = f"{ic.name}_validator"
            elif comp_type == COMPONENT_TYPE_MIDDLEWARE:
                comp_name = f"{ic.name}_middleware"
            elif comp_type == COMPONENT_TYPE_ROUTER:
                comp_name = f"{ic.name}_router"
            elif comp_type == COMPONENT_TYPE_API_CLIENT:
                comp_name = f"{ic.name}_api_client"
            else:
                comp_name = f"{ic.name}_{comp_type}"

            purpose = purpose_tmpl.format(name=display_name)
            responsibility = resp_tmpl.format(
                name=display_name, slug=slug,
            )

            # Dependencies: feature components depend on the bot
            # application and, if they use a database, on the
            # database session / repository.
            # Never allow a component to depend on itself.
            deps: List[str] = [
                d for d in list(ic.dependencies)
                if d and d != comp_name
            ]
            if (
                "bot_application" not in deps
                and comp_name != "bot_application"
            ):
                deps.append("bot_application")
            if requires_database and comp_type in (
                COMPONENT_TYPE_SERVICE, COMPONENT_TYPE_HANDLER,
                COMPONENT_TYPE_COMMAND,
            ):
                if (
                    "database_repository" not in deps
                    and comp_name != "database_repository"
                ):
                    deps.append("database_repository")

            components.append(DetectedComponent(
                name=comp_name,
                type=comp_type,
                purpose=purpose,
                responsibility=responsibility,
                source_blueprint_component=ic.name,
                source_feature=ic.source_feature or "",
                location=location,
                building_engine=building_engine,
                depends_on=deps,
                importance=importance,
                reusable=comp_type in (
                    COMPONENT_TYPE_REPOSITORY,
                    COMPONENT_TYPE_VALIDATOR,
                    COMPONENT_TYPE_KEYBOARD_BUILDER,
                    COMPONENT_TYPE_MESSAGE_BUILDER,
                    COMPONENT_TYPE_UTILITY,
                    COMPONENT_TYPE_API_CLIENT,
                ),
                scalable=True,
                compatible=True,
                metadata={
                    "blueprint_kind": ic.kind,
                    "blueprint_priority": ic.priority,
                },
            ))

        return components

    # -----------------------------------------------------------------#
    # Utility helpers
    # -----------------------------------------------------------------#

    @staticmethod
    def _find_location(
        ic: InternalComponent,
        files_by_source: Dict[str, List[FileEntry]],
        folders_by_path: Dict[str, FolderEntry],
    ) -> str:
        """Find the location (file path) for a blueprint component."""
        files = files_by_source.get(ic.name, [])
        if files:
            # Prefer a code file over a package init.
            for f in files:
                if f.contains_code and f.name != "__init__.py":
                    return f.path
            return files[0].path
        # Fall back to the component's folder.
        for path, folder in folders_by_path.items():
            if folder.name == ic.name:
                return path
        return ""

    @staticmethod
    def _find_building_engine(
        ic: InternalComponent,
        files_by_source: Dict[str, List[FileEntry]],
    ) -> str:
        """Find the building engine for a blueprint component."""
        files = files_by_source.get(ic.name, [])
        for f in files:
            if f.contains_code and f.name != "__init__.py":
                return f.building_engine
        if files:
            return files[0].building_engine
        return "code_generator"

    @staticmethod
    def _find_file(files: List[FileEntry], name: str) -> Optional[FileEntry]:
        """Find a file by name in a list of file entries."""
        for f in files:
            if f.name == name:
                return f
        return None

    @staticmethod
    def _find_folder_for_files(
        files: List[FileEntry],
        folders_by_path: Dict[str, FolderEntry],
    ) -> str:
        """Find the folder path that contains the given files."""
        for f in files:
            if f.folder and f.folder in folders_by_path:
                return f.folder
        return ""


__all__ = ["TypeDetector"]
