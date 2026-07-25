"""
Performance analyzer — analyses the performance requirements.

The :class:`PerformanceAnalyzer` is a pure processing component that
analyses the performance requirements of the project based on the
intent kind, the presence of real-time or high-throughput
requirements, and the semantic understanding.  It produces an
:class:`AnalysisResult` for the ``performance`` dimension.

Performance analysis determines whether the architecture needs
caching, asynchronous processing, or other performance-oriented
patterns.

This module is a pure processing component: it has no side effects
and does not modify the generation context.
"""

from __future__ import annotations

from typing import List

from .report_data import (
    AnalysisResult,
    DIMENSION_PERFORMANCE,
    SOURCE_SEMANTIC_UNDERSTANDING,
    SOURCE_REQUIREMENT_INTELLIGENCE,
)
from .semantic_understanding_reader import SemanticUnderstandingData
from .requirement_intelligence_reader import RequirementIntelligenceData
from .requirement_normalization_reader import RequirementNormalizationData


class PerformanceAnalyzer:
    """Analyses the performance requirements.

    The analyzer uses the intent kind, the semantic understanding
    constraints, and the requirement categories to assess the
    performance needs of the project.
    """

    # Keywords that signal performance-sensitive requirements.
    _PERFORMANCE_KEYWORDS = (
        "real-time", "realtime", "fast", "performance", "latency",
        "throughput", "concurrent", "concurrency", "cache",
        "caching", "async", "asynchronous", "high-traffic",
        "responsive", "high-frequency",
    )

    def analyze(
        self,
        semantic_data: SemanticUnderstandingData,
        requirement_intelligence_data: RequirementIntelligenceData,
        requirement_data: RequirementNormalizationData,
    ) -> AnalysisResult:
        """Analyse the performance requirements and return an
        :class:`AnalysisResult`.

        Parameters:
            semantic_data: The semantic understanding data.
            requirement_intelligence_data: The requirement
                intelligence data.
            requirement_data: The normalized requirement model.

        Returns:
            An :class:`AnalysisResult` for the ``performance``
            dimension.
        """
        score = 0.5
        details: List[str] = []

        # Check intent for performance signals.
        intent_kind = ""
        if semantic_data.available:
            intent_kind = semantic_data.intent_kind
            # The intent description may contain performance keywords.
            desc = (
                semantic_data.intent_description
                + " "
                + " ".join(semantic_data.intent_constraints)
            ).lower()
            hits = sum(
                1
                for kw in self._PERFORMANCE_KEYWORDS
                if kw in desc
            )
            if hits > 0:
                score += min(0.2, hits * 0.05)
                details.append(
                    f"Performance signals in intent: {hits}"
                )

        # Check requirement intelligence for performance wants.
        if requirement_intelligence_data.available:
            wants_text = " ".join(
                requirement_intelligence_data.intent_wants
            ).lower()
            if any(
                kw in wants_text
                for kw in self._PERFORMANCE_KEYWORDS
            ):
                score += 0.1
                details.append(
                    "Performance signals in requirement wants"
                )

        # Check requirement categories for performance-related ones.
        if requirement_data.available:
            cat_counts = requirement_data.category_counts
            # Look for categories that suggest performance needs.
            perf_categories = 0
            for cat, count in cat_counts.items():
                cat_lower = str(cat).lower()
                if any(
                    kw in cat_lower
                    for kw in (
                        "performance", "real-time", "realtime",
                        "concurrency", "throughput",
                    )
                ):
                    perf_categories += count
            if perf_categories > 0:
                score += min(0.1, perf_categories * 0.05)
                details.append(
                    f"Performance-related requirement categories: "
                    f"{perf_categories}"
                )

        # Quality level signal.
        if requirement_intelligence_data.available:
            quality = (
                requirement_intelligence_data.quality_level
            ).lower()
            if quality in ("high", "critical", "premium"):
                score += 0.05
                details.append(
                    f"High quality level: {quality}"
                )

        score = max(0.0, min(1.0, score))
        level = self._level(score)

        details.append(f"Intent kind: {intent_kind}")
        details.append(f"Performance score: {score:.2f}")
        details.append(f"Performance level: {level}")

        summary = (
            f"Performance assessed as {level} (score {score:.2f}) "
            f"based on intent, requirement wants, and categories."
        )

        source = (
            SOURCE_SEMANTIC_UNDERSTANDING
            if semantic_data.available
            else SOURCE_REQUIREMENT_INTELLIGENCE
            if requirement_intelligence_data.available
            else SOURCE_SEMANTIC_UNDERSTANDING
        )

        return AnalysisResult(
            dimension=DIMENSION_PERFORMANCE,
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
    def _level(score: float) -> str:
        """Return a human-readable level from the score."""
        if score >= 0.7:
            return "high"
        if score >= 0.5:
            return "medium"
        return "low"


__all__ = ["PerformanceAnalyzer"]
