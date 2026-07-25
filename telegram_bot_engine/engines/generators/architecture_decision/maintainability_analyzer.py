"""
Maintainability analyzer — analyses the project maintainability.

The :class:`MaintainabilityAnalyzer` is a pure processing component
that analyses the maintainability of the project based on the size
tier, the dependency structure (circular dependencies), and the
number of modules/components.  It produces an :class:`AnalysisResult`
for the ``maintainability`` dimension.

Maintainability analysis determines whether the architecture will be
clear, extensible, and maintainable.  The architecture must allow
adding new features without rebuilding.  A project with circular
dependencies or a flat structure is harder to maintain.

This module is a pure processing component: it has no side effects
and does not modify the generation context.
"""

from __future__ import annotations

from typing import List

from .report_data import (
    AnalysisResult,
    DIMENSION_MAINTAINABILITY,
    SIZE_TINY,
    SIZE_SMALL,
    SIZE_MEDIUM,
    SIZE_LARGE,
    SIZE_VERY_LARGE,
    SOURCE_INTELLIGENCE_GRAPH,
    SOURCE_REQUIREMENT_INTELLIGENCE,
)
from .intelligence_graph_reader import IntelligenceGraphData
from .requirement_intelligence_reader import RequirementIntelligenceData
from .requirement_normalization_reader import RequirementNormalizationData


class MaintainabilityAnalyzer:
    """Analyses the project maintainability.

    The analyzer uses the size tier, the graph structure (circular
    dependencies, dependency count), and the requirement intelligence
    to assess how maintainable the architecture needs to be.
    """

    def analyze(
        self,
        graph_data: IntelligenceGraphData,
        requirement_intelligence_data: RequirementIntelligenceData,
        requirement_data: RequirementNormalizationData,
        size_tier: str,
    ) -> AnalysisResult:
        """Analyse the project maintainability and return an
        :class:`AnalysisResult`.

        Parameters:
            graph_data: The intelligence graph data.
            requirement_intelligence_data: The requirement
                intelligence data.
            requirement_data: The normalized requirement model.
            size_tier: The project size tier (from the size
                analysis).

        Returns:
            An :class:`AnalysisResult` for the ``maintainability``
            dimension.
        """
        # Base maintainability score from the size tier.
        # Larger projects need more maintainable architectures.
        base_score = self._size_base_score(size_tier)

        details: List[str] = []
        details.append(f"Size tier: {size_tier}")

        circular_count = 0
        dependency_count = 0
        component_count = 0
        if graph_data.available:
            circular_count = graph_data.circular_count
            dependency_count = graph_data.dependency_count
            component_count = graph_data.component_count
            # Circular dependencies hurt maintainability.
            if circular_count > 0:
                base_score -= min(0.2, circular_count * 0.05)
                details.append(
                    f"Circular dependencies detected: "
                    f"{circular_count}"
                )
            # High dependency-to-component ratio hurts maintainability.
            if component_count > 0:
                dep_ratio = dependency_count / component_count
                if dep_ratio > 2.0:
                    base_score -= 0.05
                    details.append(
                        f"High dependency-to-component ratio: "
                        f"{dep_ratio:.2f}"
                    )

        # Ambiguities and conflicts hurt maintainability (unclear
        # requirements lead to hard-to-maintain code).
        if requirement_intelligence_data.available:
            amb_count = len(requirement_intelligence_data.ambiguities)
            conf_count = len(requirement_intelligence_data.conflicts)
            if amb_count > 0:
                base_score -= min(0.1, amb_count * 0.03)
                details.append(f"Ambiguities: {amb_count}")
            if conf_count > 0:
                base_score -= min(0.1, conf_count * 0.03)
                details.append(f"Conflicts: {conf_count}")

        # If requirements are not all linked, maintainability is
        # lower (harder to trace changes).
        if requirement_data.available:
            if not requirement_data.all_linked:
                base_score -= 0.05
                details.append("Not all requirements are linked")

        score = max(0.0, min(1.0, base_score))
        level = self._level(score)

        details.append(f"Maintainability score: {score:.2f}")
        details.append(f"Maintainability level: {level}")

        summary = (
            f"Maintainability assessed as {level} "
            f"(score {score:.2f}) based on size tier, "
            f"dependency structure, and requirement clarity."
        )

        source = (
            SOURCE_INTELLIGENCE_GRAPH
            if graph_data.available
            else SOURCE_REQUIREMENT_INTELLIGENCE
            if requirement_intelligence_data.available
            else SOURCE_INTELLIGENCE_GRAPH
        )

        return AnalysisResult(
            dimension=DIMENSION_MAINTAINABILITY,
            score=score,
            level=level,
            summary=summary,
            details=details,
            source_artefact=source,
        )

    # ----------------------------------------------------------------- #
    # Internal helpers
    # ----------------------------------------------------------------- #

    @staticmethod
    def _size_base_score(size_tier: str) -> float:
        """Return the base maintainability score for the size tier.

        Larger projects need a more maintainable architecture
        (modular, clear separation), so the base score is higher.
        """
        scores = {
            SIZE_TINY: 0.5,
            SIZE_SMALL: 0.6,
            SIZE_MEDIUM: 0.7,
            SIZE_LARGE: 0.8,
            SIZE_VERY_LARGE: 0.85,
        }
        return scores.get(size_tier, 0.6)

    @staticmethod
    def _level(score: float) -> str:
        """Return a human-readable level from the score."""
        if score >= 0.75:
            return "high"
        if score >= 0.55:
            return "medium"
        return "low"


__all__ = ["MaintainabilityAnalyzer"]
