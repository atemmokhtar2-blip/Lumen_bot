"""
Security analyzer — analyses the security requirements.

The :class:`SecurityAnalyzer` is a pure processing component that
analyses the security requirements of the project based on the
intent kind, the presence of authentication/authorization
requirements, and the semantic understanding.  It produces an
:class:`AnalysisResult` for the ``security`` dimension.

Security analysis determines whether the architecture needs
authentication, authorization, encryption, audit logging, or other
security-oriented patterns.

This module is a pure processing component: it has no side effects
and does not modify the generation context.
"""

from __future__ import annotations

from typing import List

from .report_data import (
    AnalysisResult,
    DIMENSION_SECURITY,
    SOURCE_SEMANTIC_UNDERSTANDING,
    SOURCE_REQUIREMENT_INTELLIGENCE,
)
from .semantic_understanding_reader import SemanticUnderstandingData
from .requirement_intelligence_reader import RequirementIntelligenceData
from .requirement_normalization_reader import RequirementNormalizationData


class SecurityAnalyzer:
    """Analyses the security requirements.

    The analyzer uses the intent, the requirement intelligence, and
    the normalized requirement categories to assess the security
    needs of the project.
    """

    # Keywords that signal security-sensitive requirements.
    _SECURITY_KEYWORDS = (
        "security", "authentication", "auth", "authorization",
        "permission", "encryption", "encrypt", "decrypt",
        "password", "login", "token", "session", "audit",
        "compliance", "gdpr", "sensitive", "private",
        "confidential", "access-control", "role", "rbac",
    )

    def analyze(
        self,
        semantic_data: SemanticUnderstandingData,
        requirement_intelligence_data: RequirementIntelligenceData,
        requirement_data: RequirementNormalizationData,
    ) -> AnalysisResult:
        """Analyse the security requirements and return an
        :class:`AnalysisResult`.

        Parameters:
            semantic_data: The semantic understanding data.
            requirement_intelligence_data: The requirement
                intelligence data.
            requirement_data: The normalized requirement model.

        Returns:
            An :class:`AnalysisResult` for the ``security``
            dimension.
        """
        score = 0.4
        details: List[str] = []

        # Check intent for security signals.
        if semantic_data.available:
            desc = (
                semantic_data.intent_description
                + " "
                + " ".join(semantic_data.intent_features)
                + " "
                + " ".join(semantic_data.intent_constraints)
            ).lower()
            hits = sum(
                1
                for kw in self._SECURITY_KEYWORDS
                if kw in desc
            )
            if hits > 0:
                score += min(0.25, hits * 0.06)
                details.append(
                    f"Security signals in intent: {hits}"
                )

        # Check requirement intelligence for security wants.
        if requirement_intelligence_data.available:
            wants_text = " ".join(
                requirement_intelligence_data.intent_wants
            ).lower()
            if any(
                kw in wants_text
                for kw in self._SECURITY_KEYWORDS
            ):
                score += 0.1
                details.append(
                    "Security signals in requirement wants"
                )

        # Check requirement categories for security-related ones.
        if requirement_data.available:
            cat_counts = requirement_data.category_counts
            security_categories = 0
            for cat, count in cat_counts.items():
                cat_lower = str(cat).lower()
                if any(
                    kw in cat_lower
                    for kw in (
                        "security", "auth", "authentication",
                        "authorization", "encryption",
                        "access-control",
                    )
                ):
                    security_categories += count
            if security_categories > 0:
                score += min(0.15, security_categories * 0.05)
                details.append(
                    f"Security-related requirement categories: "
                    f"{security_categories}"
                )

        score = max(0.0, min(1.0, score))
        level = self._level(score)

        details.append(f"Security score: {score:.2f}")
        details.append(f"Security level: {level}")

        summary = (
            f"Security assessed as {level} (score {score:.2f}) "
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
            dimension=DIMENSION_SECURITY,
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


__all__ = ["SecurityAnalyzer"]
