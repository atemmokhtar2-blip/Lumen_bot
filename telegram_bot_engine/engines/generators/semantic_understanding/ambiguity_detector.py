"""
Ambiguity detector — detects ambiguity in the user's request.

The :class:`AmbiguityDetector` is responsible for detecting points of
ambiguity in the user's request.  When the request admits more than
one interpretation, the engine detects the ambiguity and requests
clarification.  It does not guess.

The detector checks for:
* **Vague** requests — the request is too vague to determine the
  intent.
* **Multiple interpretations** — the request could mean more than one
  thing.
* **Missing context** — the request lacks the context needed to
  understand it.
* **Under-specified** — the request does not specify enough detail.

For each ambiguity detected, the detector creates a
:class:`SemanticAmbiguity` object and a corresponding
:class:`ClarificationRequest` object.

This module is a pure processing component: it has no side effects and
does not modify the generation context.
"""

from __future__ import annotations

from typing import Any, List, Tuple

from .report_data import (
    AMBIGUITY_MISSING_CONTEXT,
    AMBIGUITY_MULTIPLE_INTERPRETATIONS,
    AMBIGUITY_UNDER_SPECIFIED,
    AMBIGUITY_VAGUE,
    CLARIFICATION_DISAMBIGUATE,
    CLARIFICATION_PROVIDE_CONTEXT,
    CLARIFICATION_SPECIFY,
    SOURCE_LANGUAGE_RULES,
    SOURCE_USER_REQUEST,
    ClarificationRequest,
    SemanticAmbiguity,
    UnifiedIntent,
)


# Vague words that indicate the request is too vague.
_VAGUE_WORDS = {
    # English
    "something", "anything", "stuff", "things", "maybe", "perhaps",
    "possibly", "kind of", "sort of", "like", "whatever",
    # Arabic
    "شي", "شىء", "حاجة", "حاجه", "أي", "اي", "كذا", "أشياء",
    "اشياء", "ممكن", "ربما", "قد", "لا أدري", "لا_ادري",
}

# Multiple-interpretation indicators — words that can mean different
# things in different contexts.
_MULTI_INTERPRETATION_WORDS = {
    # English
    "it", "this", "that", "they", "them",
    # Arabic
    "هذا", "هذه", "ذلك", "تلك", "هم", "هن",
}


class AmbiguityDetector:
    """Detects ambiguity in the user's request.

    The detector checks for:
    1. Vague requests (the intent is unknown or the description is
       empty).
    2. Multiple-interpretation words (it, this, that, etc.).
    3. Missing context (the subject or target is empty).
    4. Under-specified requests (no features, no keywords).

    For each ambiguity, the detector creates a
    :class:`SemanticAmbiguity` and a :class:`ClarificationRequest`.
    The clarification request is marked as ``required`` when the
    ambiguity prevents the engine from understanding the request.
    """

    def __init__(self) -> None:
        self._ambiguity_counter = 0
        self._clarification_counter = 0

    def detect(
        self,
        intent: UnifiedIntent,
        sentence_analyses: Any,
        requirement_report: Any = None,
        request_data: Any = None,
    ) -> Tuple[List[SemanticAmbiguity], List[ClarificationRequest]]:
        """Detect ambiguities and create clarification requests.

        Parameters:
            intent: The unified intent.
            sentence_analyses: The list of sentence analyses.
            requirement_report: The requirement intelligence report
                data (optional).
            request_data: The request data (optional).

        Returns:
            A tuple ``(ambiguities, clarifications)``.
        """
        self._ambiguity_counter = 0
        self._clarification_counter = 0

        ambiguities: List[SemanticAmbiguity] = []
        clarifications: List[ClarificationRequest] = []

        # 1. Vague intent.
        vague_amb = self._check_vague(intent)
        if vague_amb:
            ambiguities.append(vague_amb)
            clarifications.append(self._make_clarification(
                kind=CLARIFICATION_SPECIFY,
                question=(
                    "Could you provide more detail about what you "
                    "want to create? The request is too vague."
                ),
                related_ambiguity_id=vague_amb.id,
                required=True,
            ))

        # 2. Multiple-interpretation words.
        multi_amb = self._check_multiple_interpretations(sentence_analyses)
        if multi_amb:
            ambiguities.append(multi_amb)
            clarifications.append(self._make_clarification(
                kind=CLARIFICATION_DISAMBIGUATE,
                question=(
                    "Could you clarify what you mean? Some words in "
                    "your request could have multiple interpretations."
                ),
                related_ambiguity_id=multi_amb.id,
                required=False,
            ))

        # 3. Missing context (subject or target empty).
        if not intent.subject:
            missing_amb = self._make_ambiguity(
                kind=AMBIGUITY_MISSING_CONTEXT,
                description=(
                    "The subject of the request is not clear. It is "
                    "not clear what the user wants to create or "
                    "modify."
                ),
                affected_text=intent.full_description,
                possible_interpretations=[
                    "A Telegram bot",
                    "A Telegram bot for a store",
                    "A Telegram bot for management",
                ],
                resolution_hint=(
                    "Specify what you want to create (e.g. a bot, a "
                    "website, an app)."
                ),
            )
            ambiguities.append(missing_amb)
            clarifications.append(self._make_clarification(
                kind=CLARIFICATION_PROVIDE_CONTEXT,
                question=(
                    "What would you like to create? (e.g. a bot, a "
                    "website, an app)"
                ),
                options=["bot", "website", "app"],
                related_ambiguity_id=missing_amb.id,
                required=True,
            ))

        # 4. Under-specified (no features or keywords).
        if not intent.features and not intent.primary_action:
            under_amb = self._make_ambiguity(
                kind=AMBIGUITY_UNDER_SPECIFIED,
                description=(
                    "The request does not specify any features or "
                    "actions. It is under-specified."
                ),
                affected_text=intent.full_description,
                possible_interpretations=[],
                resolution_hint=(
                    "Specify the features you want (e.g. payment, "
                    "notifications, admin panel)."
                ),
            )
            ambiguities.append(under_amb)
            clarifications.append(self._make_clarification(
                kind=CLARIFICATION_SPECIFY,
                question=(
                    "What features would you like? (e.g. payment, "
                    "notifications, admin panel)"
                ),
                options=[
                    "payment", "notifications", "admin panel",
                    "user management", "orders",
                ],
                related_ambiguity_id=under_amb.id,
                required=False,
            ))

        # 5. Ambiguities from the requirement intelligence report.
        if requirement_report is not None:
            req_ambiguities = getattr(
                requirement_report, "ambiguities", None,
            )
            if req_ambiguities:
                for req_amb in req_ambiguities:
                    amb = self._make_ambiguity(
                        kind=AMBIGUITY_VAGUE,
                        description=f"Requirement intelligence detected ambiguity: {req_amb}",
                        affected_text=req_amb,
                        possible_interpretations=[],
                        resolution_hint="Please clarify this point.",
                    )
                    ambiguities.append(amb)
                    clarifications.append(self._make_clarification(
                        kind=CLARIFICATION_DISAMBIGUATE,
                        question=f"Could you clarify: {req_amb}?",
                        related_ambiguity_id=amb.id,
                        required=False,
                    ))

        return ambiguities, clarifications

    # ----------------------------------------------------------------- #
    # Internal helpers
    # ----------------------------------------------------------------- #

    def _check_vague(self, intent: UnifiedIntent) -> SemanticAmbiguity:
        """Check if the intent is vague."""
        if not intent.full_description:
            return self._make_ambiguity(
                kind=AMBIGUITY_VAGUE,
                description=(
                    "The intent is vague — the engine could not "
                    "determine what the user wants."
                ),
                affected_text="",
                possible_interpretations=[],
                resolution_hint=(
                    "Provide a more detailed description of what you "
                    "want."
                ),
            )

        # Check for vague words in the full description.
        lower_desc = intent.full_description.lower()
        for vague_word in _VAGUE_WORDS:
            if vague_word in lower_desc:
                return self._make_ambiguity(
                    kind=AMBIGUITY_VAGUE,
                    description=(
                        f"The request contains the vague word "
                        f"'{vague_word}', making the intent unclear."
                    ),
                    affected_text=vague_word,
                    possible_interpretations=[],
                    resolution_hint=(
                        "Replace vague words with specific terms."
                    ),
                )

        return None

    def _check_multiple_interpretations(
        self, sentence_analyses: Any,
    ) -> SemanticAmbiguity:
        """Check for multiple-interpretation words."""
        if not sentence_analyses:
            return None

        found_words = set()
        for sa in sentence_analyses:
            if not hasattr(sa, "normalized_text"):
                continue
            lower = sa.normalized_text.lower()
            for word in _MULTI_INTERPRETATION_WORDS:
                if word in lower.split():
                    found_words.add(word)

        if not found_words:
            return None

        return self._make_ambiguity(
            kind=AMBIGUITY_MULTIPLE_INTERPRETATIONS,
            description=(
                f"The request contains words with multiple "
                f"interpretations: {', '.join(found_words)}."
            ),
            affected_text=", ".join(found_words),
            possible_interpretations=[],
            resolution_hint=(
                "Replace pronouns with specific nouns."
            ),
        )

    def _make_ambiguity(
        self,
        kind: str,
        description: str,
        affected_text: str,
        possible_interpretations: List[str],
        resolution_hint: str,
    ) -> SemanticAmbiguity:
        """Create a SemanticAmbiguity with a unique ID."""
        self._ambiguity_counter += 1
        amb_id = f"AMB-{self._ambiguity_counter:03d}"
        return SemanticAmbiguity(
            id=amb_id,
            kind=kind,
            description=description,
            affected_text=affected_text,
            possible_interpretations=possible_interpretations,
            resolution_hint=resolution_hint,
            source_artefact=SOURCE_USER_REQUEST,
        )

    def _make_clarification(
        self,
        kind: str,
        question: str,
        options: List[str] = None,
        related_ambiguity_id: str = "",
        required: bool = True,
    ) -> ClarificationRequest:
        """Create a ClarificationRequest with a unique ID."""
        self._clarification_counter += 1
        clar_id = f"CLAR-{self._clarification_counter:03d}"
        return ClarificationRequest(
            id=clar_id,
            kind=kind,
            question=question,
            options=options or [],
            related_ambiguity_id=related_ambiguity_id,
            required=required,
            source_artefact=SOURCE_USER_REQUEST,
        )


__all__ = ["AmbiguityDetector"]
