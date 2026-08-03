"""
FolderPlanner — Specification 020

Designs the complete folder tree for the project based on architecture,
technology choices and project scale.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from .report_data import (
    FolderNode,
    FOLDER_ROOT,
    FOLDER_CORE,
    FOLDER_MODULES,
    FOLDER_HANDLERS,
    FOLDER_SERVICES,
    FOLDER_DATABASE,
    FOLDER_UTILS,
    FOLDER_CONFIGS,
    FOLDER_TESTS,
    FOLDER_ASSETS,
    FOLDER_LOGS,
    FOLDER_DOCS,
    FOLDER_SCRIPTS,
    FOLDER_MIDDLEWARE,
    FOLDER_API,
    FOLDER_MODELS,
    FOLDER_REPOSITORIES,
)
from .data_readers import (
    ExecutionPlanData,
    ArchitectureDecisionData,
    TechnologySelectionData,
    ProjectCapabilityData,
)

_log = logging.getLogger("engine.project_structure_planning.folder_planner")


class FolderPlanner:
    """Builds the ordered list of FolderNode objects that form the project tree."""

    def __init__(self) -> None:
        self._counter = 0

    def plan(
        self,
        exec_data: ExecutionPlanData,
        arch_data: ArchitectureDecisionData,
        tech_data: TechnologySelectionData,
        cap_data: ProjectCapabilityData,
        root_name: str = "telegram_bot",
    ) -> List[FolderNode]:
        self._counter = 0
        folders: List[FolderNode] = []

        # Root
        root = self._make(FOLDER_ROOT, root_name, root_name, "Project root directory", None)
        folders.append(root)

        # Core hierarchy under root
        core = self._make(FOLDER_CORE, "core", f"{root_name}/core",
                          "Core domain logic, models and shared internals", root.folder_id)
        folders.append(core)

        models = self._make(FOLDER_MODELS, "models", f"{root_name}/core/models",
                            "Domain entities and value objects", core.folder_id)
        folders.append(models)

        # Handlers
        handlers = self._make(FOLDER_HANDLERS, "handlers", f"{root_name}/handlers",
                              "Telegram update / command / callback handlers", root.folder_id)
        folders.append(handlers)

        # Services
        services = self._make(FOLDER_SERVICES, "services", f"{root_name}/services",
                              "Business services and use-case orchestrators", root.folder_id)
        folders.append(services)

        # Database / repositories
        database = self._make(FOLDER_DATABASE, "database", f"{root_name}/database",
                              "Database connection, migrations and session management", root.folder_id)
        folders.append(database)

        repositories = self._make(FOLDER_REPOSITORIES, "repositories", f"{root_name}/database/repositories",
                                  "Data-access repositories", database.folder_id)
        folders.append(repositories)

        # Modules (feature modules)
        modules = self._make(FOLDER_MODULES, "modules", f"{root_name}/modules",
                             "Feature-oriented modules that can grow independently", root.folder_id)
        folders.append(modules)

        # Middleware
        middleware = self._make(FOLDER_MIDDLEWARE, "middleware", f"{root_name}/middleware",
                                "Request/response middleware and filters", root.folder_id)
        folders.append(middleware)

        # API (if architecture suggests it)
        if arch_data.available and "api" in (arch_data.architecture_style or "").lower():
            api = self._make(FOLDER_API, "api", f"{root_name}/api",
                             "External HTTP / webhook API layer", root.folder_id)
            folders.append(api)

        # Utils, configs, tests, assets, logs, docs, scripts
        utils = self._make(FOLDER_UTILS, "utils", f"{root_name}/utils",
                           "Shared utility helpers", root.folder_id)
        folders.append(utils)

        configs = self._make(FOLDER_CONFIGS, "configs", f"{root_name}/configs",
                             "Configuration files and environment templates", root.folder_id)
        folders.append(configs)

        tests = self._make(FOLDER_TESTS, "tests", f"{root_name}/tests",
                           "Unit, integration and end-to-end tests", root.folder_id)
        folders.append(tests)

        assets = self._make(FOLDER_ASSETS, "assets", f"{root_name}/assets",
                            "Static assets (images, locales, etc.)", root.folder_id)
        folders.append(assets)

        logs = self._make(FOLDER_LOGS, "logs", f"{root_name}/logs",
                          "Runtime log output directory (usually git-ignored)", root.folder_id)
        folders.append(logs)

        docs = self._make(FOLDER_DOCS, "docs", f"{root_name}/docs",
                          "Project documentation", root.folder_id)
        folders.append(docs)

        scripts = self._make(FOLDER_SCRIPTS, "scripts", f"{root_name}/scripts",
                             "Operational and maintenance scripts", root.folder_id)
        folders.append(scripts)

        # Scalability: if capability score is high, add an extra extension point
        if cap_data.available and cap_data.scalability_score >= 0.7:
            ext = self._make(
                "extensions", "extensions", f"{root_name}/extensions",
                "Plugin / extension point for future modules without restructuring",
                root.folder_id, is_standard=False, tags=["scalability"],
            )
            folders.append(ext)

        # Wire children lists
        by_id = {f.folder_id: f for f in folders}
        for f in folders:
            if f.parent_id and f.parent_id in by_id:
                by_id[f.parent_id].children.append(f.folder_id)

        _log.info("FolderPlanner produced %d folders", len(folders))
        return folders

    def _make(
        self,
        folder_id: str,
        name: str,
        path: str,
        purpose: str,
        parent_id: Optional[str],
        is_standard: bool = True,
        tags: Optional[List[str]] = None,
    ) -> FolderNode:
        self._counter += 1
        return FolderNode(
            folder_id=folder_id if folder_id else f"folder_{self._counter}",
            name=name,
            path=path,
            purpose=purpose,
            parent_id=parent_id,
            is_standard=is_standard,
            tags=tags or [],
        )


__all__ = ["FolderPlanner"]
