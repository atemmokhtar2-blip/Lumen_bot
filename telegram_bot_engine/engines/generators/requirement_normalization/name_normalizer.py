"""
Name normalizer — unifies component, feature, and module names.

The :class:`NameNormalizer` is the helper that unifies all the
different names the user used to refer to the same component, feature,
or module into a single canonical name.

The normalizer works by:
1. Collecting all names from the data sources (request features,
   requirement intelligence, project context, semantic understanding).
2. Normalizing each name to a canonical form (snake_case, lowercase,
   no extra whitespace).
3. Grouping names that are similar (using the synonym map from the
   knowledge base and the normalized forms from semantic
   understanding).
4. Producing a :class:`CanonicalName` for each group.

This module is a pure processing component: it has no side effects
and does not modify the generation context.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from .report_data import (
    CanonicalName,
    SOURCE_KNOWLEDGE_BASE,
    SOURCE_PROJECT_CONTEXT,
    SOURCE_REQUIREMENT_INTELLIGENCE,
    SOURCE_SEMANTIC_UNDERSTANDING,
    SOURCE_USER_REQUEST,
)
from .context_reader import ContextData
from .knowledge_reader import KnowledgeData
from .requirement_intelligence_reader import RequirementIntelligenceData
from .semantic_understanding_reader import SemanticUnderstandingData


class NameNormalizer:
    """Unifies component, feature, and module names.

    The normalizer collects all the names from the data sources,
    normalizes them, groups them by similarity, and produces a
    :class:`CanonicalName` for each group.
    """

    def normalize(
        self,
        request_features: List[str],
        request_keywords: List[str],
        requirement_data: RequirementIntelligenceData,
        semantic_data: SemanticUnderstandingData,
        context_data: ContextData,
        knowledge_data: KnowledgeData,
    ) -> List[CanonicalName]:
        """Normalize all names and return the canonical names.

        Parameters:
            request_features: The feature names from the user
                request.
            request_keywords: The keyword strings from the user
                request.
            requirement_data: The requirement intelligence data.
            semantic_data: The semantic understanding data.
            context_data: The project context data.
            knowledge_data: The knowledge base data.

        Returns:
            A list of :class:`CanonicalName` objects.
        """
        # Step 1: collect all names with their sources.
        # Each entry is (name, kind, source).
        names: List[Tuple[str, str, str]] = []

        for name in request_features:
            names.append((name, "feature", SOURCE_USER_REQUEST))
        for kw in request_keywords:
            names.append((kw, "term", SOURCE_USER_REQUEST))

        for req in requirement_data.requirements:
            if req.name:
                names.append((req.name, "feature",
                              SOURCE_REQUIREMENT_INTELLIGENCE))
            if req.display_name and req.display_name != req.name:
                names.append((req.display_name, "feature",
                              SOURCE_REQUIREMENT_INTELLIGENCE))

        for kw in semantic_data.keywords:
            if kw.word:
                names.append((kw.word, "term",
                              SOURCE_SEMANTIC_UNDERSTANDING))
            if kw.normalized_form and kw.normalized_form != kw.word:
                names.append((kw.normalized_form, "term",
                              SOURCE_SEMANTIC_UNDERSTANDING))

        for name in context_data.feature_names:
            names.append((name, "feature", SOURCE_PROJECT_CONTEXT))
        for name in context_data.component_names:
            names.append((name, "component", SOURCE_PROJECT_CONTEXT))
        for name in context_data.dependency_names:
            names.append((name, "component", SOURCE_PROJECT_CONTEXT))

        # Step 2: normalize each name to a canonical key.
        normalized_map: Dict[str, List[Tuple[str, str, str]]] = {}
        for name, kind, source in names:
            canon_key = self._to_canonical_key(name, knowledge_data)
            if canon_key not in normalized_map:
                normalized_map[canon_key] = []
            normalized_map[canon_key].append((name, kind, source))

        # Step 3: build the CanonicalName objects.
        canonical_names: List[CanonicalName] = []
        for canon_key, entries in normalized_map.items():
            # Determine the canonical form — use the first entry's
            # name (the most original form), or the canonical key.
            original_forms: List[str] = []
            kinds: Dict[str, int] = {}
            sources: Dict[str, int] = {}
            for name, kind, source in entries:
                if name not in original_forms:
                    original_forms.append(name)
                kinds[kind] = kinds.get(kind, 0) + 1
                sources[source] = sources.get(source, 0) + 1

            # The canonical form is the most common kind's
            # representative.
            best_kind = max(kinds, key=kinds.get) if kinds else "component"
            best_source = (
                max(sources, key=sources.get) if sources
                else SOURCE_USER_REQUEST
            )

            # Choose the canonical form: prefer the snake_case
            # version if available, otherwise the canonical key.
            canonical_form = canon_key
            for name, kind, source in entries:
                if "_" in name and name.lower() == canon_key:
                    canonical_form = name
                    break

            canonical_names.append(CanonicalName(
                canonical_form=canonical_form,
                original_forms=original_forms,
                kind=best_kind,
                source_artefact=best_source,
            ))

        return canonical_names

    # ----------------------------------------------------------------- #
    # Internal helpers
    # ----------------------------------------------------------------- #

    @staticmethod
    def _to_canonical_key(name: str, knowledge_data: KnowledgeData) -> str:
        """Convert a name to a canonical key for grouping.

        The canonical key is the lowercased, snake_case form of the
        name, after applying synonym resolution from the knowledge
        base.
        """
        if not name:
            return ""

        # Apply synonym resolution from the knowledge base.
        name_lower = name.lower().strip()
        if knowledge_data.available:
            for original, canonical in knowledge_data.synonyms.items():
                if name_lower == original.lower():
                    name_lower = canonical.lower()
                    break

        # Convert to snake_case: replace spaces and hyphens with
        # underscores, remove extra characters.
        key = re.sub(r"[\s\-]+", "_", name_lower)
        key = re.sub(r"[^a-z0-9_]", "", key)
        key = re.sub(r"_+", "_", key).strip("_")

        return key


__all__ = ["NameNormalizer"]
