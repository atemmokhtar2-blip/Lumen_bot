"""
Context awareness — understands the relationships between the parts
of the request.

The :class:`ContextAwareness` component is responsible for understanding
the relationships between the different parts of the user's request.
The engine does not process each sentence separately — it understands
how the parts relate to each other.

The component produces :class:`RequirementRelationship` objects that
record the relationships it detected.  The kinds of relationships it
detects include:

* ``depends_on`` — one part of the request depends on another
  part.
* ``part_of`` — one part of the request is a sub-part of another
  part.
* ``contradicts`` — one part of the request contradicts another
  part.
* ``extends`` — one part of the request extends another part.
* ``relates_to`` — a general relationship (the fallback).

The component uses the sentence analyses (which contain the keywords
and the normalized text) and the requirement intelligence report (which
contains the requirements) to detect relationships.

This module is a pure processing component: it has no side effects and
does not modify the generation context.
"""

from __future__ import annotations

from typing import Any, Dict, List, Set

from .report_data import (
    RequirementRelationship,
    SentenceAnalysis,
    SOURCE_LANGUAGE_RULES,
    SOURCE_REQUIREMENT_INTELLIGENCE,
    SOURCE_USER_REQUEST,
)


# ---------------------------------------------------------------------------#
# Relationship-kind constants (internal)
# ---------------------------------------------------------------------------#

REL_DEPENDS_ON = "depends_on"
REL_PART_OF = "part_of"
REL_CONTRADICTS = "contradicts"
REL_EXTENDS = "extends"
REL_RELATES_TO = "relates_to"


# Words that signal a dependency relationship.
_DEPENDENCY_WORDS = {
    # English
    "after", "before", "then", "once", "when", "requires",
    "depends", "following", "prior", "first", "second",
    # Arabic (formal)
    "بعد", "قبل", "ثم", "عند", "يتطلب", "يعتمد", "أولا", "ثانيا",
    # Arabic (colloquial)
    "بعدين", "اول", "تاني",
}

# Words that signal a part-of relationship.
_PART_OF_WORDS = {
    # English
    "include", "includes", "part", "component", "feature",
    "section", "module", "within", "inside",
    # Arabic (formal)
    "يتضمن", "جزء", "مكون", "ميزة", "قسم", "وحدة", "داخل",
    # Arabic (colloquial)
    "ضمن",
}

# Words that signal a contradiction.
_CONTRADICTION_WORDS = {
    # English
    "not", "without", "except", "but not", "do not", "don't",
    "no", "never", "instead",
    # Arabic (formal)
    "لا", "بدون", "إلا", "لكن", "غير", "ليس", "عوضا",
    # Arabic (colloquial)
    "منغير", "مش", "مفيش",
}

# Words that signal an extension.
_EXTENSION_WORDS = {
    # English
    "also", "additionally", "moreover", "plus", "extra", "and",
    "further", "add",
    # Arabic (formal)
    "أيضا", "إضافة", "بالإضافة", "كما", "زائد", "إضافي",
    # Arabic (colloquial)
    "كمان", "كمانكمان",
}


class ContextAwareness:
    """Understands the relationships between the parts of the request.

    The component takes the sentence analyses and the requirement
    intelligence report and detects the relationships between the
    parts of the request.  It produces a list of
    :class:`RequirementRelationship` objects.

    The component does not guess.  It only detects relationships that
    are clearly indicated by the text.
    """

    def __init__(self) -> None:
        pass

    def analyze(
        self,
        sentence_analyses: List[SentenceAnalysis],
        intent: Any = None,
        requirement_report: Any = None,
    ) -> List[RequirementRelationship]:
        """Detect the relationships between the parts of the request.

        Parameters:
            sentence_analyses: The list of sentence analyses.
            intent: The unified intent (optional, may be ``None``).
            requirement_report: The requirement intelligence report
                data (optional, may be ``None``).

        Returns:
            A list of :class:`RequirementRelationship` objects.
        """
        if not sentence_analyses or len(sentence_analyses) < 2:
            return []

        relationships: List[RequirementRelationship] = []
        rel_counter = 0

        # Build a set of all keywords across all sentence analyses.
        all_keywords: Set[str] = set()
        for sa in sentence_analyses:
            for kw in sa.keywords:
                all_keywords.add(kw.lower())

        # Detect relationships between consecutive sentences.
        for i in range(len(sentence_analyses) - 1):
            current = sentence_analyses[i]
            following = sentence_analyses[i + 1]

            rel = self._detect_pair_relationship(
                current, following, rel_counter,
            )
            if rel is not None:
                relationships.append(rel)
                rel_counter += 1

        # Detect relationships from the requirement intelligence
        # report (if available) — the requirements in the report
        # may have dependencies between them.
        if requirement_report is not None:
            req_rels = self._detect_requirement_relationships(
                requirement_report, rel_counter,
            )
            relationships.extend(req_rels)
            rel_counter += len(req_rels)

        # Detect a relationship between the intent and the
        # requirement report (if both are available).
        if intent is not None and requirement_report is not None:
            intent_rel = self._detect_intent_to_report_relationship(
                intent, requirement_report, rel_counter,
            )
            if intent_rel is not None:
                relationships.append(intent_rel)

        return relationships

    # ----------------------------------------------------------------- #
    # Internal helpers
    # ----------------------------------------------------------------- #

    @staticmethod
    def _detect_pair_relationship(
        current: SentenceAnalysis,
        following: SentenceAnalysis,
        counter: int,
    ) -> RequirementRelationship:
        """Detect the relationship between two consecutive sentences.

        The relationship is determined by the signal words in the
        following sentence.
        """
        rel_id = f"REL-{counter + 1:03d}"

        from_text = (
            current.normalized_text.strip() or current.raw_text.strip()
        )
        to_text = (
            following.normalized_text.strip() or following.raw_text.strip()
        )

        if not from_text or not to_text:
            return None  # type: ignore[return-value]

        from_short = from_text[:60]
        to_short = to_text[:60]

        following_lower = to_text.lower()

        # Check for contradiction.
        for word in _CONTRADICTION_WORDS:
            if word in following_lower:
                return RequirementRelationship(
                    id=rel_id,
                    kind=REL_CONTRADICTS,
                    from_entity=from_short,
                    to_entity=to_short,
                    description=(
                        f"The second part contradicts the first: "
                        f"'{to_short}' contains the negation "
                        f"'{word}'."
                    ),
                    confidence=0.7,
                    source_artefact=SOURCE_USER_REQUEST,
                )

        # Check for dependency.
        for word in _DEPENDENCY_WORDS:
            if word in following_lower:
                return RequirementRelationship(
                    id=rel_id,
                    kind=REL_DEPENDS_ON,
                    from_entity=to_short,
                    to_entity=from_short,
                    description=(
                        f"The second part depends on the first: "
                        f"'{to_short}' contains the dependency "
                        f"signal '{word}'."
                    ),
                    confidence=0.7,
                    source_artefact=SOURCE_USER_REQUEST,
                )

        # Check for part-of.
        for word in _PART_OF_WORDS:
            if word in following_lower:
                return RequirementRelationship(
                    id=rel_id,
                    kind=REL_PART_OF,
                    from_entity=to_short,
                    to_entity=from_short,
                    description=(
                        f"The second part is part of the first: "
                        f"'{to_short}' contains the part-of "
                        f"signal '{word}'."
                    ),
                    confidence=0.7,
                    source_artefact=SOURCE_USER_REQUEST,
                )

        # Check for extension.
        for word in _EXTENSION_WORDS:
            if word in following_lower:
                return RequirementRelationship(
                    id=rel_id,
                    kind=REL_EXTENDS,
                    from_entity=from_short,
                    to_entity=to_short,
                    description=(
                        f"The second part extends the first: "
                        f"'{to_short}' contains the extension "
                        f"signal '{word}'."
                    ),
                    confidence=0.7,
                    source_artefact=SOURCE_USER_REQUEST,
                )

        # Default: a general relationship.
        return RequirementRelationship(
            id=rel_id,
            kind=REL_RELATES_TO,
            from_entity=from_short,
            to_entity=to_short,
            description=(
                f"The parts of the request are related: "
                f"'{from_short}' and '{to_short}'."
            ),
            confidence=0.5,
            source_artefact=SOURCE_USER_REQUEST,
        )

    @staticmethod
    def _detect_requirement_relationships(
        requirement_report: Any,
        counter: int,
    ) -> List[RequirementRelationship]:
        """Detect relationships from the requirement intelligence
        report.

        The requirement intelligence report may contain conflicts,
        which are contradictions between requirements.
        """
        relationships: List[RequirementRelationship] = []

        # Extract conflicts from the requirement intelligence report.
        conflicts = getattr(requirement_report, "conflicts", None)
        if conflicts:
            for i, conflict in enumerate(conflicts):
                rel_id = f"REL-{counter + i + 1:03d}"
                conflict_text = str(conflict)
                relationships.append(RequirementRelationship(
                    id=rel_id,
                    kind=REL_CONTRADICTS,
                    from_entity=conflict_text[:60],
                    to_entity=conflict_text[:60],
                    description=(
                        f"Requirement intelligence detected a "
                        f"conflict: {conflict_text}"
                    ),
                    confidence=0.8,
                    source_artefact=SOURCE_REQUIREMENT_INTELLIGENCE,
                ))

        return relationships

    @staticmethod
    def _detect_intent_to_report_relationship(
        intent: Any,
        requirement_report: Any,
        counter: int,
    ) -> RequirementRelationship:
        """Detect the relationship between the intent and the
        requirement intelligence report.

        The intent is derived from the requirement intelligence
        report — the intent is the unified understanding of what the
        requirement intelligence report described.
        """
        rel_id = f"REL-{counter + 1:03d}"

        intent_desc = getattr(intent, "full_description", "") or ""
        intent_desc_short = intent_desc[:60] if intent_desc else "intent"

        return RequirementRelationship(
            id=rel_id,
            kind=REL_DEPENDS_ON,
            from_entity=intent_desc_short,
            to_entity="requirement_intelligence_report",
            description=(
                "The unified intent is derived from the requirement "
                "intelligence report. The intent is the unified "
                "understanding of the user's request."
            ),
            confidence=0.9,
            source_artefact=SOURCE_LANGUAGE_RULES,
        )


__all__ = [
    "ContextAwareness",
    "REL_DEPENDS_ON",
    "REL_PART_OF",
    "REL_CONTRADICTS",
    "REL_EXTENDS",
    "REL_RELATES_TO",
]
