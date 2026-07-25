"""
Deduplication remover — removes duplicate requirements.

The :class:`DeduplicationRemover` is the helper that detects and
removes duplicate requirements from the list of normalized
requirements.

The remover works by:
1. Computing a similarity score between each pair of requirements
   (based on the normalized description, name, and category).
2. When two requirements are sufficiently similar (above the
   threshold), the duplicate is removed and a :class:`DuplicateRecord`
   is created recording which requirement it was merged into.

This module is a pure processing component: it has no side effects
and does not modify the generation context.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from .report_data import (
    DuplicateRecord,
    NormalizedRequirement,
    SOURCE_REQUIREMENT_INTELLIGENCE,
    STATUS_MERGED,
)


# The similarity threshold above which two requirements are
# considered duplicates.
SIMILARITY_THRESHOLD = 0.85


class DeduplicationRemover:
    """Removes duplicate requirements.

    The remover detects duplicates by computing a similarity score
    between each pair of requirements.  When the similarity is above
    the threshold, the duplicate is merged into the first requirement.
    """

    def __init__(self, threshold: float = SIMILARITY_THRESHOLD) -> None:
        self._threshold = threshold

    def remove(
        self,
        requirements: List[NormalizedRequirement],
    ) -> Tuple[List[NormalizedRequirement], List[DuplicateRecord]]:
        """Remove duplicate requirements.

        Parameters:
            requirements: The list of normalized requirements.

        Returns:
            A tuple ``(unique_requirements, duplicates)`` where
            ``unique_requirements`` is the list of requirements
            with duplicates removed, and ``duplicates`` is the list
            of :class:`DuplicateRecord` objects.
        """
        duplicates: List[DuplicateRecord] = []
        if not requirements:
            return [], []

        unique: List[NormalizedRequirement] = []
        # Track which requirements have been marked as duplicates.
        merged_ids: set = set()

        for i, req_a in enumerate(requirements):
            if req_a.id in merged_ids:
                continue

            for j in range(i + 1, len(requirements)):
                req_b = requirements[j]
                if req_b.id in merged_ids:
                    continue

                similarity = self._compute_similarity(req_a, req_b)

                if similarity >= self._threshold:
                    # req_b is a duplicate of req_a.
                    merged_ids.add(req_b.id)
                    req_b.status = STATUS_MERGED

                    # Merge the original forms of req_b into req_a.
                    for form in req_b.original_forms:
                        if form not in req_a.original_forms:
                            req_a.original_forms.append(form)

                    # Merge dependencies.
                    for dep in req_b.dependencies:
                        if dep not in req_a.dependencies:
                            req_a.dependencies.append(dep)

                    duplicates.append(DuplicateRecord(
                        duplicate_id=req_b.id,
                        duplicate_description=req_b.description,
                        merged_into_id=req_a.id,
                        similarity=similarity,
                        source_artefact=SOURCE_REQUIREMENT_INTELLIGENCE,
                    ))

            unique.append(req_a)

        return unique, duplicates

    # ----------------------------------------------------------------- #
    # Internal helpers
    # ----------------------------------------------------------------- #

    def _compute_similarity(
        self,
        req_a: NormalizedRequirement,
        req_b: NormalizedRequirement,
    ) -> float:
        """Compute the similarity between two requirements.

        The similarity is a weighted combination of:
        * Name similarity (40%)
        * Description similarity (40%)
        * Category match (20%)
        """
        name_sim = self._text_similarity(
            req_a.name.lower(), req_b.name.lower()
        )
        desc_sim = self._text_similarity(
            self._normalize_text(req_a.description),
            self._normalize_text(req_b.description),
        )
        cat_sim = 1.0 if req_a.category == req_b.category else 0.0

        return (name_sim * 0.4) + (desc_sim * 0.4) + (cat_sim * 0.2)

    @staticmethod
    def _text_similarity(a: str, b: str) -> float:
        """Compute the text similarity between two strings.

        Uses a simple Jaccard similarity over word sets.
        """
        if not a and not b:
            return 1.0
        if not a or not b:
            return 0.0

        words_a = set(a.split())
        words_b = set(b.split())

        if not words_a and not words_b:
            return 1.0
        if not words_a or not words_b:
            return 0.0

        intersection = words_a & words_b
        union = words_a | words_b

        return len(intersection) / len(union) if union else 0.0

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize text for comparison."""
        text = text.lower().strip()
        text = re.sub(r"[^a-z0-9\s]", "", text)
        text = re.sub(r"\s+", " ", text)
        return text


__all__ = ["DeduplicationRemover", "SIMILARITY_THRESHOLD"]
