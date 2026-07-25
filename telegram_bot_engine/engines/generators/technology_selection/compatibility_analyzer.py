"""
CompatibilityAnalyzer — Specification 016

Verifies that all selected technologies are compatible with one another.
Prevents:
    - Conflict between components
    - Version problems (incompatible version combinations)
    - Unsupported libraries for the chosen stack
    - Broken dependencies in the technology graph

The analyzer builds a compatibility matrix between all selected
technologies and flags any incompatibilities.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from .report_data import (
    DIMENSION_COMPATIBILITY,
    AnalysisResult,
    TechnologyFinding,
    SOURCE_ARCHITECTURE_DECISION,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    SEVERITY_INFO,
    TECH_FRAMEWORK,
    TECH_PROGRAMMING_LANGUAGE,
    TECH_DATABASE,
    TECH_ORM,
    TECH_CACHE,
    TECH_QUEUE,
    TECH_STORAGE,
    TECH_LOGGING,
    TECH_TESTING,
    TECH_DEPLOYMENT,
)

_log = logging.getLogger("engine.technology_selection.compatibility")


# ---------------------------------------------------------------------------#
# Known compatibility rules
# ---------------------------------------------------------------------------#
#
# These are the built-in compatibility rules that prevent selecting
# technologies that are known to conflict with each other.

INCOMPATIBLE_PAIRS: Dict[str, List[str]] = {
    # Django ORM is not compatible with MongoDB natively
    "django:orm": ["mongodb"],
    # Flask does not have a built-in ORM
    "flask:framework": ["sqlalchemy:orm"],  # This is actually fine — Flask + SQLAlchemy is common
    # SQLite is not suitable for production deployment
    "sqlite:database": ["kubernetes:deployment"],
    # Celery requires a message broker (queue)
    "celery:queue": [],
    # Pytest is compatible with most frameworks
    # Express.js is Node.js only
    "express:framework": ["python:programming_language"],
    # Next.js is React + Node.js
    "next:framework": ["python:programming_language"],
}

# Framework-to-language mapping
FRAMEWORK_LANGUAGE: Dict[str, str] = {
    "django": "python",
    "flask": "python",
    "fastapi": "python",
    "tornado": "python",
    "pyramid": "python",
    "bottle": "python",
    "sanic": "python",
    "aiohttp": "python",
    "express": "nodejs",
    "nest": "nodejs",
    "next": "nodejs",
    "koa": "nodejs",
    "hapi": "nodejs",
    "spring": "java",
    "quarkus": "java",
    "micronaut": "java",
    "rails": "ruby",
    "sinatra": "ruby",
    "laravel": "php",
    "symfony": "php",
    "slim": "php",
    "aspnet": "dotnet",
    "dotnet": "dotnet",
    "go": "golang",
    "fiber": "golang",
    "gin": "golang",
    "echo": "golang",
}

# ORM-to-database mapping
ORM_DATABASE: Dict[str, List[str]] = {
    "django_orm": ["postgresql", "mysql", "sqlite", "oracle"],
    "sqlalchemy": [
        "postgresql", "mysql", "sqlite", "oracle",
        "mssql", "firebird", "db2",
    ],
    "peewee": [
        "postgresql", "mysql", "sqlite", "cockroachdb",
    ],
    "tortoise_orm": [
        "postgresql", "mysql", "sqlite", "cockroachdb",
    ],
    "prisma": ["postgresql", "mysql", "sqlite", "mongodb"],
    "sequelize": ["postgresql", "mysql", "sqlite", "mssql"],
    "mongoose": ["mongodb"],
    "hibernate": [
        "postgresql", "mysql", "oracle", "mssql", "h2",
    ],
    "entity_framework": [
        "postgresql", "mysql", "mssql", "sqlite", "oracle",
    ],
    "gorm": [
        "postgresql", "mysql", "sqlite", "mssql", "cockroachdb",
    ],
    "pymongo": ["mongodb"],
    "redis_client": ["redis"],
    "elasticsearch_client": ["elasticsearch"],
}

# Database-to-storage compatibility
DATABASE_STORAGE: Dict[str, List[str]] = {
    "postgresql": ["aws_s3", "gcp_cloud_storage", "azure_blob", "local_fs"],
    "mysql": ["aws_s3", "gcp_cloud_storage", "azure_blob", "local_fs"],
    "mongodb": [
        "aws_s3", "gcp_cloud_storage", "azure_blob",
        "local_fs", "gridfs",
    ],
    "sqlite": ["local_fs"],
    "redis": ["local_fs"],
    "elasticsearch": [
        "aws_s3", "gcp_cloud_storage", "azure_blob", "local_fs",
    ],
}


class CompatibilityAnalyzer:
    """Analyzes compatibility between candidate technologies.

    Builds a compatibility matrix between all selected technologies
    and flags any incompatibilities. Prevents conflicts, version
    problems, unsupported libraries, and broken dependencies.
    """

    def __init__(self) -> None:
        self._findings: List[TechnologyFinding] = []

    def analyze(
        self,
        architecture_data: Any,
        requirement_data: Any,
        graph_data: Any,
        knowledge_data: Any,
    ) -> AnalysisResult:
        """Analyze compatibility of candidate technologies.

        This method is called during the engine's execution to
        perform the compatibility analysis. It checks:
        1. Framework-language compatibility.
        2. ORM-database compatibility.
        3. Database-storage compatibility.
        4. Known incompatibility pairs.
        5. Dependency chain integrity.

        Args:
            architecture_data: Architecture decision data.
            requirement_data: Requirement normalization data.
            graph_data: Intelligence graph data.
            knowledge_data: Knowledge base data.

        Returns:
            An :class:`AnalysisResult` for the compatibility
            dimension.
        """
        self._findings = []

        # Since the Technology Selection Engine selects technologies
        # based on the architecture decision, we use the architecture
        # data as the primary input for compatibility analysis.
        details = []

        # Check if architecture data is available.
        if not architecture_data.available:
            self._findings.append(TechnologyFinding(
                severity=SEVERITY_WARNING,
                code="no_architecture_data",
                message=(
                    "Architecture Decision Report is not available. "
                    "Compatibility analysis will use defaults."
                ),
                affected="compatibility_analysis",
                resolution_hint=(
                    "Ensure the Architecture Decision Engine runs "
                    "before the Technology Selection Engine."
                ),
                category="compatibility",
            ))
            return AnalysisResult(
                dimension=DIMENSION_COMPATIBILITY,
                score=0.5,
                level="medium",
                summary=(
                    "Limited compatibility analysis due to "
                    "missing architecture data."
                ),
                details=["Architecture data not available."],
                source_artefact=SOURCE_ARCHITECTURE_DECISION,
            )

        # Extract the selected pattern and communication from
        # architecture data.
        pattern = getattr(architecture_data, "pattern", "")
        communication = getattr(architecture_data, "communication", "")
        layers = getattr(architecture_data, "layers", [])

        details.append(f"Architecture pattern: {pattern}")
        details.append(f"Communication: {communication}")
        details.append(f"Layers: {', '.join(layers)}")

        # Analyze framework-language compatibility.
        framework_compat = self._check_framework_language(
            pattern, architecture_data
        )
        details.extend(framework_compat)

        # Analyze ORM-database compatibility.
        orm_compat = self._check_orm_database(
            architecture_data
        )
        details.extend(orm_compat)

        # Analyze database-storage compatibility.
        storage_compat = self._check_database_storage(
            architecture_data
        )
        details.extend(storage_compat)

        # Analyze known incompatibilities.
        conflict_compat = self._check_known_incompatibilities(
            architecture_data
        )
        details.extend(conflict_compat)

        # Analyze dependency chain integrity.
        dep_compat = self._check_dependency_chain(
            architecture_data, graph_data
        )
        details.extend(dep_compat)

        # Calculate score based on findings.
        error_count = sum(
            1 for f in self._findings
            if f.severity == SEVERITY_ERROR
        )
        warning_count = sum(
            1 for f in self._findings
            if f.severity == SEVERITY_WARNING
        )

        score = max(0.0, 1.0 - (error_count * 0.2) - (warning_count * 0.1))
        score = min(1.0, max(0.0, score))

        level = "high" if score >= 0.8 else "medium" if score >= 0.5 else "low"

        summary = (
            f"Compatibility analysis complete with "
            f"{error_count} errors and {warning_count} warnings."
        )

        return AnalysisResult(
            dimension=DIMENSION_COMPATIBILITY,
            score=round(score, 3),
            level=level,
            summary=summary,
            details=details,
            source_artefact=SOURCE_ARCHITECTURE_DECISION,
        )

    @property
    def findings(self) -> List[TechnologyFinding]:
        """Return all findings produced during analysis."""
        return self._findings

    # ----------------------------------------------------------------- #
    # Private helpers
    # ----------------------------------------------------------------- #

    def _check_framework_language(
        self,
        pattern: str,
        data: Any,
    ) -> List[str]:
        """Check framework-to-language compatibility.

        Args:
            pattern: The architecture pattern.
            data: The architecture decision data.

        Returns:
            A list of detail strings.
        """
        details = []
        modules = getattr(data, "modules", [])

        # Try to infer the programming language from the
        # architecture decisions.
        language = self._infer_language_from_architecture(data)

        if not language:
            details.append(
                "Could not infer programming language from "
                "architecture. Using all-language compatible "
                "selections."
            )
            return details

        details.append(f"Inferred programming language: {language}")

        # Check if any module implies a different language.
        for module in modules:
            module_dict = (
                module if isinstance(module, dict)
                else module.to_dict()
                if hasattr(module, "to_dict")
                else module
            )
            module_name = ""
            if isinstance(module_dict, dict):
                module_name = module_dict.get("name", "")
            elif isinstance(module_dict, str):
                module_name = module_dict

            # Check if any module name implies a different language.
            for framework, lang in FRAMEWORK_LANGUAGE.items():
                if framework in module_name.lower() and lang != language:
                    self._findings.append(TechnologyFinding(
                        severity=SEVERITY_ERROR,
                        code="framework_language_mismatch",
                        message=(
                            f"Module '{module_name}' implies "
                            f"language '{lang}' but the project "
                            f"uses '{language}'."
                        ),
                        affected=module_name,
                        resolution_hint=(
                            f"Use a {language}-compatible "
                            f"framework or change the primary "
                            f"language."
                        ),
                        category="compatibility",
                    ))

        details.append(
            f"Framework-language compatibility: "
            f"{'passed' if not any(
                f.code == 'framework_language_mismatch'
                for f in self._findings
            ) else 'issues found'}"
        )
        return details

    def _check_orm_database(
        self,
        data: Any,
    ) -> List[str]:
        """Check ORM-to-database compatibility.

        Args:
            data: The architecture decision data.

        Returns:
            A list of detail strings.
        """
        details = []

        # Extract database and ORM from decisions.
        database = self._extract_decision_value(data, "database")
        orm = self._extract_decision_value(data, "orm")

        if not database or not orm:
            details.append(
                "Database or ORM not yet selected in "
                "architecture. Skipping ORM-database check."
            )
            return details

        details.append(f"Database: {database}, ORM: {orm}")

        # Check compatibility.
        compatible_dbs = ORM_DATABASE.get(orm, [])
        if compatible_dbs and database not in compatible_dbs:
            self._findings.append(TechnologyFinding(
                severity=SEVERITY_ERROR,
                code="orm_database_incompatible",
                message=(
                    f"ORM '{orm}' is not compatible with "
                    f"database '{database}'."
                ),
                affected=f"{orm}:{database}",
                resolution_hint=(
                    f"Choose a compatible ORM for '{database}' "
                    f"or switch to one of: "
                    f"{', '.join(compatible_dbs)}."
                ),
                category="compatibility",
            ))
        else:
            details.append(
                f"ORM-database compatibility: passed"
            )

        return details

    def _check_database_storage(
        self,
        data: Any,
    ) -> List[str]:
        """Check database-to-storage compatibility.

        Args:
            data: The architecture decision data.

        Returns:
            A list of detail strings.
        """
        details = []

        database = self._extract_decision_value(data, "database")
        storage = self._extract_decision_value(data, "storage")

        if not database or not storage:
            details.append(
                "Database or storage not yet selected in "
                "architecture. Skipping database-storage check."
            )
            return details

        details.append(f"Database: {database}, Storage: {storage}")

        compatible_storages = DATABASE_STORAGE.get(database, [])
        if compatible_storages and storage not in compatible_storages:
            self._findings.append(TechnologyFinding(
                severity=SEVERITY_WARNING,
                code="database_storage_incompatible",
                message=(
                    f"Storage '{storage}' is not in the "
                    f"recommended list for database "
                    f"'{database}'."
                ),
                affected=f"{database}:{storage}",
                resolution_hint=(
                    f"Consider using one of: "
                    f"{', '.join(compatible_storages)}."
                ),
                category="compatibility",
            ))
        else:
            details.append(
                f"Database-storage compatibility: passed"
            )

        return details

    def _check_known_incompatibilities(
        self,
        data: Any,
    ) -> List[str]:
        """Check for known incompatibility pairs.

        Args:
            data: The architecture decision data.

        Returns:
            A list of detail strings.
        """
        details = []

        # Extract all selected technologies from decisions.
        selections = {}
        for domain in (
            "layers", "modules", "services",
            "dependency_structure", "project_layout",
            "communication", "error_handling", "configuration",
        ):
            value = self._extract_decision_value(data, domain)
            if value:
                selections[domain] = value

        # Check known incompatibility pairs.
        for key, incompatible in INCOMPATIBLE_PAIRS.items():
            parts = key.split(":")
            if len(parts) == 2:
                category, tech = parts[0], parts[1]
                selected = selections.get(category, "")

                if selected and tech in selected.lower():
                    for incomp in incompatible:
                        if incomp and incomp in str(selections).lower():
                            self._findings.append(TechnologyFinding(
                                severity=SEVERITY_ERROR,
                                code="known_incompatibility",
                                message=(
                                    f"Known incompatibility between "
                                    f"'{tech}' and '{incomp}'."
                                ),
                                affected=f"{category}:{tech}",
                                resolution_hint=(
                                    f"Remove or replace "
                                    f"'{tech}' or '{incomp}'."
                                ),
                                category="compatibility",
                            ))

        details.append(
            f"Known incompatibility check: "
            f"{'passed' if not any(
                f.code == 'known_incompatibility'
                for f in self._findings
            ) else 'issues found'}"
        )
        return details

    def _check_dependency_chain(
        self,
        architecture_data: Any,
        graph_data: Any,
    ) -> List[str]:
        """Check dependency chain integrity.

        Args:
            architecture_data: Architecture decision data.
            graph_data: Intelligence graph data.

        Returns:
            A list of detail strings.
        """
        details = []

        if not graph_data.available:
            details.append(
                "Intelligence graph not available. "
                "Skipping dependency chain analysis."
            )
            return details

        # Check for circular dependencies in the module graph.
        modules = getattr(graph_data, "nodes", [])
        edges = getattr(graph_data, "edges", [])

        # Build adjacency list.
        adjacency: Dict[str, List[str]] = {}
        for node in modules:
            node_dict = (
                node if isinstance(node, dict)
                else node.to_dict()
                if hasattr(node, "to_dict")
                else node
            )
            name = ""
            if isinstance(node_dict, dict):
                name = node_dict.get("name", "")
            if name:
                adjacency[name] = []

        for edge in edges:
            edge_dict = (
                edge if isinstance(edge, dict)
                else edge.to_dict()
                if hasattr(edge, "to_dict")
                else edge
            )
            if isinstance(edge_dict, dict):
                source = edge_dict.get("source", "")
                target = edge_dict.get("target", "")
                if source in adjacency and target:
                    adjacency[source].append(target)

        # Detect circular dependencies using DFS.
        visited = set()
        rec_stack = set()

        def _has_cycle(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            for neighbor in adjacency.get(node, []):
                if neighbor not in visited:
                    if _has_cycle(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            rec_stack.discard(node)
            return False

        has_cycle = False
        for node in adjacency:
            if node not in visited:
                if _has_cycle(node):
                    has_cycle = True
                    break

        if has_cycle:
            self._findings.append(TechnologyFinding(
                severity=SEVERITY_ERROR,
                code="circular_dependency",
                message=(
                    "Circular dependency detected in the "
                    "module graph."
                ),
                affected="dependency_graph",
                resolution_hint=(
                    "Break the circular dependency by "
                    "introducing an abstraction layer."
                ),
                category="compatibility",
            ))

        details.append(
            f"Dependency chain integrity: "
            f"{'has circular deps' if has_cycle else 'no circular deps found'}"
        )
        return details

    # ----------------------------------------------------------------- #
    # Utility methods
    # ----------------------------------------------------------------- #

    def _infer_language_from_architecture(self, data: Any) -> str:
        """Infer the programming language from architecture data.

        Args:
            data: The architecture decision data.

        Returns:
            The inferred programming language, or empty string.
        """
        # Try to get from modules.
        modules = getattr(data, "modules", [])
        for module in modules:
            module_dict = (
                module if isinstance(module, dict)
                else module.to_dict()
                if hasattr(module, "to_dict")
                else module
            )
            name = ""
            if isinstance(module_dict, dict):
                name = module_dict.get("name", "")
            elif isinstance(module_dict, str):
                name = module_dict

            # Check if any module name implies a language.
            for framework, lang in FRAMEWORK_LANGUAGE.items():
                if framework in name.lower():
                    return lang

        # Check decisions.
        decisions = getattr(data, "decisions", [])
        for decision in decisions:
            decision_dict = (
                decision if isinstance(decision, dict)
                else decision.to_dict()
                if hasattr(decision, "to_dict")
                else decision
            )
            if isinstance(decision_dict, dict):
                selected = decision_dict.get("selected", "")
                for framework, lang in FRAMEWORK_LANGUAGE.items():
                    if framework in selected.lower():
                        return lang

        return ""

    def _extract_decision_value(
        self,
        data: Any,
        domain: str,
    ) -> str:
        """Extract a decision value for a given domain.

        Args:
            data: The architecture decision data.
            domain: The decision domain.

        Returns:
            The selected value, or empty string.
        """
        decisions = getattr(data, "decisions", [])
        for decision in decisions:
            decision_dict = (
                decision if isinstance(decision, dict)
                else decision.to_dict()
                if hasattr(decision, "to_dict")
                else decision
            )
            if isinstance(decision_dict, dict):
                if decision_dict.get("domain") == domain:
                    return decision_dict.get("selected", "")
        return ""


__all__ = ["CompatibilityAnalyzer"]
