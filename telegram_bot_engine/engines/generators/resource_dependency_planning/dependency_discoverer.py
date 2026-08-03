"""
DependencyDiscoverer — Specification 025

Discovers libraries, frameworks, resources, versions, risks and optimisations.
"""

from __future__ import annotations

import logging
from typing import List, Tuple

from .report_data import (
    DependencyItem, ResourceItem, VersionMatrixEntry, RiskItem, OptimizationSuggestion,
    DEP_LIBRARY, DEP_FRAMEWORK, DEP_SDK, DEP_API, DEP_DATABASE,
    RES_CONFIG, RES_ENV, RES_SECRET, RES_API_KEY, RES_LOG, RES_ASSET,
    RISK_DEPRECATED, RISK_SECURITY, RISK_VERSION_CONFLICT,
    SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW,
)
from .data_readers import GenericData

_log = logging.getLogger("engine.resource_dependency_planning.dependency_discoverer")


class DependencyDiscoverer:
    def discover(
        self,
        tech_data: GenericData,
        comp_data: GenericData,
        flow_data: GenericData,
        struct_data: GenericData,
    ) -> Tuple[
        List[DependencyItem],
        List[ResourceItem],
        List[VersionMatrixEntry],
        List[RiskItem],
        List[OptimizationSuggestion],
        str,
    ]:
        deps: List[DependencyItem] = []
        resources: List[ResourceItem] = []
        matrix: List[VersionMatrixEntry] = []
        risks: List[RiskItem] = []
        optimisations: List[OptimizationSuggestion] = []
        python_version = ">=3.10,<3.13"

        # ------------------------------------------------------------------ #
        # Core Python / Telegram stack
        # ------------------------------------------------------------------ #
        deps.extend([
            DependencyItem(
                "dep.python-telegram-bot", "python-telegram-bot", DEP_LIBRARY,
                "21.0", ">=21.0,<22",
                "Official Telegram Bot API wrapper",
                ["mod.integration.telegram"], "LGPL-3.0", True,
                tags=["telegram", "core"],
            ),
            DependencyItem(
                "dep.pydantic", "pydantic", DEP_LIBRARY,
                "2.7", ">=2.5,<3",
                "Data validation and settings management",
                ["mod.infra.config", "mod.core.domain"], "MIT", True,
                tags=["validation", "config"],
            ),
            DependencyItem(
                "dep.python-dotenv", "python-dotenv", DEP_LIBRARY,
                "1.0", ">=1.0",
                "Load environment variables from .env files",
                ["mod.infra.config"], "BSD-3-Clause", True,
                tags=["config"],
            ),
            DependencyItem(
                "dep.httpx", "httpx", DEP_LIBRARY,
                "0.27", ">=0.27",
                "Async HTTP client for external APIs",
                ["mod.integration.telegram"], "BSD-3-Clause", True,
                tags=["http", "async"],
            ),
            DependencyItem(
                "dep.sqlalchemy", "SQLAlchemy", DEP_LIBRARY,
                "2.0", ">=2.0,<3",
                "ORM / database toolkit",
                ["mod.infra.persistence"], "MIT", True,
                tags=["database", "orm"],
            ),
            DependencyItem(
                "dep.aiosqlite", "aiosqlite", DEP_LIBRARY,
                "0.20", ">=0.20",
                "Async SQLite driver",
                ["mod.infra.persistence"], "MIT", True,
                tags=["database", "sqlite"],
            ),
            DependencyItem(
                "dep.structlog", "structlog", DEP_LIBRARY,
                "24.1", ">=24.1",
                "Structured logging",
                ["mod.support.logging"], "Apache-2.0", True, True,
                tags=["logging"],
            ),
            DependencyItem(
                "dep.pytest", "pytest", DEP_LIBRARY,
                "8.2", ">=8.0",
                "Test runner",
                ["mod.testing"], "MIT", True, True,
                tags=["testing"],
            ),
            DependencyItem(
                "dep.pytest-asyncio", "pytest-asyncio", DEP_LIBRARY,
                "0.23", ">=0.23",
                "Async test support",
                ["mod.testing"], "Apache-2.0", True, True,
                tags=["testing", "async"],
            ),
        ])

        # From technology selection if available
        if tech_data.available and tech_data.raw:
            lang = (tech_data.raw.get("language") or "python").lower()
            framework = (tech_data.raw.get("framework") or "").lower()
            database = (tech_data.raw.get("database") or "").lower()
            if "postgres" in database:
                deps.append(DependencyItem(
                    "dep.asyncpg", "asyncpg", DEP_DRIVER,
                    "0.29", ">=0.29",
                    "Async PostgreSQL driver",
                    ["mod.infra.persistence"], "Apache-2.0", True,
                    tags=["database", "postgres"],
                ))
            if framework and framework not in ("", "none"):
                deps.append(DependencyItem(
                    f"dep.{framework}", framework, DEP_FRAMEWORK,
                    "", "latest",
                    f"Selected framework: {framework}",
                    ["mod.core"], "", True,
                    tags=["framework"],
                ))

        # ------------------------------------------------------------------ #
        # Resources
        # ------------------------------------------------------------------ #
        resources.extend([
            ResourceItem("res.env", ".env", RES_ENV, ".env",
                         "Runtime environment file (secrets, tokens)", True, "secret",
                         ["mod.infra.config"]),
            ResourceItem("res.env.example", ".env.example", RES_CONFIG, ".env.example",
                         "Documented template of required environment variables", True, "public",
                         ["mod.infra.config"]),
            ResourceItem("res.settings", "configs/settings.py", RES_CONFIG, "configs/settings.py",
                         "Central application settings module", True, "internal",
                         ["mod.infra.config"]),
            ResourceItem("res.bot_token", "BOT_TOKEN", RES_API_KEY, "BOT_TOKEN",
                         "Telegram Bot API token", True, "secret",
                         ["mod.integration.telegram", "mod.infra.config"]),
            ResourceItem("res.db_url", "DATABASE_URL", RES_ENV, "DATABASE_URL",
                         "Database connection string", True, "sensitive",
                         ["mod.infra.persistence"]),
            ResourceItem("res.logs", "logs/", RES_LOG, "logs/",
                         "Runtime log directory (git-ignored)", False, "internal",
                         ["mod.support.logging"]),
            ResourceItem("res.requirements", "requirements.txt", RES_CONFIG, "requirements.txt",
                         "Pinned Python dependency list", True, "public",
                         ["root"]),
            ResourceItem("res.gitignore", ".gitignore", RES_CONFIG, ".gitignore",
                         "Excludes secrets, logs, venv, caches", True, "public",
                         ["root"]),
        ])

        # ------------------------------------------------------------------ #
        # Version matrix (compatibility notes)
        # ------------------------------------------------------------------ #
        matrix.extend([
            VersionMatrixEntry("python", "3.10–3.12",
                               ["python-telegram-bot>=21", "pydantic>=2", "SQLAlchemy>=2"],
                               "Target runtime"),
            VersionMatrixEntry("python-telegram-bot", "21.x",
                               ["httpx>=0.27", "python>=3.8"],
                               "v21 is the current major line"),
            VersionMatrixEntry("SQLAlchemy", "2.x",
                               ["aiosqlite>=0.20", "asyncpg>=0.29"],
                               "2.0 style async sessions"),
            VersionMatrixEntry("pydantic", "2.x",
                               ["python>=3.8"],
                               "v1 is EOL; stay on v2"),
        ])

        # ------------------------------------------------------------------ #
        # Risks
        # ------------------------------------------------------------------ #
        risks.extend([
            RiskItem("risk.ptb_major", RISK_VERSION_CONFLICT, SEVERITY_MEDIUM,
                     "dep.python-telegram-bot",
                     "python-telegram-bot major versions introduce breaking API changes",
                     "Pin to a single major and follow the upgrade guide carefully"),
            RiskItem("risk.secrets_in_env", RISK_SECURITY, SEVERITY_HIGH,
                     "res.bot_token",
                     "Bot token in .env can leak if committed",
                     "Ensure .env is git-ignored; use secret manager in production"),
        ])

        # ------------------------------------------------------------------ #
        # Optimisations
        # ------------------------------------------------------------------ #
        optimisations.append(OptimizationSuggestion(
            "opt.structlog_optional",
            "structlog is optional; stdlib logging is enough for small bots",
            ["dep.structlog"],
            "logging (stdlib)",
            "Fewer dependencies, zero extra install size",
        ))

        _log.info(
            "DependencyDiscoverer: %d deps, %d resources, %d risks",
            len(deps), len(resources), len(risks),
        )
        return deps, resources, matrix, risks, optimisations, python_version


__all__ = ["DependencyDiscoverer"]
