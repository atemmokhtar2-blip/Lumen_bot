"""
PerformanceAnalyzer — Specification 016

Evaluates candidate technologies against:
    - Performance (runtime efficiency)
    - Memory consumption (resource footprint)
    - Execution speed (throughput and latency)
    - Scalability (ability to grow with the project)

The analyzer scores each candidate technology across four
performance dimensions and produces a composite score.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from .report_data import (
    DIMENSION_PERFORMANCE,
    AnalysisResult,
    TechnologyFinding,
    SOURCE_ARCHITECTURE_DECISION,
    SEVERITY_WARNING,
    SEVERITY_INFO,
)

_log = logging.getLogger("engine.technology_selection.performance")


# ---------------------------------------------------------------------------#
# Performance scoring data
# ---------------------------------------------------------------------------#
#
# Pre-defined performance scores for common technologies.
# Scores range from 0.0 (worst) to 1.0 (best).

PERFORMANCE_SCORES: Dict[str, Dict[str, float]] = {
    # Programming languages
    "python": {"runtime": 0.5, "memory": 0.6, "speed": 0.5, "scalability": 0.7},
    "nodejs": {"runtime": 0.7, "memory": 0.5, "speed": 0.7, "scalability": 0.8},
    "java": {"runtime": 0.7, "memory": 0.4, "speed": 0.7, "scalability": 0.9},
    "golang": {"runtime": 0.9, "memory": 0.9, "speed": 0.9, "scalability": 0.9},
    "rust": {"runtime": 0.95, "memory": 0.95, "speed": 0.95, "scalability": 0.85},
    "dotnet": {"runtime": 0.75, "memory": 0.5, "speed": 0.75, "scalability": 0.8},
    "ruby": {"runtime": 0.4, "memory": 0.5, "speed": 0.4, "scalability": 0.5},
    "php": {"runtime": 0.5, "memory": 0.6, "speed": 0.5, "scalability": 0.6},

    # Databases
    "postgresql": {"runtime": 0.8, "memory": 0.6, "speed": 0.8, "scalability": 0.85},
    "mysql": {"runtime": 0.75, "memory": 0.65, "speed": 0.75, "scalability": 0.75},
    "mongodb": {"runtime": 0.7, "memory": 0.5, "speed": 0.7, "scalability": 0.8},
    "sqlite": {"runtime": 0.8, "memory": 0.95, "speed": 0.75, "scalability": 0.3},
    "redis": {"runtime": 0.95, "memory": 0.3, "speed": 0.95, "scalability": 0.7},
    "elasticsearch": {"runtime": 0.65, "memory": 0.3, "speed": 0.7, "scalability": 0.8},
    "oracle": {"runtime": 0.75, "memory": 0.4, "speed": 0.75, "scalability": 0.9},
    "mssql": {"runtime": 0.75, "memory": 0.45, "speed": 0.75, "scalability": 0.8},
    "cockroachdb": {"runtime": 0.65, "memory": 0.4, "speed": 0.65, "scalability": 0.95},

    # ORMs
    "sqlalchemy": {"runtime": 0.7, "memory": 0.7, "speed": 0.7, "scalability": 0.8},
    "django_orm": {"runtime": 0.65, "memory": 0.6, "speed": 0.65, "scalability": 0.7},
    "peewee": {"runtime": 0.75, "memory": 0.8, "speed": 0.75, "scalability": 0.6},
    "tortoise_orm": {"runtime": 0.7, "memory": 0.75, "speed": 0.7, "scalability": 0.65},
    "prisma": {"runtime": 0.65, "memory": 0.6, "speed": 0.7, "scalability": 0.75},
    "hibernate": {"runtime": 0.6, "memory": 0.5, "speed": 0.65, "scalability": 0.8},
    "entity_framework": {"runtime": 0.65, "memory": 0.55, "speed": 0.65, "scalability": 0.75},
    "gorm": {"runtime": 0.8, "memory": 0.8, "speed": 0.8, "scalability": 0.8},

    # Caches
    "redis": {"runtime": 0.95, "memory": 0.4, "speed": 0.95, "scalability": 0.8},
    "memcached": {"runtime": 0.9, "memory": 0.6, "speed": 0.9, "scalability": 0.85},
    "hazelcast": {"runtime": 0.75, "memory": 0.5, "speed": 0.75, "scalability": 0.8},

    # Queues
    "rabbitmq": {"runtime": 0.7, "memory": 0.5, "speed": 0.75, "scalability": 0.8},
    "kafka": {"runtime": 0.75, "memory": 0.4, "speed": 0.9, "scalability": 0.95},
    "redis_stream": {"runtime": 0.85, "memory": 0.6, "speed": 0.85, "scalability": 0.6},
    "celery": {"runtime": 0.6, "memory": 0.55, "speed": 0.6, "scalability": 0.7},
    "bull": {"runtime": 0.7, "memory": 0.6, "speed": 0.7, "scalability": 0.65},
    "sidekiq": {"runtime": 0.65, "memory": 0.5, "speed": 0.65, "scalability": 0.75},

    # Logging
    "structlog": {"runtime": 0.8, "memory": 0.85, "speed": 0.8, "scalability": 0.7},
    "loguru": {"runtime": 0.8, "memory": 0.85, "speed": 0.8, "scalability": 0.7},
    "winston": {"runtime": 0.75, "memory": 0.75, "speed": 0.75, "scalability": 0.7},
    "pino": {"runtime": 0.85, "memory": 0.8, "speed": 0.85, "scalability": 0.75},
    "logback": {"runtime": 0.7, "memory": 0.7, "speed": 0.7, "scalability": 0.75},
    "serilog": {"runtime": 0.75, "memory": 0.75, "speed": 0.75, "scalability": 0.7},

    # Testing
    "pytest": {"runtime": 0.75, "memory": 0.7, "speed": 0.75, "scalability": 0.7},
    "unittest": {"runtime": 0.7, "memory": 0.8, "speed": 0.7, "scalability": 0.6},
    "jest": {"runtime": 0.7, "memory": 0.6, "speed": 0.7, "scalability": 0.7},
    "junit": {"runtime": 0.7, "memory": 0.7, "speed": 0.7, "scalability": 0.7},
    "xunit": {"runtime": 0.7, "memory": 0.7, "speed": 0.7, "scalability": 0.7},
    "rspec": {"runtime": 0.65, "memory": 0.65, "speed": 0.65, "scalability": 0.6},
    "mocha": {"runtime": 0.65, "memory": 0.65, "speed": 0.65, "scalability": 0.65},
}


class PerformanceAnalyzer:
    """Analyzes performance characteristics of candidate technologies.

    Evaluates each candidate technology across four dimensions:
    runtime efficiency, memory consumption, execution speed, and
    scalability. Produces a composite performance score.
    """

    # Weights for the four performance dimensions.
    _WEIGHT_RUNTIME = 0.30
    _WEIGHT_MEMORY = 0.20
    _WEIGHT_SPEED = 0.30
    _WEIGHT_SCALABILITY = 0.20

    def __init__(self) -> None:
        self._findings: List[TechnologyFinding] = []
        self._scores: Dict[str, Dict[str, float]] = {}

    def analyze(
        self,
        architecture_data: Any,
        requirement_data: Any,
        graph_data: Any,
        knowledge_data: Any,
    ) -> AnalysisResult:
        """Analyze performance of candidate technologies.

        Evaluates performance across four dimensions:
        1. Runtime efficiency
        2. Memory consumption
        3. Execution speed
        4. Scalability

        Args:
            architecture_data: Architecture decision data.
            requirement_data: Requirement normalization data.
            graph_data: Intelligence graph data.
            knowledge_data: Knowledge base data.

        Returns:
            An :class:`AnalysisResult` for the performance
            dimension.
        """
        self._findings = []
        self._scores = {}
        details = []

        # Extract performance requirements from the requirement
        # data.
        perf_requirement = self._extract_performance_requirement(
            requirement_data
        )
        if perf_requirement:
            details.append(
                f"Performance requirement: {perf_requirement}"
            )

        # Extract size tier from architecture data to weight the
        # performance analysis.
        size_tier = self._extract_size_tier(architecture_data)
        if size_tier:
            details.append(f"Project size tier: {size_tier}")

        # Score all known technologies.
        for tech_name, scores in PERFORMANCE_SCORES.items():
            composite = self._calculate_composite(scores)
            self._scores[tech_name] = {**scores, "composite": composite}

        # Determine the overall performance level based on the
        # project size and requirements.
        overall_score = self._calculate_overall_score(
            perf_requirement, size_tier
        )

        # Generate findings based on the analysis.
        self._generate_findings(
            perf_requirement, size_tier, overall_score
        )

        level = (
            "high" if overall_score >= 0.8
            else "medium" if overall_score >= 0.5
            else "low"
        )

        details.append(f"Overall performance score: {overall_score:.3f}")
        details.append(f"Performance level: {level}")

        # Add top 3 technologies per category.
        details.append(
            "Top performers: " + ", ".join(
                sorted(
                    self._scores.keys(),
                    key=lambda x: self._scores[x]["composite"],
                    reverse=True,
                )[:5]
            )
        )

        summary = (
            f"Performance analysis complete. Overall score: "
            f"{overall_score:.3f} ({level})."
        )

        return AnalysisResult(
            dimension=DIMENSION_PERFORMANCE,
            score=round(overall_score, 3),
            level=level,
            summary=summary,
            details=details,
            source_artefact=SOURCE_ARCHITECTURE_DECISION,
        )

    @property
    def findings(self) -> List[TechnologyFinding]:
        """Return all findings produced during analysis."""
        return self._findings

    @property
    def scores(self) -> Dict[str, Dict[str, float]]:
        """Return the performance scores for all technologies."""
        return self._scores

    def get_score(self, technology: str) -> float:
        """Get the composite score for a specific technology.

        Args:
            technology: The technology name.

        Returns:
            The composite score (0.0-1.0), or 0.5 if unknown.
        """
        if technology in self._scores:
            return self._scores[technology]["composite"]
        return 0.5  # Default for unknown technologies.

    # ----------------------------------------------------------------- #
    # Private helpers
    # ----------------------------------------------------------------- #

    def _calculate_composite(
        self, scores: Dict[str, float]
    ) -> float:
        """Calculate the composite score from dimension scores.

        Args:
            scores: Dictionary with runtime, memory, speed,
                scalability scores.

        Returns:
            The weighted composite score.
        """
        return (
            scores.get("runtime", 0.5) * self._WEIGHT_RUNTIME
            + scores.get("memory", 0.5) * self._WEIGHT_MEMORY
            + scores.get("speed", 0.5) * self._WEIGHT_SPEED
            + scores.get("scalability", 0.5) * self._WEIGHT_SCALABILITY
        )

    def _extract_performance_requirement(
        self, requirement_data: Any
    ) -> str:
        """Extract performance requirements from requirement data.

        Args:
            requirement_data: Requirement normalization data.

        Returns:
            The performance requirement level, or empty string.
        """
        if not requirement_data.available:
            return ""

        requirements = getattr(requirement_data, "requirements", [])
        for req in requirements:
            req_dict = (
                req if isinstance(req, dict)
                else req.to_dict()
                if hasattr(req, "to_dict")
                else req
            )
            if isinstance(req_dict, dict):
                text = req_dict.get("text", "").lower()
                category = req_dict.get("category", "").lower()
                if "performance" in text or "performance" in category:
                    if "high" in text:
                        return "high"
                    if "medium" in text:
                        return "medium"
                    return "standard"
        return ""

    def _extract_size_tier(self, architecture_data: Any) -> str:
        """Extract the project size tier from architecture data.

        Args:
            architecture_data: Architecture decision data.

        Returns:
            The size tier, or empty string.
        """
        # Try to get from decisions.
        decisions = getattr(architecture_data, "decisions", [])
        for decision in decisions:
            decision_dict = (
                decision if isinstance(decision, dict)
                else decision.to_dict()
                if hasattr(decision, "to_dict")
                else decision
            )
            if isinstance(decision_dict, dict):
                domain = decision_dict.get("domain", "")
                selected = decision_dict.get("selected", "")
                if domain == "layers":
                    # Infer size from number of layers.
                    layer_count = len(
                        [l.strip() for l in selected.split(",") if l.strip()]
                    )
                    if layer_count >= 5:
                        return "very_large"
                    if layer_count >= 4:
                        return "large"
                    if layer_count >= 3:
                        return "medium"
                    return "small"
        return ""

    def _calculate_overall_score(
        self,
        perf_requirement: str,
        size_tier: str,
    ) -> float:
        """Calculate the overall performance score.

        Args:
            perf_requirement: The performance requirement level.
            size_tier: The project size tier.

        Returns:
            The overall score (0.0-1.0).
        """
        # Base score starts at 0.7.
        score = 0.7

        # Adjust based on performance requirement.
        if perf_requirement == "high":
            score -= 0.1  # Harder to meet high requirements.
        elif perf_requirement == "medium":
            score += 0.05

        # Adjust based on size tier.
        size_factors = {
            "tiny": 0.15,
            "small": 0.1,
            "medium": 0.0,
            "large": -0.05,
            "very_large": -0.1,
        }
        score += size_factors.get(size_tier, 0.0)

        return max(0.0, min(1.0, score))

    def _generate_findings(
        self,
        perf_requirement: str,
        size_tier: str,
        overall_score: float,
    ) -> None:
        """Generate performance findings.

        Args:
            perf_requirement: The performance requirement level.
            size_tier: The project size tier.
            overall_score: The overall performance score.
        """
        if perf_requirement == "high" and overall_score < 0.7:
            self._findings.append(TechnologyFinding(
                severity=SEVERITY_WARNING,
                code="performance_below_requirement",
                message=(
                    f"Overall performance score ({overall_score:.3f}) "
                    f"is below the high performance requirement."
                ),
                affected="performance",
                resolution_hint=(
                    "Consider selecting higher-performance "
                    "technologies or optimizing the architecture."
                ),
                category="performance",
            ))

        if size_tier in ("large", "very_large"):
            self._findings.append(TechnologyFinding(
                severity=SEVERITY_INFO,
                code="large_project_performance",
                message=(
                    f"Large project ({size_tier}) requires "
                    f"careful technology selection for "
                    f"performance."
                ),
                affected="performance",
                resolution_hint=(
                    "Prioritize technologies with high "
                    "scalability scores."
                ),
                category="performance",
            ))

        if overall_score < 0.5:
            self._findings.append(TechnologyFinding(
                severity=SEVERITY_WARNING,
                code="low_performance_score",
                message=(
                    f"Overall performance score ({overall_score:.3f}) "
                    f"is below acceptable threshold."
                ),
                affected="performance",
                resolution_hint=(
                    "Review technology selections and consider "
                    "alternatives with better performance."
                ),
                category="performance",
            ))


__all__ = ["PerformanceAnalyzer"]
