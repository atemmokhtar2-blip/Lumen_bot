"""
Scalability analyzer — analyses the project scalability.

The :class:`ScalabilityAnalyzer` is a pure processing component that
analyses the project scalability based on the size tier, the number
of services/components, and the presence of integration or messaging
requirements.  It produces an :class:`AnalysisResult` for the
``scalability`` dimension.

Scalability analysis determines how well the architecture will scale
as the project grows.  A project with many components and
integrations needs a scalable architecture; a small project with few
components can use a simpler architecture.

This module is a pure processing component: it has no side effects
and does not modify the generation context.
"""

from __future__ import annotations

from typing import List

from .report_data import (
    AnalysisResult,
    DIMENSION_SCALABILITY,
    SIZE_TINY,
    SIZE_SMALL,
    SIZE_MEDIUM,
    SIZE_LARGE,
    SIZE_VERY_LARGE,
    SOURCE_INTELLIGENCE_GRAPH,
)
from .intelligence_graph_reader import IntelligenceGraphData
from .requirement_normalization_reader import RequirementNormalizationData


class ScalabilityAnalyzer:
    """Analyses the project scalability.

    The analyzer uses the size tier and the graph structure
    (component count, service count, dependency count) to assess
    how well the architecture must scale.
    """

    def analyze(
        self,
        graph_data: IntelligenceGraphData,
        requirement_data: RequirementNormalizationData,
        size_tier: str,
    ) -> AnalysisResult:
        """Analyse the project scalability and return an
        :class:`AnalysisResult`.

        Parameters:
            graph_data: The intelligence graph data.
            requirement_data: The normalized requirement model.
            size_tier: The project size tier (from the size
                analysis).

        Returns:
            An :class:`AnalysisResult` for the ``scalability``
            dimension.
        """
        component_count = (
            graph_data.component_count if graph_data.available else 0
        )
        service_count = (
            graph_data.service_count if graph_data.available else 0
        )
        dependency_count = (
            graph_data.dependency_count if graph_data.available else 0
        )
        circular_count = (
            graph_data.circular_count if graph_data.available else 0
        )

        # Base scalability score from the size tier.
        base_score = self._size_base_score(size_tier)

        # Adjustments.
        # More components → higher scalability need.
        if component_count > 20:
            base_score += 0.1
        if service_count > 5:
            base_score += 0.05
        # Circular dependencies → lower scalability (harder to scale).
        if circular_count > 0:
            base_score -= 0.1

        score = max(0.0, min(1.0, base_score))

        level = self._level(score)

        details: List[str] = []
        details.append(f"Size tier: {size_tier}")
        details.append(f"Component count: {component_count}")
        details.append(f"Service count: {service_count}")
        details.append(f"Dependency count: {dependency_count}")
        details.append(f"Circular dependencies: {circular_count}")
        details.append(f"Scalability score: {score:.2f}")
        details.append(f"Scalability level: {level}")

        summary = (
            f"Scalability assessed as {level} (score {score:.2f}) "
            f"based on {component_count} components, "
            f"{service_count} services, and "
            f"{circular_count} circular dependencies."
        )

        return AnalysisResult(
            dimension=DIMENSION_SCALABILITY,
            score=score,
            level=level,
            summary=summary,
            details=details,
            source_artefact=SOURCE_INTELLIGENCE_GRAPH,
        )

    # ----------------------------------------------------------------- #
    # Internal helpers
    # ----------------------------------------------------------------- #

    @staticmethod
    def _size_base_score(size_tier: str) -> float:
        """Return the base scalability score for the size tier."""
        scores = {
            SIZE_TINY: 0.4,
            SIZE_SMALL: 0.5,
            SIZE_MEDIUM: 0.65,
            SIZE_LARGE: 0.8,
            SIZE_VERY_LARGE: 0.9,
        }
        return scores.get(size_tier, 0.5)

    @staticmethod
    def _level(score: float) -> str:
        """Return a human-readable level from the score."""
        if score >= 0.8:
            return "high"
        if score >= 0.6:
            return "medium"
        return "low"


__all__ = ["ScalabilityAnalyzer"]
