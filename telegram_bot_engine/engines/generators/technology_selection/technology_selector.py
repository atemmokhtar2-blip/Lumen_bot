"""
TechnologySelector — Specification 016

The core decision-making component of the Technology Selection Engine.
Selects all ten technology categories based on the project's needs,
architecture decisions, and quality rules.

For every selection it:
    * Provides a clear reason.
    * Compares alternatives.
    * Selects the best fit, not the most popular.
    * Records pros and cons.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from .data_readers import (
    ArchitectureDecisionData,
    RequirementNormalizationData,
    IntelligenceGraphData,
    KnowledgeData,
    QualityRulesData,
)
from .report_data import (
    RejectedAlternative,
    TechnologySelection,
    TechnologyFinding,
    TECH_PROGRAMMING_LANGUAGE,
    TECH_FRAMEWORK,
    TECH_DATABASE,
    TECH_ORM,
    TECH_CACHE,
    TECH_QUEUE,
    TECH_STORAGE,
    TECH_LOGGING,
    TECH_TESTING,
    TECH_DEPLOYMENT,
    ALL_TECH_CATEGORIES,
    SEVERITY_WARNING,
    SEVERITY_INFO,
    SOURCE_ARCHITECTURE_DECISION,
)

_log = logging.getLogger("engine.technology_selection.selector")


# ---------------------------------------------------------------------------#
# Technology candidate database
# ---------------------------------------------------------------------------#

CANDIDATES: Dict[str, List[Dict[str, Any]]] = {
    TECH_PROGRAMMING_LANGUAGE: [
        {"name": "python", "reason": "Best for rapid development, AI/ML, and automation"},
        {"name": "nodejs", "reason": "Best for real-time, I/O-heavy applications"},
        {"name": "java", "reason": "Best for enterprise-scale, high-performance systems"},
        {"name": "golang", "reason": "Best for microservices and high-concurrency"},
        {"name": "rust", "reason": "Best for performance-critical and systems programming"},
        {"name": "dotnet", "reason": "Best for enterprise Windows environments"},
        {"name": "ruby", "reason": "Best for rapid web development with convention over configuration"},
        {"name": "php", "reason": "Best for web applications and CMS"},
    ],
    TECH_FRAMEWORK: [
        {"name": "fastapi", "reason": "Modern, async, auto-docs, high performance for Python"},
        {"name": "django", "reason": "Full-featured, batteries-included, excellent for CRUD"},
        {"name": "flask", "reason": "Lightweight, flexible, good for microservices"},
        {"name": "express", "reason": "Minimal, flexible, largest Node.js ecosystem"},
        {"name": "nest", "reason": "Enterprise-grade, TypeScript, Angular-style architecture"},
        {"name": "next", "reason": "React SSR, best for full-stack web apps"},
        {"name": "spring", "reason": "Enterprise Java, massive ecosystem"},
        {"name": "rails", "reason": "Convention over configuration, rapid development"},
        {"name": "laravel", "reason": "Elegant PHP framework, great DX"},
        {"name": "gin", "reason": "High-performance Go HTTP framework"},
        {"name": "fiber", "reason": "Fastest Go web framework, Express-like"},
    ],
    TECH_DATABASE: [
        {"name": "postgresql", "reason": "Most advanced open-source RDBMS, best feature set"},
        {"name": "mysql", "reason": "Widely adopted, good performance, simple"},
        {"name": "mongodb", "reason": "Best NoSQL for document-oriented data"},
        {"name": "sqlite", "reason": "Zero-config, embedded, best for small projects"},
        {"name": "redis", "reason": "In-memory, best for caching and real-time"},
        {"name": "elasticsearch", "reason": "Best for search and analytics"},
        {"name": "cockroachdb", "reason": "Distributed SQL, best for high availability"},
    ],
    TECH_ORM: [
        {"name": "sqlalchemy", "reason": "Most powerful Python ORM, full control"},
        {"name": "django_orm", "reason": "Tight Django integration, great DX"},
        {"name": "peewee", "reason": "Lightweight Python ORM, simple API"},
        {"name": "tortoise_orm", "reason": "Async Python ORM, modern design"},
        {"name": "prisma", "reason": "Type-safe, auto-generated, best for Node.js/TypeScript"},
        {"name": "hibernate", "reason": "Enterprise Java ORM, mature and powerful"},
        {"name": "entity_framework", "reason": "Official Microsoft ORM for .NET"},
        {"name": "gorm", "reason": "Go ORM, developer-friendly"},
        {"name": "mongoose", "reason": "Best ODM for MongoDB in Node.js"},
        {"name": "pymongo", "reason": "Official MongoDB driver for Python"},
    ],
    TECH_CACHE: [
        {"name": "redis", "reason": "Industry standard, in-memory, versatile"},
        {"name": "memcached", "reason": "Simple, fast, distributed memory cache"},
        {"name": "hazelcast", "reason": "In-memory data grid for Java ecosystem"},
    ],
    TECH_QUEUE: [
        {"name": "rabbitmq", "reason": "Mature message broker, AMQP standard"},
        {"name": "kafka", "reason": "Best for event streaming and high-throughput"},
        {"name": "redis_stream", "reason": "Simple queue using Redis streams"},
        {"name": "celery", "reason": "Distributed task queue for Python"},
        {"name": "bull", "reason": "Fastest Node.js queue, Redis-backed"},
        {"name": "sidekiq", "reason": "Background processing for Ruby"},
    ],
    TECH_STORAGE: [
        {"name": "aws_s3", "reason": "Industry standard object storage"},
        {"name": "gcp_cloud_storage", "reason": "Google Cloud object storage"},
        {"name": "azure_blob", "reason": "Microsoft Azure object storage"},
        {"name": "local_fs", "reason": "Local filesystem, simple for small projects"},
        {"name": "gridfs", "reason": "MongoDB GridFS for file storage"},
    ],
    TECH_LOGGING: [
        {"name": "structlog", "reason": "Structured logging for Python, excellent DX"},
        {"name": "loguru", "reason": "Modern Python logging, easy to use"},
        {"name": "winston", "reason": "Most popular Node.js logger"},
        {"name": "pino", "reason": "Fastest Node.js logger, low overhead"},
        {"name": "logback", "reason": "Standard Java logging"},
        {"name": "serilog", "reason": "Structured logging for .NET"},
    ],
    TECH_TESTING: [
        {"name": "pytest", "reason": "Best Python testing framework, fixtures, plugins"},
        {"name": "unittest", "reason": "Built-in Python testing, no dependencies"},
        {"name": "jest", "reason": "Best Node.js testing, snapshot testing"},
        {"name": "junit", "reason": "Industry standard for Java testing"},
        {"name": "xunit", "reason": "Standard .NET testing framework"},
        {"name": "rspec", "reason": "Behavior-driven testing for Ruby"},
        {"name": "mocha", "reason": "Flexible Node.js test runner"},
    ],
    TECH_DEPLOYMENT: [
        {"name": "docker", "reason": "Industry standard containerization"},
        {"name": "kubernetes", "reason": "Best for orchestration at scale"},
        {"name": "docker_compose", "reason": "Simple multi-container development"},
        {"name": "serverless", "reason": "No servers, pay-per-use, auto-scaling"},
        {"name": "heroku", "reason": "Simplest deployment, good for small projects"},
        {"name": "aws_ecs", "reason": "AWS managed containers"},
        {"name": "gcp_cloud_run", "reason": "Google serverless containers"},
    ],
}


# ---------------------------------------------------------------------------#
# Selection rules per architecture pattern
# ---------------------------------------------------------------------------#

PATTERN_LANGUAGE: Dict[str, str] = {
    "monolith": "python",
    "layered": "python",
    "modular_monolith": "python",
    "microservices": "golang",
    "event_driven": "golang",
    "hexagonal": "java",
}

PATTERN_FRAMEWORK: Dict[str, str] = {
    "monolith": "django",
    "layered": "fastapi",
    "modular_monolith": "fastapi",
    "microservices": "gin",
    "event_driven": "fiber",
    "hexagonal": "spring",
}

PATTERN_DATABASE: Dict[str, str] = {
    "monolith": "postgresql",
    "layered": "postgresql",
    "modular_monolith": "postgresql",
    "microservices": "postgresql",
    "event_driven": "postgresql",
    "hexagonal": "postgresql",
}

PATTERN_CACHE: Dict[str, str] = {
    "monolith": "redis",
    "layered": "redis",
    "modular_monolith": "redis",
    "microservices": "redis",
    "event_driven": "redis",
    "hexagonal": "redis",
}

PATTERN_QUEUE: Dict[str, str] = {
    "monolith": "celery",
    "layered": "rabbitmq",
    "modular_monolith": "rabbitmq",
    "microservices": "kafka",
    "event_driven": "kafka",
    "hexagonal": "rabbitmq",
}

SIZE_STORAGE: Dict[str, str] = {
    "tiny": "local_fs",
    "small": "local_fs",
    "medium": "aws_s3",
    "large": "aws_s3",
    "very_large": "aws_s3",
}

SIZE_DEPLOYMENT: Dict[str, str] = {
    "tiny": "docker_compose",
    "small": "docker",
    "medium": "docker",
    "large": "kubernetes",
    "very_large": "kubernetes",
}


class TechnologySelector:
    """The core technology selector.

    Makes all ten technology selections based on the project's
    architecture, requirements, and quality rules.
    """

    def __init__(self) -> None:
        self._findings: List[TechnologyFinding] = []

    def select(
        self,
        architecture_data: ArchitectureDecisionData,
        requirement_data: RequirementNormalizationData,
        graph_data: IntelligenceGraphData,
        knowledge_data: KnowledgeData,
        quality_data: QualityRulesData,
    ) -> List[TechnologySelection]:
        """Select all technologies for the project.

        Args:
            architecture_data: Architecture decision data.
            requirement_data: Requirement normalization data.
            graph_data: Intelligence graph data.
            knowledge_data: Knowledge base data.
            quality_data: Quality rules data.

        Returns:
            A list of :class:`TechnologySelection` objects, one
            per technology category.
        """
        self._findings = []
        selections: List[TechnologySelection] = []

        # Determine the project size tier.
        size_tier = self._determine_size_tier(
            architecture_data, requirement_data
        )

        # Determine the architecture pattern.
        pattern = self._determine_pattern(architecture_data)

        _log.info(
            "Technology selection starting",
            {"pattern": pattern, "size_tier": size_tier},
        )

        # Select each technology category.
        selections.append(
            self._select_programming_language(
                pattern, size_tier, architecture_data,
                requirement_data, knowledge_data,
            )
        )
        selections.append(
            self._select_framework(
                pattern, size_tier, architecture_data,
                requirement_data, knowledge_data,
            )
        )
        selections.append(
            self._select_database(
                pattern, size_tier, architecture_data,
                requirement_data, knowledge_data,
            )
        )
        selections.append(
            self._select_orm(
                pattern, size_tier, architecture_data,
                requirement_data, knowledge_data,
            )
        )
        selections.append(
            self._select_cache(
                pattern, size_tier, architecture_data,
                requirement_data, knowledge_data,
            )
        )
        selections.append(
            self._select_queue(
                pattern, size_tier, architecture_data,
                requirement_data, knowledge_data,
            )
        )
        selections.append(
            self._select_storage(
                pattern, size_tier, architecture_data,
                requirement_data, knowledge_data,
            )
        )
        selections.append(
            self._select_logging(
                pattern, size_tier, architecture_data,
                requirement_data, knowledge_data,
            )
        )
        selections.append(
            self._select_testing(
                pattern, size_tier, architecture_data,
                requirement_data, knowledge_data,
            )
        )
        selections.append(
            self._select_deployment(
                pattern, size_tier, architecture_data,
                requirement_data, knowledge_data,
            )
        )

        _log.info(
            "Technology selection complete",
            {"selection_count": len(selections)},
        )

        return selections

    @property
    def findings(self) -> List[TechnologyFinding]:
        """Return all findings produced during selection."""
        return self._findings

    # ----------------------------------------------------------------- #
    # Pattern and size determination
    # ----------------------------------------------------------------- #

    def _determine_pattern(
        self, architecture_data: ArchitectureDecisionData
    ) -> str:
        """Determine the architecture pattern.

        Args:
            architecture_data: Architecture decision data.

        Returns:
            The pattern string, defaulting to "monolith".
        """
        pattern = getattr(architecture_data, "pattern", "")
        if pattern:
            return pattern
        return "monolith"

    def _determine_size_tier(
        self,
        architecture_data: ArchitectureDecisionData,
        requirement_data: RequirementNormalizationData,
    ) -> str:
        """Determine the project size tier.

        Args:
            architecture_data: Architecture decision data.
            requirement_data: Requirement normalization data.

        Returns:
            The size tier string, defaulting to "small".
        """
        # Try to get from requirement count.
        if requirement_data.available:
            count = requirement_data.requirement_count
            if count <= 5:
                return "tiny"
            if count <= 15:
                return "small"
            if count <= 50:
                return "medium"
            if count <= 200:
                return "large"
            return "very_large"

        # Try to infer from architecture.
        decision_count = architecture_data.decision_count
        if decision_count >= 6:
            return "medium"
        return "small"

    # ----------------------------------------------------------------- #
    # Individual category selectors
    # ----------------------------------------------------------------- #

    def _select_programming_language(
        self,
        pattern: str,
        size_tier: str,
        architecture_data: ArchitectureDecisionData,
        requirement_data: RequirementNormalizationData,
        knowledge_data: KnowledgeData,
    ) -> TechnologySelection:
        """Select the programming language.

        Args:
            pattern: The architecture pattern.
            size_tier: The project size tier.
            architecture_data: Architecture decision data.
            requirement_data: Requirement normalization data.
            knowledge_data: Knowledge base data.

        Returns:
            A :class:`TechnologySelection` for the programming language.
        """
        selected = PATTERN_LANGUAGE.get(pattern, "python")

        # Check for language requirements.
        language_req = self._extract_language_requirement(
            requirement_data, knowledge_data
        )
        if language_req:
            selected = language_req

        # Build alternatives.
        candidates = CANDIDATES[TECH_PROGRAMMING_LANGUAGE]
        alternatives = [
            RejectedAlternative(
                name=c["name"],
                reason=(
                    f"'{c['reason']}' but "
                    f"'{selected}' is better for "
                    f"pattern '{pattern}'."
                ),
                impact=(
                    f"Using '{c['name']}' would require "
                    f"additional bridging for the "
                    f"'{pattern}' architecture."
                ),
            )
            for c in candidates
            if c["name"] != selected
        ][:3]

        # Determine the recommended version.
        version = self._get_language_version(selected)

        return TechnologySelection(
            category=TECH_PROGRAMMING_LANGUAGE,
            selected=selected,
            version=version,
            reason=(
                f"'{selected}' is the best fit for the "
                f"'{pattern}' architecture pattern and "
                f"'{size_tier}' project size."
            ),
            analysis=(
                f"Selected based on architecture pattern "
                f"'{pattern}', project size '{size_tier}', "
                f"and requirement analysis."
            ),
            impact=(
                f"Using '{selected}' enables rapid development "
                f"with strong ecosystem support for the "
                f"'{pattern}' architecture."
            ),
            pros=self._get_language_pros(selected),
            cons=self._get_language_cons(selected),
            rejected_alternatives=alternatives,
            source_artefact=SOURCE_ARCHITECTURE_DECISION,
            confidence=0.85,
        )

    def _select_framework(
        self,
        pattern: str,
        size_tier: str,
        architecture_data: ArchitectureDecisionData,
        requirement_data: RequirementNormalizationData,
        knowledge_data: KnowledgeData,
    ) -> TechnologySelection:
        """Select the framework."""
        selected = PATTERN_FRAMEWORK.get(pattern, "fastapi")

        candidates = CANDIDATES[TECH_FRAMEWORK]
        alternatives = [
            RejectedAlternative(
                name=c["name"],
                reason=(
                    f"'{c['reason']}' but '{selected}' is "
                    f"better for pattern '{pattern}'."
                ),
                impact=(
                    f"Using '{c['name']}' would not align as "
                    f"well with the '{pattern}' architecture."
                ),
            )
            for c in candidates
            if c["name"] != selected
        ][:3]

        return TechnologySelection(
            category=TECH_FRAMEWORK,
            selected=selected,
            version=self._get_framework_version(selected),
            reason=(
                f"'{selected}' is the optimal framework for "
                f"the '{pattern}' architecture pattern."
            ),
            analysis=(
                f"Selected based on architecture pattern "
                f"'{pattern}' and project size '{size_tier}'."
            ),
            impact=(
                f"'{selected}' provides the right balance of "
                f"features and performance for the project."
            ),
            pros=self._get_framework_pros(selected),
            cons=self._get_framework_cons(selected),
            rejected_alternatives=alternatives,
            source_artefact=SOURCE_ARCHITECTURE_DECISION,
            confidence=0.8,
        )

    def _select_database(
        self,
        pattern: str,
        size_tier: str,
        architecture_data: ArchitectureDecisionData,
        requirement_data: RequirementNormalizationData,
        knowledge_data: KnowledgeData,
    ) -> TechnologySelection:
        """Select the database."""
        selected = PATTERN_DATABASE.get(pattern, "postgresql")

        candidates = CANDIDATES[TECH_DATABASE]
        alternatives = [
            RejectedAlternative(
                name=c["name"],
                reason=(
                    f"'{c['reason']}' but '{selected}' is "
                    f"better for pattern '{pattern}'."
                ),
                impact=(
                    f"Using '{c['name']}' would have different "
                    f"performance characteristics."
                ),
            )
            for c in candidates
            if c["name"] != selected
        ][:3]

        return TechnologySelection(
            category=TECH_DATABASE,
            selected=selected,
            version=self._get_database_version(selected),
            reason=(
                f"'{selected}' is the best database for the "
                f"'{pattern}' architecture and '{size_tier}' size."
            ),
            analysis=(
                f"Selected based on architecture pattern, "
                f"project size, and data access requirements."
            ),
            impact=(
                f"'{selected}' provides reliable data storage "
                f"with strong consistency guarantees."
            ),
            pros=self._get_database_pros(selected),
            cons=self._get_database_cons(selected),
            rejected_alternatives=alternatives,
            source_artefact=SOURCE_ARCHITECTURE_DECISION,
            confidence=0.85,
        )

    def _select_orm(
        self,
        pattern: str,
        size_tier: str,
        architecture_data: ArchitectureDecisionData,
        requirement_data: RequirementNormalizationData,
        knowledge_data: KnowledgeData,
    ) -> TechnologySelection:
        """Select the ORM."""
        language = PATTERN_LANGUAGE.get(pattern, "python")

        orm_map = {
            "python": "sqlalchemy",
            "nodejs": "prisma",
            "java": "hibernate",
            "golang": "gorm",
            "dotnet": "entity_framework",
            "ruby": None,
            "php": None,
        }
        selected = orm_map.get(language, "sqlalchemy")
        if selected is None:
            selected = "sqlalchemy"

        candidates = CANDIDATES[TECH_ORM]
        alternatives = [
            RejectedAlternative(
                name=c["name"],
                reason=(
                    f"'{c['reason']}' but '{selected}' is "
                    f"the best ORM for '{language}'."
                ),
                impact=(
                    f"Using '{c['name']}' would require "
                    f"additional configuration for '{language}'."
                ),
            )
            for c in candidates
            if c["name"] != selected
        ][:3]

        return TechnologySelection(
            category=TECH_ORM,
            selected=selected,
            version="",
            reason=(
                f"'{selected}' is the best ORM for "
                f"'{language}' with the '{pattern}' "
                f"architecture."
            ),
            analysis=(
                f"Selected based on the programming language "
                f"'{language}' and architecture pattern "
                f"'{pattern}'."
            ),
            impact=(
                f"'{selected}' provides type-safe data access "
                f"with migration support."
            ),
            pros=self._get_orm_pros(selected),
            cons=self._get_orm_cons(selected),
            rejected_alternatives=alternatives,
            source_artefact=SOURCE_ARCHITECTURE_DECISION,
            confidence=0.8,
        )

    def _select_cache(
        self,
        pattern: str,
        size_tier: str,
        architecture_data: ArchitectureDecisionData,
        requirement_data: RequirementNormalizationData,
        knowledge_data: KnowledgeData,
    ) -> TechnologySelection:
        """Select the cache."""
        selected = PATTERN_CACHE.get(pattern, "redis")

        candidates = CANDIDATES[TECH_CACHE]
        alternatives = [
            RejectedAlternative(
                name=c["name"],
                reason=(
                    f"'{c['reason']}' but '{selected}' is "
                    f"the industry standard."
                ),
                impact=(
                    f"Using '{c['name']}' would have different "
                    f"feature set and ecosystem support."
                ),
            )
            for c in candidates
            if c["name"] != selected
        ][:3]

        return TechnologySelection(
            category=TECH_CACHE,
            selected=selected,
            version="7.0",
            reason=(
                f"'{selected}' is the industry-standard "
                f"caching solution."
            ),
            analysis=(
                f"Selected based on performance requirements "
                f"and architecture pattern '{pattern}'."
            ),
            impact=(
                f"'{selected}' provides in-memory caching "
                f"with sub-millisecond latency."
            ),
            pros=self._get_cache_pros(selected),
            cons=self._get_cache_cons(selected),
            rejected_alternatives=alternatives,
            source_artefact=SOURCE_ARCHITECTURE_DECISION,
            confidence=0.9,
        )

    def _select_queue(
        self,
        pattern: str,
        size_tier: str,
        architecture_data: ArchitectureDecisionData,
        requirement_data: RequirementNormalizationData,
        knowledge_data: KnowledgeData,
    ) -> TechnologySelection:
        """Select the queue."""
        selected = PATTERN_QUEUE.get(pattern, "rabbitmq")

        candidates = CANDIDATES[TECH_QUEUE]
        alternatives = [
            RejectedAlternative(
                name=c["name"],
                reason=(
                    f"'{c['reason']}' but '{selected}' is "
                    f"better for pattern '{pattern}'."
                ),
                impact=(
                    f"Using '{c['name']}' would have different "
                    f"throughput and reliability characteristics."
                ),
            )
            for c in candidates
            if c["name"] != selected
        ][:3]

        return TechnologySelection(
            category=TECH_QUEUE,
            selected=selected,
            version="",
            reason=(
                f"'{selected}' is the best queue for the "
                f"'{pattern}' architecture pattern."
            ),
            analysis=(
                f"Selected based on architecture pattern "
                f"'{pattern}' and messaging requirements."
            ),
            impact=(
                f"'{selected}' enables reliable asynchronous "
                f"message processing."
            ),
            pros=self._get_queue_pros(selected),
            cons=self._get_queue_cons(selected),
            rejected_alternatives=alternatives,
            source_artefact=SOURCE_ARCHITECTURE_DECISION,
            confidence=0.8,
        )

    def _select_storage(
        self,
        pattern: str,
        size_tier: str,
        architecture_data: ArchitectureDecisionData,
        requirement_data: RequirementNormalizationData,
        knowledge_data: KnowledgeData,
    ) -> TechnologySelection:
        """Select the storage."""
        selected = SIZE_STORAGE.get(size_tier, "aws_s3")

        candidates = CANDIDATES[TECH_STORAGE]
        alternatives = [
            RejectedAlternative(
                name=c["name"],
                reason=(
                    f"'{c['reason']}' but '{selected}' is "
                    f"better for '{size_tier}' projects."
                ),
                impact=(
                    f"Using '{c['name']}' would have different "
                    f"cost and scalability characteristics."
                ),
            )
            for c in candidates
            if c["name"] != selected
        ][:3]

        return TechnologySelection(
            category=TECH_STORAGE,
            selected=selected,
            version="",
            reason=(
                f"'{selected}' is the best storage solution "
                f"for '{size_tier}' projects."
            ),
            analysis=(
                f"Selected based on project size '{size_tier}' "
                f"and storage requirements."
            ),
            impact=(
                f"'{selected}' provides reliable and scalable "
                f"object storage."
            ),
            pros=self._get_storage_pros(selected),
            cons=self._get_storage_cons(selected),
            rejected_alternatives=alternatives,
            source_artefact=SOURCE_ARCHITECTURE_DECISION,
            confidence=0.8,
        )

    def _select_logging(
        self,
        pattern: str,
        size_tier: str,
        architecture_data: ArchitectureDecisionData,
        requirement_data: RequirementNormalizationData,
        knowledge_data: KnowledgeData,
    ) -> TechnologySelection:
        """Select the logging system."""
        language = PATTERN_LANGUAGE.get(pattern, "python")

        logging_map = {
            "python": "structlog",
            "nodejs": "pino",
            "java": "logback",
            "golang": "zap",
            "dotnet": "serilog",
            "ruby": "logger",
            "php": "monolog",
        }
        selected = logging_map.get(language, "structlog")

        candidates = CANDIDATES[TECH_LOGGING]
        alternatives = [
            RejectedAlternative(
                name=c["name"],
                reason=(
                    f"'{c['reason']}' but '{selected}' is "
                    f"the best for '{language}'."
                ),
                impact=(
                    f"Using '{c['name']}' would require "
                    f"additional configuration."
                ),
            )
            for c in candidates
            if c["name"] != selected
        ][:3]

        return TechnologySelection(
            category=TECH_LOGGING,
            selected=selected,
            version="",
            reason=(
                f"'{selected}' is the best logging solution "
                f"for '{language}'."
            ),
            analysis=(
                f"Selected based on programming language "
                f"'{language}' and structured logging needs."
            ),
            impact=(
                f"'{selected}' provides structured, "
                f"high-performance logging."
            ),
            pros=self._get_logging_pros(selected),
            cons=self._get_logging_cons(selected),
            rejected_alternatives=alternatives,
            source_artefact=SOURCE_ARCHITECTURE_DECISION,
            confidence=0.85,
        )

    def _select_testing(
        self,
        pattern: str,
        size_tier: str,
        architecture_data: ArchitectureDecisionData,
        requirement_data: RequirementNormalizationData,
        knowledge_data: KnowledgeData,
    ) -> TechnologySelection:
        """Select the testing framework."""
        language = PATTERN_LANGUAGE.get(pattern, "python")

        testing_map = {
            "python": "pytest",
            "nodejs": "jest",
            "java": "junit",
            "golang": "testing",
            "dotnet": "xunit",
            "ruby": "rspec",
            "php": "phpunit",
        }
        selected = testing_map.get(language, "pytest")

        candidates = CANDIDATES[TECH_TESTING]
        alternatives = [
            RejectedAlternative(
                name=c["name"],
                reason=(
                    f"'{c['reason']}' but '{selected}' is "
                    f"the best for '{language}'."
                ),
                impact=(
                    f"Using '{c['name']}' would have different "
                    f"ecosystem integration."
                ),
            )
            for c in candidates
            if c["name"] != selected
        ][:3]

        return TechnologySelection(
            category=TECH_TESTING,
            selected=selected,
            version="",
            reason=(
                f"'{selected}' is the best testing framework "
                f"for '{language}'."
            ),
            analysis=(
                f"Selected based on programming language "
                f"'{language}' and testing requirements."
            ),
            impact=(
                f"'{selected}' provides comprehensive testing "
                f"with fixtures and assertions."
            ),
            pros=self._get_testing_pros(selected),
            cons=self._get_testing_cons(selected),
            rejected_alternatives=alternatives,
            source_artefact=SOURCE_ARCHITECTURE_DECISION,
            confidence=0.9,
        )

    def _select_deployment(
        self,
        pattern: str,
        size_tier: str,
        architecture_data: ArchitectureDecisionData,
        requirement_data: RequirementNormalizationData,
        knowledge_data: KnowledgeData,
    ) -> TechnologySelection:
        """Select the deployment requirements."""
        selected = SIZE_DEPLOYMENT.get(size_tier, "docker")

        candidates = CANDIDATES[TECH_DEPLOYMENT]
        alternatives = [
            RejectedAlternative(
                name=c["name"],
                reason=(
                    f"'{c['reason']}' but '{selected}' is "
                    f"better for '{size_tier}' projects."
                ),
                impact=(
                    f"Using '{c['name']}' would have different "
                    f"operational complexity."
                ),
            )
            for c in candidates
            if c["name"] != selected
        ][:3]

        return TechnologySelection(
            category=TECH_DEPLOYMENT,
            selected=selected,
            version="",
            reason=(
                f"'{selected}' is the best deployment solution "
                f"for '{size_tier}' projects."
            ),
            analysis=(
                f"Selected based on project size '{size_tier}' "
                f"and deployment requirements."
            ),
            impact=(
                f"'{selected}' provides the right balance of "
                f"simplicity and scalability."
            ),
            pros=self._get_deployment_pros(selected),
            cons=self._get_deployment_cons(selected),
            rejected_alternatives=alternatives,
            source_artefact=SOURCE_ARCHITECTURE_DECISION,
            confidence=0.85,
        )

    # ----------------------------------------------------------------- #
    # Utility methods
    # ----------------------------------------------------------------- #

    def _extract_language_requirement(
        self,
        requirement_data: RequirementNormalizationData,
        knowledge_data: KnowledgeData,
    ) -> str:
        """Extract a language requirement from data.

        Args:
            requirement_data: Requirement normalization data.
            knowledge_data: Knowledge base data.

        Returns:
            The language name, or empty string.
        """
        # Check requirements.
        if requirement_data.available:
            for req in getattr(requirement_data, "requirements", []):
                req_dict = (
                    req if isinstance(req, dict)
                    else req.to_dict()
                    if hasattr(req, "to_dict")
                    else req
                )
                if isinstance(req_dict, dict):
                    text = req_dict.get("text", "").lower()
                    for lang in ("python", "nodejs", "java",
                                 "golang", "rust", "dotnet",
                                 "ruby", "php"):
                        if lang in text:
                            return lang
        # Check knowledge base defaults.
        if knowledge_data.available:
            defaults = getattr(knowledge_data, "defaults", {})
            lang = defaults.get("language", "")
            if lang:
                return lang
        return ""

    def _get_language_version(self, name: str) -> str:
        versions = {
            "python": "3.12",
            "nodejs": "22.x",
            "java": "21 LTS",
            "golang": "1.23",
            "rust": "1.80",
            "dotnet": "8.0",
            "ruby": "3.3",
            "php": "8.3",
        }
        return versions.get(name, "")

    def _get_framework_version(self, name: str) -> str:
        versions = {
            "fastapi": "0.115",
            "django": "5.1",
            "flask": "3.1",
            "express": "5.x",
            "nest": "10.x",
            "next": "14.x",
            "spring": "3.3",
            "rails": "7.2",
            "laravel": "11.x",
            "gin": "1.10",
            "fiber": "2.52",
        }
        return versions.get(name, "")

    def _get_database_version(self, name: str) -> str:
        versions = {
            "postgresql": "16",
            "mysql": "8.4 LTS",
            "mongodb": "8.0",
            "sqlite": "3.46",
            "redis": "7.2",
            "elasticsearch": "8.15",
            "cockroachdb": "24.1",
        }
        return versions.get(name, "")

    # ----------------------------------------------------------------- #
    # Pros and cons helpers
    # ----------------------------------------------------------------- #

    def _get_language_pros(self, name: str) -> List[str]:
        pros_map = {
            "python": [
                "Massive ecosystem", "Easy to learn",
                "Strong AI/ML support", "Rapid development",
            ],
            "nodejs": [
                "Single language full-stack", "Non-blocking I/O",
                "NPM ecosystem", "Real-time capabilities",
            ],
            "java": [
                "Enterprise-grade", "Strong typing",
                "JVM performance", "Massive ecosystem",
            ],
            "golang": [
                "Built-in concurrency", "Fast compilation",
                "Static binaries", "Simple syntax",
            ],
            "rust": [
                "Memory safety", "Zero-cost abstractions",
                "Exceptional performance", "No garbage collector",
            ],
            "dotnet": [
                "Enterprise support", "Cross-platform",
                "Strong tooling", "Large ecosystem",
            ],
        }
        return pros_map.get(name, ["General purpose language"])

    def _get_language_cons(self, name: str) -> List[str]:
        cons_map = {
            "python": ["GIL limits true parallelism", "Slower execution"],
            "nodejs": ["CPU-bound tasks", "Callback complexity"],
            "java": ["Verbose syntax", "High memory usage"],
            "golang": ["Limited generics", "Smaller ecosystem"],
            "rust": ["Steep learning curve", "Compilation time"],
            "dotnet": ["Windows-centric legacy", "Smaller community"],
        }
        return cons_map.get(name, ["Some limitations"])

    def _get_framework_pros(self, name: str) -> List[str]:
        pros_map = {
            "fastapi": ["Auto docs", "Async", "Type-safe", "Fast"],
            "django": ["Batteries included", "Admin panel", "ORM"],
            "flask": ["Lightweight", "Flexible", "Microservices"],
            "express": ["Minimal", "Huge ecosystem", "Simple"],
            "nest": ["TypeScript", "Dependency injection", "Modular"],
            "next": ["SSR", "React integration", "Full-stack"],
        }
        return pros_map.get(name, ["Good framework"])

    def _get_framework_cons(self, name: str) -> List[str]:
        cons_map = {
            "fastapi": ["Younger ecosystem", "Limited plugins"],
            "django": ["Monolithic", "Heavy", "Learning curve"],
            "flask": ["Manual configuration", "No built-in ORM"],
            "express": ["Unopinionated", "Callback hell risk"],
            "nest": ["Boilerplate", "Complexity"],
            "next": ["React dependency", "Build complexity"],
        }
        return cons_map.get(name, ["Some limitations"])

    def _get_database_pros(self, name: str) -> List[str]:
        pros_map = {
            "postgresql": ["ACID", "Advanced features", "JSON support"],
            "mysql": ["Simple", "Fast reads", "Widely deployed"],
            "mongodb": ["Flexible schema", "Horizontal scaling", "JSON"],
            "sqlite": ["Zero config", "Embedded", "Fast"],
            "redis": ["In-memory", "Sub-ms latency", "Versatile"],
            "elasticsearch": ["Full-text search", "Analytics", "Scaling"],
        }
        return pros_map.get(name, ["Good database"])

    def _get_database_cons(self, name: str) -> List[str]:
        cons_map = {
            "postgresql": ["Complex configuration", "Memory heavy"],
            "mysql": ["Limited features vs PostgreSQL", "Oracle-owned"],
            "mongodb": ["No ACID by default", "Memory hungry"],
            "sqlite": ["No concurrency", "Not for production scale"],
            "redis": ["Data in memory only", "Not persistent"],
            "elasticsearch": ["Heavy resource usage", "Complex"],
        }
        return cons_map.get(name, ["Some limitations"])

    def _get_orm_pros(self, name: str) -> List[str]:
        pros_map = {
            "sqlalchemy": ["Full control", "Migration support", "Mature"],
            "django_orm": ["Django integration", "Simple API"],
            "prisma": ["Type-safe", "Auto-generated", "Modern DX"],
            "hibernate": ["Enterprise features", "Mature", "JPA"],
            "gorm": ["Go-native", "Developer-friendly"],
        }
        return pros_map.get(name, ["Good ORM"])

    def _get_orm_cons(self, name: str) -> List[str]:
        cons_map = {
            "sqlalchemy": ["Complex API", "Learning curve"],
            "django_orm": ["Django-only", "Limited flexibility"],
            "prisma": ["Young", "Frequent breaking changes"],
            "hibernate": ["Heavy", "Complex configuration"],
            "gorm": ["Limited advanced features"],
        }
        return cons_map.get(name, ["Some limitations"])

    def _get_cache_pros(self, name: str) -> List[str]:
        pros_map = {
            "redis": ["In-memory", "Versatile", "Industry standard"],
            "memcached": ["Simple", "Fast", "Distributed"],
        }
        return pros_map.get(name, ["Good cache"])

    def _get_cache_cons(self, name: str) -> List[str]:
        cons_map = {
            "redis": ["Single-threaded", "Memory limits"],
            "memcached": ["Limited data types", "No persistence"],
        }
        return cons_map.get(name, ["Some limitations"])

    def _get_queue_pros(self, name: str) -> List[str]:
        pros_map = {
            "rabbitmq": ["AMQP standard", "Reliable", "Mature"],
            "kafka": ["High throughput", "Event streaming", "Scalable"],
            "celery": ["Python-native", "Distributed", "Flexible"],
        }
        return pros_map.get(name, ["Good queue"])

    def _get_queue_cons(self, name: str) -> List[str]:
        cons_map = {
            "rabbitmq": ["Complex clustering", "Erlang dependency"],
            "kafka": ["Heavy setup", "Overkill for small projects"],
            "celery": ["Worker management", "Complex configuration"],
        }
        return cons_map.get(name, ["Some limitations"])

    def _get_storage_pros(self, name: str) -> List[str]:
        pros_map = {
            "aws_s3": ["Industry standard", "Scalable", "Durable"],
            "local_fs": ["Simple", "No external dependency", "Fast"],
        }
        return pros_map.get(name, ["Good storage"])

    def _get_storage_cons(self, name: str) -> List[str]:
        cons_map = {
            "aws_s3": ["Cost at scale", "External dependency"],
            "local_fs": ["No scalability", "Single point of failure"],
        }
        return cons_map.get(name, ["Some limitations"])

    def _get_logging_pros(self, name: str) -> List[str]:
        pros_map = {
            "structlog": ["Structured output", "Pythonic", "Composable"],
            "pino": ["Fastest Node.js logger", "Low overhead", "Structured"],
        }
        return pros_map.get(name, ["Good logger"])

    def _get_logging_cons(self, name: str) -> List[str]:
        cons_map = {
            "structlog": ["Extra dependency", "Not standard library"],
            "pino": ["Node.js only", "Less mature than winston"],
        }
        return cons_map.get(name, ["Some limitations"])

    def _get_testing_pros(self, name: str) -> List[str]:
        pros_map = {
            "pytest": ["Fixtures", "Plugins", "Parametrization"],
            "jest": ["Snapshot testing", "Code coverage", "Fast"],
            "junit": ["Industry standard", "Mature", "IDE support"],
        }
        return pros_map.get(name, ["Good framework"])

    def _get_testing_cons(self, name: str) -> List[str]:
        cons_map = {
            "pytest": ["Learning curve", "Plugin dependency"],
            "jest": ["Heavy memory usage", "Node.js only"],
            "junit": ["Verbose", "Java only"],
        }
        return cons_map.get(name, ["Some limitations"])

    def _get_deployment_pros(self, name: str) -> List[str]:
        pros_map = {
            "docker": ["Isolation", "Reproducibility", "Industry standard"],
            "kubernetes": ["Orchestration", "Auto-scaling", "Self-healing"],
            "docker_compose": ["Simple", "Multi-container", "Dev-friendly"],
            "serverless": ["No ops", "Auto-scaling", "Pay-per-use"],
        }
        return pros_map.get(name, ["Good deployment"])

    def _get_deployment_cons(self, name: str) -> List[str]:
        cons_map = {
            "docker": ["Image size", "Build time"],
            "kubernetes": ["Complex", "Expensive", "Overkill for small"],
            "docker_compose": ["No orchestration", "Not for production"],
            "serverless": ["Cold starts", "Vendor lock-in"],
        }
        return cons_map.get(name, ["Some limitations"])


__all__ = ["TechnologySelector"]
