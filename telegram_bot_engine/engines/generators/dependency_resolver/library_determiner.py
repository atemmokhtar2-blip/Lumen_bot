"""
Library Determiner — determines the required libraries, frameworks,
tools, versions, and their relationships (Specification 009).

The :class:`LibraryDeterminer` is a stateless helper that the
:class:`DependencyResolutionEngine` calls during the *determination*
phase.  It takes the :class:`ComponentAnalysisResult` produced by the
:class:`ComponentAnalyzer`, the :class:`ProjectBlueprint`, the
:class:`ProjectStructureMap`, and the :class:`FileGenerationPlan`, and
converts the raw library names into :class:`DependencyEntry` objects —
the planned-dependency objects that record the full metadata the spec
requires:

* name
* type (library, framework, tool, etc.)
* suggested version
* version constraint
* reason (why this dependency is needed)
* source (where it was discovered)
* source components (which components require it)
* priority (the broad resolution phase)
* language, framework, OS compatibility
* reputation, trust, stability, official, extensible

The determiner consolidates the libraries declared in the blueprint
(``ProjectIdentity.libraries``), the framework, the database driver,
and the libraries inferred from the component analysis into a single,
deduplicated list of :class:`DependencyEntry` objects.

Data source
-----------
The determiner reads **only**:

1. the :class:`ComponentAnalysisResult` (from the
   :class:`ComponentAnalyzer`),
2. the :class:`ProjectBlueprint` (for the declared libraries and
   framework),
3. the :class:`ProjectStructureMap` (for project context), and
4. the :class:`FileGenerationPlan` (for file-level context).

It does **not** read the user's request.
"""

from __future__ import annotations

from typing import Dict, List

from ..component_detector.registry import ComponentRegistry
from ..file_planner.plan_data import FileGenerationPlan
from ..project_planner.blueprint import ProjectBlueprint
from ..structure_generator.structure_map import ProjectStructureMap
from .component_analyzer import ComponentAnalysisResult
from .report_data import (
    DEPENDENCY_PRIORITY_CORE,
    DEPENDENCY_PRIORITY_DATABASE,
    DEPENDENCY_PRIORITY_DEV,
    DEPENDENCY_PRIORITY_ENTRY,
    DEPENDENCY_PRIORITY_FEATURES,
    DEPENDENCY_PRIORITY_INFRASTRUCTURE,
    DEPENDENCY_PRIORITY_TESTS,
    DEPENDENCY_PRIORITY_WIRING,
    DEPENDENCY_TYPE_BUILD,
    DEPENDENCY_TYPE_DEV,
    DEPENDENCY_TYPE_FRAMEWORK,
    DEPENDENCY_TYPE_LIBRARY,
    DEPENDENCY_TYPE_TEST,
    DEPENDENCY_TYPE_TOOL,
    DependencyEntry,
    REPUTATION_GOOD,
    REPUTATION_UNKNOWN,
    SOURCE_BLUEPRINT,
    SOURCE_COMPONENT,
    SOURCE_FRAMEWORK,
    STABILITY_STABLE,
    TRUST_OFFICIAL,
    TRUST_COMMUNITY,
    TRUST_UNKNOWN,
)


# ---------------------------------------------------------------------------#
# Known library metadata table
# ---------------------------------------------------------------------------#
#
# This table provides known metadata for common libraries, frameworks,
# and tools.  When a library is encountered, the determiner looks it up
# here to assign a suggested version, type, priority, OS compatibility,
# reputation, trust, stability, and official status.  Unknown libraries
# receive conservative defaults.

_KNOWN_LIBRARIES: Dict[str, Dict[str, object]] = {
    "python-telegram-bot": {
        "type": DEPENDENCY_TYPE_FRAMEWORK,
        "suggested_version": "21.x",
        "version_constraint": ">=20.0,<22.0",
        "priority": DEPENDENCY_PRIORITY_INFRASTRUCTURE,
        "language": "python",
        "framework": "python-telegram-bot",
        "os_compatibility": ["linux", "windows", "macos"],
        "reputation": REPUTATION_GOOD,
        "trust": TRUST_OFFICIAL,
        "stability": STABILITY_STABLE,
        "official": True,
        "reason": "The core Telegram bot framework for the project.",
    },
    "SQLAlchemy": {
        "type": DEPENDENCY_TYPE_LIBRARY,
        "suggested_version": "2.x",
        "version_constraint": ">=2.0,<3.0",
        "priority": DEPENDENCY_PRIORITY_DATABASE,
        "language": "python",
        "framework": "",
        "os_compatibility": ["linux", "windows", "macos"],
        "reputation": REPUTATION_GOOD,
        "trust": TRUST_OFFICIAL,
        "stability": STABILITY_STABLE,
        "official": True,
        "reason": "SQL toolkit and Object-Relational Mapper for database access.",
    },
    "alembic": {
        "type": DEPENDENCY_TYPE_TOOL,
        "suggested_version": "1.x",
        "version_constraint": ">=1.10,<2.0",
        "priority": DEPENDENCY_PRIORITY_DATABASE,
        "language": "python",
        "framework": "",
        "os_compatibility": ["linux", "windows", "macos"],
        "reputation": REPUTATION_GOOD,
        "trust": TRUST_OFFICIAL,
        "stability": STABILITY_STABLE,
        "official": True,
        "reason": "Database migration tool for SQLAlchemy.",
    },
    "psycopg2": {
        "type": DEPENDENCY_TYPE_LIBRARY,
        "suggested_version": "2.x",
        "version_constraint": ">=2.9,<3.0",
        "priority": DEPENDENCY_PRIORITY_DATABASE,
        "language": "python",
        "framework": "",
        "os_compatibility": ["linux", "windows", "macos"],
        "reputation": REPUTATION_GOOD,
        "trust": TRUST_OFFICIAL,
        "stability": STABILITY_STABLE,
        "official": True,
        "reason": "PostgreSQL database adapter for Python.",
    },
    "psycopg2-binary": {
        "type": DEPENDENCY_TYPE_LIBRARY,
        "suggested_version": "2.x",
        "version_constraint": ">=2.9,<3.0",
        "priority": DEPENDENCY_PRIORITY_DATABASE,
        "language": "python",
        "framework": "",
        "os_compatibility": ["linux", "windows", "macos"],
        "reputation": REPUTATION_GOOD,
        "trust": TRUST_COMMUNITY,
        "stability": STABILITY_STABLE,
        "official": True,
        "reason": "Binary distribution of the PostgreSQL adapter (no compilation needed).",
    },
    "aiosqlite": {
        "type": DEPENDENCY_TYPE_LIBRARY,
        "suggested_version": "0.x",
        "version_constraint": ">=0.19,<1.0",
        "priority": DEPENDENCY_PRIORITY_DATABASE,
        "language": "python",
        "framework": "",
        "os_compatibility": ["linux", "windows", "macos"],
        "reputation": REPUTATION_GOOD,
        "trust": TRUST_OFFICIAL,
        "stability": STABILITY_STABLE,
        "official": True,
        "reason": "Asyncio support for SQLite, used with async SQLAlchemy.",
    },
    "redis": {
        "type": DEPENDENCY_TYPE_LIBRARY,
        "suggested_version": "5.x",
        "version_constraint": ">=4.0,<6.0",
        "priority": DEPENDENCY_PRIORITY_DATABASE,
        "language": "python",
        "framework": "",
        "os_compatibility": ["linux", "windows", "macos"],
        "reputation": REPUTATION_GOOD,
        "trust": TRUST_OFFICIAL,
        "stability": STABILITY_STABLE,
        "official": True,
        "reason": "Redis client for caching and session storage.",
    },
    "aiohttp": {
        "type": DEPENDENCY_TYPE_LIBRARY,
        "suggested_version": "3.x",
        "version_constraint": ">=3.8,<4.0",
        "priority": DEPENDENCY_PRIORITY_CORE,
        "language": "python",
        "framework": "",
        "os_compatibility": ["linux", "windows", "macos"],
        "reputation": REPUTATION_GOOD,
        "trust": TRUST_OFFICIAL,
        "stability": STABILITY_STABLE,
        "official": True,
        "reason": "Async HTTP client for external API calls.",
    },
    "httpx": {
        "type": DEPENDENCY_TYPE_LIBRARY,
        "suggested_version": "0.x",
        "version_constraint": ">=0.24,<1.0",
        "priority": DEPENDENCY_PRIORITY_CORE,
        "language": "python",
        "framework": "",
        "os_compatibility": ["linux", "windows", "macos"],
        "reputation": REPUTATION_GOOD,
        "trust": TRUST_OFFICIAL,
        "stability": STABILITY_STABLE,
        "official": True,
        "reason": "HTTP client library for external API calls.",
    },
    "pydantic": {
        "type": DEPENDENCY_TYPE_LIBRARY,
        "suggested_version": "2.x",
        "version_constraint": ">=2.0,<3.0",
        "priority": DEPENDENCY_PRIORITY_CORE,
        "language": "python",
        "framework": "",
        "os_compatibility": ["linux", "windows", "macos"],
        "reputation": REPUTATION_GOOD,
        "trust": TRUST_OFFICIAL,
        "stability": STABILITY_STABLE,
        "official": True,
        "reason": "Data validation and settings management.",
    },
    "python-dotenv": {
        "type": DEPENDENCY_TYPE_LIBRARY,
        "suggested_version": "1.x",
        "version_constraint": ">=1.0,<2.0",
        "priority": DEPENDENCY_PRIORITY_INFRASTRUCTURE,
        "language": "python",
        "framework": "",
        "os_compatibility": ["linux", "windows", "macos"],
        "reputation": REPUTATION_GOOD,
        "trust": TRUST_OFFICIAL,
        "stability": STABILITY_STABLE,
        "official": True,
        "reason": "Environment variable loading from .env files.",
    },
    "pytest": {
        "type": DEPENDENCY_TYPE_TEST,
        "suggested_version": "8.x",
        "version_constraint": ">=7.0,<9.0",
        "priority": DEPENDENCY_PRIORITY_TESTS,
        "language": "python",
        "framework": "",
        "os_compatibility": ["linux", "windows", "macos"],
        "reputation": REPUTATION_GOOD,
        "trust": TRUST_OFFICIAL,
        "stability": STABILITY_STABLE,
        "official": True,
        "reason": "Testing framework for the project's test suite.",
    },
    "pytest-asyncio": {
        "type": DEPENDENCY_TYPE_TEST,
        "suggested_version": "0.x",
        "version_constraint": ">=0.21,<1.0",
        "priority": DEPENDENCY_PRIORITY_TESTS,
        "language": "python",
        "framework": "",
        "os_compatibility": ["linux", "windows", "macos"],
        "reputation": REPUTATION_GOOD,
        "trust": TRUST_OFFICIAL,
        "stability": STABILITY_STABLE,
        "official": True,
        "reason": "Async test support for pytest.",
    },
    "black": {
        "type": DEPENDENCY_TYPE_DEV,
        "suggested_version": "24.x",
        "version_constraint": ">=23.0,<25.0",
        "priority": DEPENDENCY_PRIORITY_DEV,
        "language": "python",
        "framework": "",
        "os_compatibility": ["linux", "windows", "macos"],
        "reputation": REPUTATION_GOOD,
        "trust": TRUST_OFFICIAL,
        "stability": STABILITY_STABLE,
        "official": True,
        "reason": "Code formatter for development.",
    },
    "flake8": {
        "type": DEPENDENCY_TYPE_DEV,
        "suggested_version": "7.x",
        "version_constraint": ">=6.0,<8.0",
        "priority": DEPENDENCY_PRIORITY_DEV,
        "language": "python",
        "framework": "",
        "os_compatibility": ["linux", "windows", "macos"],
        "reputation": REPUTATION_GOOD,
        "trust": TRUST_OFFICIAL,
        "stability": STABILITY_STABLE,
        "official": True,
        "reason": "Linter for development.",
    },
    "mypy": {
        "type": DEPENDENCY_TYPE_DEV,
        "suggested_version": "1.x",
        "version_constraint": ">=1.0,<2.0",
        "priority": DEPENDENCY_PRIORITY_DEV,
        "language": "python",
        "framework": "",
        "os_compatibility": ["linux", "windows", "macos"],
        "reputation": REPUTATION_GOOD,
        "trust": TRUST_OFFICIAL,
        "stability": STABILITY_STABLE,
        "official": True,
        "reason": "Static type checker for development.",
    },
    "uvicorn": {
        "type": DEPENDENCY_TYPE_TOOL,
        "suggested_version": "0.x",
        "version_constraint": ">=0.24,<1.0",
        "priority": DEPENDENCY_PRIORITY_CORE,
        "language": "python",
        "framework": "",
        "os_compatibility": ["linux", "windows", "macos"],
        "reputation": REPUTATION_GOOD,
        "trust": TRUST_OFFICIAL,
        "stability": STABILITY_STABLE,
        "official": True,
        "reason": "ASGI server for running the application.",
    },
}

# Needed for the type hints in _KNOWN_LIBRARIES value dict.
from .report_data import (  # noqa: E402
    TRUST_COMMUNITY,
)


# ---------------------------------------------------------------------------#
# Database → driver mapping
# ---------------------------------------------------------------------------#
#
# Maps the blueprint's database choice to the required driver library.

_DATABASE_DRIVERS: Dict[str, str] = {
    "postgres": "psycopg2",
    "postgresql": "psycopg2",
    "sqlite": "aiosqlite",
    "redis": "redis",
    "mysql": "mysqlclient",
}


class LibraryDeterminer:
    """Stateless helper that determines the required dependencies.

    The determiner is called by the
    :class:`DependencyResolutionEngine` after the
    :class:`ComponentAnalyzer` has grouped the components' required
    libraries.  It converts the raw library names into
    :class:`DependencyEntry` objects with the full resolution metadata.

    The determiner is **pure**: it does not modify the blueprint, the
    component analysis result, the structure map, or the file plan.
    It produces a new list of :class:`DependencyEntry` objects.
    """

    def determine(
        self,
        analysis: ComponentAnalysisResult,
        blueprint: ProjectBlueprint,
        structure_map: ProjectStructureMap,
        file_plan: FileGenerationPlan,
        registry: ComponentRegistry,
    ) -> List[DependencyEntry]:
        """Determine the required dependencies and their metadata.

        Parameters:
            analysis: The component analysis result.
            blueprint: The project blueprint.
            structure_map: The project structure map.
            file_plan: The file generation plan.
            registry: The component registry.

        Returns:
            A list of :class:`DependencyEntry` objects — the complete,
            deduplicated list of every dependency the project needs.
        """
        # Build a library → source-components mapping.
        lib_to_components: Dict[str, List[str]] = {}
        for comp_name, comp_analysis in analysis.analyses.items():
            for lib in comp_analysis.required_libraries:
                lib_to_components.setdefault(lib, []).append(comp_name)

        # Collect all library names to resolve.
        all_lib_names: List[str] = []

        # The framework is always the first dependency.
        framework = blueprint.identity.framework
        if framework:
            all_lib_names.append(framework)

        # Libraries declared in the blueprint.
        for lib in blueprint.identity.libraries:
            if lib not in all_lib_names:
                all_lib_names.append(lib)

        # Libraries inferred from the component analysis.
        for lib in analysis.all_required_libraries:
            if lib not in all_lib_names:
                all_lib_names.append(lib)

        # Database driver (if a database is configured).
        database = blueprint.identity.database
        if database:
            driver = _DATABASE_DRIVERS.get(database, "")
            if driver and driver not in all_lib_names:
                all_lib_names.append(driver)

        # Always include python-dotenv for environment loading.
        if "python-dotenv" not in all_lib_names:
            all_lib_names.append("python-dotenv")

        # Build the entries.
        entries: List[DependencyEntry] = []
        for name in all_lib_names:
            entry = self._make_entry(
                name,
                blueprint,
                lib_to_components,
                is_framework=(name == framework),
            )
            entries.append(entry)

        return entries

    # -----------------------------------------------------------------#
    # Internal helpers
    # -----------------------------------------------------------------#

    def _make_entry(
        self,
        name: str,
        blueprint: ProjectBlueprint,
        lib_to_components: Dict[str, List[str]],
        is_framework: bool,
    ) -> DependencyEntry:
        """Build a single :class:`DependencyEntry` from a library name."""
        known = _KNOWN_LIBRARIES.get(name, {})

        # Determine the source.
        if is_framework:
            source = SOURCE_FRAMEWORK
            reason = known.get(
                "reason",
                f"Framework '{name}' is the primary framework for the project.",
            )
        elif name in blueprint.identity.libraries:
            source = SOURCE_BLUEPRINT
            reason = known.get(
                "reason",
                f"Library '{name}' is declared in the project blueprint.",
            )
        elif name in lib_to_components:
            source = SOURCE_COMPONENT
            comps = lib_to_components[name]
            reason = known.get(
                "reason",
                f"Library '{name}' is required by component(s): "
                f"{', '.join(comps)}.",
            )
        else:
            source = SOURCE_COMPONENT
            reason = known.get(
                "reason",
                f"Library '{name}' is required by the project.",
            )

        return DependencyEntry(
            name=name,
            type=str(known.get("type", DEPENDENCY_TYPE_LIBRARY)),
            suggested_version=str(known.get("suggested_version", "latest")),
            version_constraint=str(known.get("version_constraint", "")),
            reason=str(reason),
            source=source,
            source_components=list(lib_to_components.get(name, [])),
            priority=int(known.get("priority", DEPENDENCY_PRIORITY_CORE)),
            language=str(known.get("language", blueprint.identity.language)),
            framework=str(known.get("framework", "")),
            os_compatibility=list(
                known.get("os_compatibility", ["linux", "windows", "macos"])
            ),
            reputation=str(known.get("reputation", REPUTATION_UNKNOWN)),
            trust=str(known.get("trust", TRUST_UNKNOWN)),
            stability=str(known.get("stability", STABILITY_STABLE)),
            official=bool(known.get("official", False)),
            extensible=True,
        )


__all__ = ["LibraryDeterminer"]
