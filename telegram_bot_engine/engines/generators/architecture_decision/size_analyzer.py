"""
Size analyzer — analyses the project size.

The :class:`SizeAnalyzer` is a pure processing component that
analyses the project size based on the requirement count and the
intelligence graph node count.  It produces an
:class:`AnalysisResult` for the ``size`` dimension.

The size analysis classifies the project into one of five tiers:
tiny, small, medium, large, or very large.  The size tier drives
many architectural decisions: a tiny project does not need a
microservice architecture, and a very large project cannot use a
monolith.

This module is a pure processing component: it has no side effects
and does not modify the generation context.
"""

from __future__ import annotations

from typing import List

from .report_data import (
    AnalysisResult,
    DIMENSION_SIZE,
    SIZE_TINY,
    SIZE_SMALL,
    SIZE_MEDIUM,
    SIZE_LARGE,
    SIZE_VERY_LARGE,
    SIZE_THRESHOLD_TINY,
    SIZE_THRESHOLD_SMALL,
    SIZE_THRESHOLD_MEDIUM,
    SIZE_THRESHOLD_LARGE,
    SOURCE_NORMALIZED_REQUIREMENTS,
    SOURCE_INTELLIGENCE_GRAPH,
)
from .requirement_normalization_reader import RequirementNormalizationData
from .intelligence_graph_reader import IntelligenceGraphData


class SizeAnalyzer:
    """Analyses the project size.

    The analyzer uses the requirement count (from the normalized
    requirement model) and the graph node count (from the
    intelligence graph) to classify the project into a size tier.
    """

    def analyze(
        self,
        requirement_data: RequirementNormalizationData,
        graph_data: IntelligenceGraphData,
    ) -> AnalysisResult:
        """Analyse the project size and return an
        :class:`AnalysisResult`.

        Parameters:
            requirement_data: The normalized requirement model.
            graph_data: The intelligence graph data.

        Returns:
            An :class:`AnalysisResult` for the ``size`` dimension.
        """
        requirement_count = (
            requirement_data.requirement_count
            if requirement_data.available
            else 0
        )
        node_count = (
            graph_data.node_count
            if graph_data.available
            else 0
        )

        # The effective count is the maximum of the two, so a
        # project with few requirements but many graph nodes is
        # still classified as large.
        effective_count = max(requirement_count, node_count)

        size_tier = self._classify(effective_count)
        score = self._score(size_tier)

        details: List[str] = []
        details.append(
            f"Requirement count: {requirement_count}"
        )
        details.append(
            f"Graph node count: {node_count}"
        )
        details.append(
            f"Effective count: {effective_count}"
        )
        details.append(f"Size tier: {size_tier}")

        summary = (
            f"Project classified as {size_tier} based on "
            f"{effective_count} effective components "
            f"({requirement_count} requirements, "
            f"{node_count} graph nodes)."
        )

        source = (
            SOURCE_NORMALIZED_REQUIREMENTS
            if requirement_data.available
            else SOURCE_INTELLIGENCE_GRAPH
            if graph_data.available
            else SOURCE_NORMALIZED_REQUIREMENTS
        )

        return AnalysisResult(
            dimension=DIMENSION_SIZE,
            score=score,
            level=size_tier,
            summary=summary,
            details=details,
            source_artefact=source,
        )

    # ----------------------------------------------------------------- #
    # Internal helpers
    # ----------------------------------------------------------------- #

    @staticmethod
    def _classify(count: int) -> str:
        """Classify the effective count into a size tier."""
        if count <= SIZE_THRESHOLD_TINY:
            return SIZE_TINY
        if count <= SIZE_THRESHOLD_SMALL:
            return SIZE_SMALL
        if count <= SIZE_THRESHOLD_MEDIUM:
            return SIZE_MEDIUM
        if count <= SIZE_THRESHOLD_LARGE:
            return SIZE_LARGE
        return SIZE_VERY_LARGE

    @staticmethod
    def _score(size_tier: str) -> float:
        """Return a 0.0-1.0 score for the size tier.

        Larger projects get a higher score because the size analysis
        is more confident (more data to base the tier on).
        """
        scores = {
            SIZE_TINY: 0.5,
            SIZE_SMALL: 0.6,
            SIZE_MEDIUM: 0.7,
            SIZE_LARGE: 0.8,
            SIZE_VERY_LARGE: 0.9,
        }
        return scores.get(size_tier, 0.5)


__all__ = ["SizeAnalyzer"]
