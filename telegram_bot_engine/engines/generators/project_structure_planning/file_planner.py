"""
FilePlanner — Specification 020

Enumerates every file that the project will need, assigning purpose,
responsibility, type, module and folder.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from .report_data import (
    FolderNode,
    FileDescriptor,
    ModuleMapping,
    FILE_TYPE_PYTHON,
    FILE_TYPE_CONFIG,
    FILE_TYPE_TEST,
    FILE_TYPE_DOC,
    FILE_TYPE_SCRIPT,
    FILE_TYPE_INIT,
    FOLDER_ROOT,
    FOLDER_CORE,
    FOLDER_HANDLERS,
    FOLDER_SERVICES,
    FOLDER_DATABASE,
    FOLDER_UTILS,
    FOLDER_CONFIGS,
    FOLDER_TESTS,
    FOLDER_DOCS,
    FOLDER_SCRIPTS,
    FOLDER_MODELS,
    FOLDER_REPOSITORIES,
    FOLDER_MIDDLEWARE,
    FOLDER_MODULES,
)
from .data_readers import (
    ExecutionPlanData,
    ArchitectureDecisionData,
    TechnologySelectionData,
    RequirementNormalizationData,
)

_log = logging.getLogger("engine.project_structure_planning.file_planner")


class FilePlanner:
    """Produces the complete list of FileDescriptor objects."""

    def plan(
        self,
        folders: List[FolderNode],
        exec_data: ExecutionPlanData,
        arch_data: ArchitectureDecisionData,
        tech_data: TechnologySelectionData,
        req_data: RequirementNormalizationData,
        root_name: str = "telegram_bot",
    ) -> tuple[List[FileDescriptor], List[ModuleMapping]]:
        folder_by_id = {f.folder_id: f for f in folders}
        files: List[FileDescriptor] = []
        modules: List[ModuleMapping] = []

        def add(
            file_id: str,
            name: str,
            folder_id: str,
            purpose: str,
            responsibility: str,
            file_type: str = FILE_TYPE_PYTHON,
            module_id: str = "",
            depends_on: Optional[List[str]] = None,
            exports: Optional[List[str]] = None,
            tags: Optional[List[str]] = None,
        ) -> FileDescriptor:
            folder = folder_by_id.get(folder_id)
            path = f"{folder.path}/{name}" if folder else name
            fd = FileDescriptor(
                file_id=file_id,
                name=name,
                path=path,
                purpose=purpose,
                responsibility=responsibility,
                file_type=file_type,
                module_id=module_id,
                folder_id=folder_id,
                depends_on=depends_on or [],
                exports=exports or [],
                tags=tags or [],
            )
            files.append(fd)
            return fd

        # ------------------------------------------------------------------ #
        # Root level
        # ------------------------------------------------------------------ #
        add("file.root.main", "main.py", FOLDER_ROOT if FOLDER_ROOT in folder_by_id else "root",
            "Application entry point", "Bootstraps the bot and starts the polling / webhook loop",
            exports=["main"], tags=["entrypoint"])
        add("file.root.init", "__init__.py", "root",
            "Package marker for the project root", "Makes the root importable as a package",
            FILE_TYPE_INIT)
        add("file.root.requirements", "requirements.txt", "root",
            "Python dependency list", "Declares runtime and development dependencies",
            FILE_TYPE_CONFIG, tags=["deps"])
        add("file.root.readme", "README.md", "root",
            "Project overview", "Human-readable project description and usage",
            FILE_TYPE_DOC)
        add("file.root.gitignore", ".gitignore", "root",
            "Git ignore rules", "Excludes logs, caches, virtualenvs and secrets",
            FILE_TYPE_CONFIG)

        # ------------------------------------------------------------------ #
        # Core / models
        # ------------------------------------------------------------------ #
        add("file.core.init", "__init__.py", FOLDER_CORE,
            "Core package marker", "Exposes core public API", FILE_TYPE_INIT)
        add("file.models.init", "__init__.py", FOLDER_MODELS,
            "Models package marker", "Exports domain models", FILE_TYPE_INIT,
            exports=["*"])
        add("file.models.base", "base.py", FOLDER_MODELS,
            "Base model classes", "Defines shared base entity / value-object classes",
            module_id="mod.models", exports=["BaseModel", "BaseEntity"])

        # ------------------------------------------------------------------ #
        # Handlers
        # ------------------------------------------------------------------ #
        add("file.handlers.init", "__init__.py", FOLDER_HANDLERS,
            "Handlers package marker", "Exports registered handlers", FILE_TYPE_INIT)
        add("file.handlers.commands", "commands.py", FOLDER_HANDLERS,
            "Command handlers", "Handles /start, /help and other slash commands",
            module_id="mod.handlers", depends_on=["file.models.base"],
            exports=["command_handlers"])
        add("file.handlers.callbacks", "callbacks.py", FOLDER_HANDLERS,
            "Callback query handlers", "Handles inline button callbacks",
            module_id="mod.handlers", depends_on=["file.models.base"],
            exports=["callback_handlers"])
        add("file.handlers.messages", "messages.py", FOLDER_HANDLERS,
            "Message handlers", "Handles free-text and media messages",
            module_id="mod.handlers", depends_on=["file.models.base"],
            exports=["message_handlers"])

        # ------------------------------------------------------------------ #
        # Services
        # ------------------------------------------------------------------ #
        add("file.services.init", "__init__.py", FOLDER_SERVICES,
            "Services package marker", "Exports business services", FILE_TYPE_INIT)
        add("file.services.user", "user_service.py", FOLDER_SERVICES,
            "User service", "Encapsulates user-related business logic",
            module_id="mod.services", depends_on=["file.models.base"],
            exports=["UserService"])

        # ------------------------------------------------------------------ #
        # Database
        # ------------------------------------------------------------------ #
        add("file.db.init", "__init__.py", FOLDER_DATABASE,
            "Database package marker", "Exposes session and engine helpers", FILE_TYPE_INIT)
        add("file.db.session", "session.py", FOLDER_DATABASE,
            "Database session factory", "Creates and manages DB sessions",
            module_id="mod.database", exports=["get_session", "engine"])
        add("file.repo.init", "__init__.py", FOLDER_REPOSITORIES,
            "Repositories package marker", "Exports repository classes", FILE_TYPE_INIT)
        add("file.repo.user", "user_repository.py", FOLDER_REPOSITORIES,
            "User repository", "CRUD operations for user entities",
            module_id="mod.database", depends_on=["file.db.session", "file.models.base"],
            exports=["UserRepository"])

        # ------------------------------------------------------------------ #
        # Middleware / Utils / Configs
        # ------------------------------------------------------------------ #
        add("file.middleware.init", "__init__.py", FOLDER_MIDDLEWARE,
            "Middleware package marker", "Exports middleware stack", FILE_TYPE_INIT)
        add("file.utils.init", "__init__.py", FOLDER_UTILS,
            "Utils package marker", "Exports shared helpers", FILE_TYPE_INIT)
        add("file.utils.helpers", "helpers.py", FOLDER_UTILS,
            "Generic helpers", "Pure utility functions used across the project",
            module_id="mod.utils", exports=["*"])
        add("file.configs.settings", "settings.py", FOLDER_CONFIGS,
            "Application settings", "Central configuration loaded from environment",
            FILE_TYPE_CONFIG, module_id="mod.config", exports=["Settings", "settings"])
        add("file.configs.env", ".env.example", FOLDER_CONFIGS,
            "Environment template", "Documents required environment variables",
            FILE_TYPE_CONFIG)

        # ------------------------------------------------------------------ #
        # Tests
        # ------------------------------------------------------------------ #
        add("file.tests.init", "__init__.py", FOLDER_TESTS,
            "Tests package marker", "Makes tests importable", FILE_TYPE_INIT)
        add("file.tests.test_handlers", "test_handlers.py", FOLDER_TESTS,
            "Handler unit tests", "Verifies command and callback handlers",
            FILE_TYPE_TEST, depends_on=["file.handlers.commands"])
        add("file.tests.test_services", "test_services.py", FOLDER_TESTS,
            "Service unit tests", "Verifies business service behaviour",
            FILE_TYPE_TEST, depends_on=["file.services.user"])

        # ------------------------------------------------------------------ #
        # Docs / Scripts
        # ------------------------------------------------------------------ #
        add("file.docs.architecture", "architecture.md", FOLDER_DOCS,
            "Architecture documentation", "Describes the chosen architecture",
            FILE_TYPE_DOC)
        add("file.scripts.run", "run.sh", FOLDER_SCRIPTS,
            "Run script", "Convenience script to start the bot",
            FILE_TYPE_SCRIPT)

        # ------------------------------------------------------------------ #
        # Feature modules derived from requirements (limited)
        # ------------------------------------------------------------------ #
        if req_data.available and req_data.features:
            for idx, feature in enumerate(req_data.features[:8]):
                name = ""
                if isinstance(feature, dict):
                    name = feature.get("name") or feature.get("title") or f"feature_{idx}"
                else:
                    name = str(feature)
                safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in name.lower())[:30]
                mod_id = f"mod.feature.{safe}"
                folder_id = FOLDER_MODULES
                add(
                    f"file.modules.{safe}",
                    f"{safe}.py",
                    folder_id,
                    f"Feature module: {name}",
                    f"Implements the '{name}' feature as derived from requirements",
                    module_id=mod_id,
                    tags=["feature", safe],
                )
                modules.append(ModuleMapping(
                    module_id=mod_id,
                    name=name,
                    folder_path=f"{root_name}/modules",
                    file_ids=[f"file.modules.{safe}"],
                    description=f"Feature module for '{name}'",
                ))

        # ------------------------------------------------------------------ #
        # Core modules
        # ------------------------------------------------------------------ #
        modules.extend([
            ModuleMapping("mod.models", "Models", f"{root_name}/core/models",
                          ["file.models.base", "file.models.init"], "Domain models"),
            ModuleMapping("mod.handlers", "Handlers", f"{root_name}/handlers",
                          ["file.handlers.commands", "file.handlers.callbacks", "file.handlers.messages"],
                          "Telegram handlers"),
            ModuleMapping("mod.services", "Services", f"{root_name}/services",
                          ["file.services.user"], "Business services"),
            ModuleMapping("mod.database", "Database", f"{root_name}/database",
                          ["file.db.session", "file.repo.user"], "Persistence layer"),
            ModuleMapping("mod.utils", "Utils", f"{root_name}/utils",
                          ["file.utils.helpers"], "Shared utilities"),
            ModuleMapping("mod.config", "Config", f"{root_name}/configs",
                          ["file.configs.settings"], "Configuration"),
        ])

        _log.info("FilePlanner produced %d files and %d modules", len(files), len(modules))
        return files, modules


__all__ = ["FilePlanner"]
