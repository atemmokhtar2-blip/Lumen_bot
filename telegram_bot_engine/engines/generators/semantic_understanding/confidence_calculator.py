"""
Confidence calculator — calculates the overall confidence score.

The :class:`ConfidenceCalculator` is the component that calculates the
overall confidence score of the Semantic Understanding Report.  The
confidence score is a value between 0.0 and 1.0 that represents how
confident the engine is that it correctly understood the user's
request.

The confidence is computed from several factors:

1. **Intent confidence** — the confidence of the intent (how well
   the intent was determined).
2. **Keyword confidence** — the confidence based on the number and
   quality of the keywords extracted.
3. **Ambiguity penalty** — the penalty for each ambiguity detected.
4. **Clarification penalty** — the penalty for each required
   clarification.
5. **Data-source bonus** — a bonus for each data source that was
   available (more data sources → more confidence).
6. **Language confidence** — the confidence based on the language
   and style detection.

The final confidence is a weighted average of these factors, clamped
to the range [0.0, 1.0].

This module is a pure processing component: it has no side effects and
does not modify the generation context.
"""

from __future__ import annotations

from typing import Any, List

from .report_data import (
    CONFIDENCE_HIGH,
    CONFIDENCE_HIGH_THRESHOLD,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_MEDIUM_THRESHOLD,
    ClarificationRequest,
    ImportantKeyword,
    RequirementRelationship,
    SemanticAmbiguity,
    SemanticProvenance,
    SentenceAnalysis,
    UnifiedIntent,
)


# Weights for each factor.
_WEIGHT_INTENT = 0.35
_WEIGHT_KEYWORDS = 0.20
_WEIGHT_AMBIGUITY = 0.15
_WEIGHT_CLARIFICATION = 0.10
_WEIGHT_DATA_SOURCES = 0.10
_WEIGHT_LANGUAGE = 0.10

# Penalties.
_AMBIGUITY_PENALTY = 0.10
_CLARIFICATION_PENALTY = 0.15
_DATA_SOURCE_BONUS = 0.05


class ConfidenceCalculator:
    """Calculates the overall confidence score of the report.

    The calculator takes the intent, the keywords, the ambiguities, the
    clarifications, the relationships, the sentence analyses, the
    provenance, and the language and computes a single confidence
    score between 0.0 and 1.0.

    The calculator also determines the confidence level (high,
    medium, low) based on the confidence score and the thresholds.
    """

    def __init__(self) -> None:
        pass

    def calculate(
        self,
        intent: UnifiedIntent,
        keywords: List[ImportantKeyword],
        ambiguities: List[SemanticAmbiguity],
        clarifications: List[ClarificationRequest],
        relationships: List[RequirementRelationship],
        sentence_analyses: List[SentenceAnalysis],
        provenance: SemanticProvenance,
        language: str,
        style: str,
    ) -> float:
        """Calculate the overall confidence score.

        Parameters:
            intent: The unified intent.
            keywords: The important keywords.
            ambiguities: The ambiguities detected.
            clarifications: The clarification requests.
            relationships: The relationships detected.
            sentence_analyses: The sentence analyses.
            provenance: The provenance record.
            language: The detected language.
            style: The detected style.

        Returns:
            The confidence score (0.0–1.0).
        """
        # Factor 1: Intent confidence.
        intent_score = float(intent.confidence) if intent else 0.0

        # Factor 2: Keyword confidence.
        keyword_score = self._keyword_confidence(keywords)

        # Factor 3: Ambiguity penalty (starts at 1.0, penalized).
        ambiguity_score = max(
            0.0, 1.0 - (_AMBIGUITY_PENALTY * len(ambiguities)),
        )

        # Factor 4: Clarification penalty (starts at 1.0, penalized).
        required_clarifications = [
            c for c in clarifications if c.required
        ]
        clarification_score = max(
            0.0, 1.0 - (_CLARIFICATION_PENALTY * len(required_clarifications)),
        )

        # Factor 5: Data-source bonus.
        data_source_score = self._data_source_confidence(provenance)

        # Factor 6: Language confidence.
        language_score = self._language_confidence(
            language, style, sentence_analyses,
        )

        # Weighted average.
        total = (
            (_WEIGHT_INTENT * intent_score)
            + (_WEIGHT_KEYWORDS * keyword_score)
            + (_WEIGHT_AMBIGUITY * ambiguity_score)
            + (_WEIGHT_CLARIFICATION * clarification_score)
            + (_WEIGHT_DATA_SOURCES * data_source_score)
            + (_WEIGHT_LANGUAGE * language_score)
        )

        # Clamp to [0.0, 1.0].
        return max(0.0, min(1.0, total))

    @staticmethod
    def classify(confidence: float) -> str:
        """Classify the confidence into a level.

        Parameters:
            confidence: The confidence score (0.0–1.0).

        Returns:
            One of the ``CONFIDENCE_*`` constants.
        """
        if confidence >= CONFIDENCE_HIGH_THRESHOLD:
            return CONFIDENCE_HIGH
        if confidence >= CONFIDENCE_MEDIUM_THRESHOLD:
            return CONFIDENCE_MEDIUM
        return CONFIDENCE_LOW

    # ----------------------------------------------------------------- #
    # Internal helpers
    # ----------------------------------------------------------------- #

    @staticmethod
    def _keyword_confidence(
        keywords: List[ImportantKeyword],
    ) -> float:
        """Calculate the confidence based on the keywords.

        More keywords → more confidence (up to a maximum).
        """
        if not keywords:
            return 0.0

        # Confidence increases with the number of keywords, but
        # saturates at around 5 keywords.
        count = len(keywords)
        if count >= 5:
            return 1.0
        return count / 5.0

    @staticmethod
    def _data_source_confidence(
        provenance: SemanticProvenance,
    ) -> float:
        """Calculate the confidence based on the data sources used.

        More data sources → more confidence.
        """
        if not provenance:
            return 0.0

        # Count the available data sources.
        available_count = 0
        if provenance.request_available:
            available_count += 1
        if provenance.requirement_intelligence_available:
            available_count += 1
        if provenance.project_context_available:
            available_count += 1
        if provenance.knowledge_base_available:
            available_count += 1
        if provenance.language_rules_available:
            available_count += 1

        # The language rules are always available (built-in), so the
        # minimum is 1.
        return min(1.0, available_count * _DATA_SOURCE_BONUS + 0.2)

    @staticmethod
    def _language_confidence(
        language: str,
        style: str,
        sentence_analyses: List[SentenceAnalysis],
    ) -> float:
        """Calculate the confidence based on the language and style.

        The language and style detection is more confident when:
        * The language is clearly Arabic or English (not mixed).
        * The style is clearly formal (not slang or mixed).
        * The sentence analyses are consistent (all the same
          language).
        """
        if not sentence_analyses:
            return 0.0

        # Language consistency.
        languages = set(sa.language for sa in sentence_analyses)
        if len(languages) == 1:
            lang_consistency = 1.0
        elif len(languages) == 2:
            lang_consistency = 0.7
        else:
            lang_consistency = 0.4

        # Style consistency.
        styles = set(sa.style for sa in sentence_analyses)
        if len(styles) == 1:
            style_consistency = 1.0
        elif len(styles) == 2:
            style_consistency = 0.7
        else:
            style_consistency = 0.4

        # Formal style is more confident.
        if style == "formal":
            style_bonus = 1.0
        elif style == "colloquial":
            style_bonus = 0.8
        elif style == "mixed":
            style_bonus = 0.6
        else:
            style_bonus = 0.5

        return (
            (0.4 * lang_consistency)
            + (0.3 * style_consistency)
            + (0.3 * style_bonus)
        )


__all__ = ["ConfidenceCalculator"]
