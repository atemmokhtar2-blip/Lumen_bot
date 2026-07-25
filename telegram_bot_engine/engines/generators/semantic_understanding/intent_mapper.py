"""
Intent mapper — maps all request variations to a unified Intent.

The :class:`IntentMapper` is responsible for mapping all the different
ways the user could write the same request to a single, unified
:class:`UnifiedIntent`.  This is the core principle of the Semantic
Understanding Engine: *same request, many ways, one intent*.

The mapper takes the initial :class:`UnifiedIntent` produced by the
:class:`IntentExtractor` and refines it by:
* Counting the number of request variations that were mapped to this
  intent (this is the "mapped_from_variations" field).
* Consolidating keywords from all sentence analyses into a single set
  of important keywords.
* Ensuring that the intent is the single, canonical understanding of
  the request.

The mapper does not create a new intent — it refines the existing
intent.  The :class:`IntentExtractor` is the component that creates
the initial intent; the :class:`IntentMapper` is the component that
maps all variations to it.

This module is a pure processing component: it has no side effects and
does not modify the generation context.
"""

from __future__ import annotations

from typing import Dict, List

from .report_data import (
    ImportantKeyword,
    SOURCE_LANGUAGE_RULES,
    SOURCE_USER_REQUEST,
    SentenceAnalysis,
    UnifiedIntent,
)


class IntentMapper:
    """Maps all request variations to a unified Intent.

    The mapper takes the initial :class:`UnifiedIntent` (from the
    :class:`IntentExtractor`) and the list of
    :class:`SentenceAnalysis` objects, and:
    1. Counts the number of variations (sentences) that were mapped
       to the intent.
    2. Consolidates keywords from all sentence analyses into a list
       of :class:`ImportantKeyword` objects.
    3. Groups the keywords by their normalized form (so that all
       variations of the same word are grouped together).
    4. Returns the refined intent and the list of important keywords.
    """

    def __init__(self) -> None:
        pass

    def map(
        self,
        intent: UnifiedIntent,
        sentence_analyses: List[SentenceAnalysis],
        synonyms: Dict[str, str],
    ) -> List[ImportantKeyword]:
        """Map all variations to the unified intent.

        Parameters:
            intent: The initial intent (from the
                :class:`IntentExtractor`).
            sentence_analyses: The list of sentence analyses.
            synonyms: The synonym dictionary (for canonical form
                resolution).

        Returns:
            A list of :class:`ImportantKeyword` objects, sorted by
            weight (descending).
        """
        # Count the number of variations.
        intent.mapped_from_variations = len(sentence_analyses)

        # Consolidate keywords from all sentence analyses.
        important_keywords = self._consolidate_keywords(
            sentence_analyses, synonyms,
        )

        return important_keywords

    # ----------------------------------------------------------------- #
    # Internal helpers
    # ----------------------------------------------------------------- #

    @staticmethod
    def _consolidate_keywords(
        sentence_analyses: List[SentenceAnalysis],
        synonyms: Dict[str, str],
    ) -> List[ImportantKeyword]:
        """Consolidate keywords from all sentence analyses.

        This groups all variations of the same word into a single
        :class:`ImportantKeyword` object.  The ``normalized_form`` is
        the canonical form (from the synonym dictionary), and the
        ``original_forms`` is the list of all different forms the
        keyword appeared in.
        """
        # Build a mapping: normalized_form → {word → count}.
        keyword_data: Dict[str, Dict[str, int]] = {}

        for sa in sentence_analyses:
            for kw in sa.keywords:
                if not kw:
                    continue

                # Determine the normalized form.
                lower = kw.lower()
                normalized = synonyms.get(lower, lower)
                if not normalized:
                    normalized = lower

                if normalized not in keyword_data:
                    keyword_data[normalized] = {}
                if kw not in keyword_data[normalized]:
                    keyword_data[normalized][kw] = 0
                keyword_data[normalized][kw] += 1

        # Build the list of ImportantKeyword objects.
        keywords: List[ImportantKeyword] = []
        for normalized_form, forms in keyword_data.items():
            original_forms = list(forms.keys())
            total_count = sum(forms.values())

            # Weight is based on the number of times the keyword
            # appeared (capped at 1.0).
            weight = min(1.0, total_count / max(1, len(sentence_analyses)))

            keywords.append(ImportantKeyword(
                word=original_forms[0] if original_forms else normalized_form,
                weight=weight,
                normalized_form=normalized_form,
                original_forms=original_forms,
                source_artefact=SOURCE_LANGUAGE_RULES,
            ))

        # Sort by weight (descending).
        keywords.sort(key=lambda k: -k.weight)

        return keywords


__all__ = ["IntentMapper"]
