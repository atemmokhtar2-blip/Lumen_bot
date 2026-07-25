"""
Terminology normalizer — unifies terminology.

The :class:`TerminologyNormalizer` is the helper that unifies all the
different terms the user used to refer to the same concept into a
single canonical term.

The normalizer works by:
1. Collecting all terms from the data sources (keywords from the
   request, terms from the semantic understanding, synonyms and
   abbreviations from the knowledge base).
2. Building a terminology map from the knowledge base (synonyms,
   abbreviations, and explicit terminology mappings).
3. Producing a :class:`TerminologyMapping` for each term that has a
   non-trivial mapping.

This module is a pure processing component: it has no side effects
and does not modify the generation context.
"""

from __future__ import annotations

import re
from typing import Dict, List

from .report_data import (
    SOURCE_KNOWLEDGE_BASE,
    SOURCE_REQUIREMENT_INTELLIGENCE,
    SOURCE_SEMANTIC_UNDERSTANDING,
    SOURCE_USER_REQUEST,
    TerminologyMapping,
)
from .knowledge_reader import KnowledgeData
from .requirement_intelligence_reader import RequirementIntelligenceData
from .semantic_understanding_reader import SemanticUnderstandingData


class TerminologyNormalizer:
    """Unifies terminology.

    The normalizer collects all terms, builds a terminology map from
    the knowledge base, and produces a
    :class:`TerminologyMapping` for each term that has a
    non-trivial mapping.
    """

    def normalize(
        self,
        request_keywords: List[str],
        requirement_data: RequirementIntelligenceData,
        semantic_data: SemanticUnderstandingData,
        knowledge_data: KnowledgeData,
    ) -> List[TerminologyMapping]:
        """Normalize all terminology and return the terminology
        mappings.

        Parameters:
            request_keywords: The keyword strings from the user
                request.
            requirement_data: The requirement intelligence data.
            semantic_data: The semantic understanding data.
            knowledge_data: The knowledge base data.

        Returns:
            A list of :class:`TerminologyMapping` objects.
        """
        mappings: List[TerminologyMapping] = []
        seen: Dict[str, str] = {}

        # Step 1: build the terminology map from the knowledge base.
        # The terminology map maps original_term → canonical_term.
        term_map: Dict[str, str] = {}

        if knowledge_data.available:
            # Synonyms: word → canonical form.
            for original, canonical in knowledge_data.synonyms.items():
                term_map[original.lower()] = canonical

            # Abbreviations: abbreviation → expanded form.
            for abbr, expanded in knowledge_data.abbreviations.items():
                term_map[abbr.lower()] = expanded

            # Explicit terminology: term → canonical term.
            for original, canonical in knowledge_data.terminology.items():
                term_map[original.lower()] = canonical

        # Step 2: collect all terms and map them.
        # (term, kind, source)
        all_terms: List[tuple] = []

        for kw in request_keywords:
            all_terms.append((kw, "general", SOURCE_USER_REQUEST))

        for req in requirement_data.requirements:
            if req.name:
                all_terms.append(
                    (req.name, "concept", SOURCE_REQUIREMENT_INTELLIGENCE)
                )

        for kw in semantic_data.keywords:
            all_terms.append(
                (kw.word, "general", SOURCE_SEMANTIC_UNDERSTANDING)
            )
            if kw.normalized_form and kw.normalized_form != kw.word:
                # The semantic understanding already mapped this
                # keyword.
                mappings.append(TerminologyMapping(
                    original_term=kw.word,
                    canonical_term=kw.normalized_form,
                    kind="general",
                    source_artefact=SOURCE_SEMANTIC_UNDERSTANDING,
                ))
                seen[kw.word.lower()] = kw.normalized_form

        # Step 3: for each term, check if it has a mapping in the
        # knowledge base.
        for term, kind, source in all_terms:
            term_lower = term.lower().strip()
            if not term_lower:
                continue

            # Skip if already mapped by semantic understanding.
            if term_lower in seen:
                continue

            # Check the knowledge base terminology map.
            if term_lower in term_map:
                canonical = term_map[term_lower]
                if canonical.lower() != term_lower:
                    mappings.append(TerminologyMapping(
                        original_term=term,
                        canonical_term=canonical,
                        kind=kind,
                        source_artefact=SOURCE_KNOWLEDGE_BASE,
                    ))
                    seen[term_lower] = canonical
                    continue

            # Check for abbreviation patterns (e.g. "tg" →
            # "telegram").
            # Try matching individual words.
            words = re.split(r"[\s_\-]+", term_lower)
            for word in words:
                if word in term_map and term_map[word].lower() != word:
                    canonical = self._replace_word(
                        term, word, term_map[word]
                    )
                    if canonical.lower() != term.lower():
                        mappings.append(TerminologyMapping(
                            original_term=term,
                            canonical_term=canonical,
                            kind=kind,
                            source_artefact=SOURCE_KNOWLEDGE_BASE,
                        ))
                        seen[term_lower] = canonical
                        break

        return mappings

    @staticmethod
    def _replace_word(term: str, word: str, replacement: str) -> str:
        """Replace a word in a term, preserving the case pattern."""
        # Case-insensitive word replacement.
        pattern = re.compile(re.escape(word), re.IGNORECASE)
        return pattern.sub(replacement, term)


__all__ = ["TerminologyNormalizer"]
