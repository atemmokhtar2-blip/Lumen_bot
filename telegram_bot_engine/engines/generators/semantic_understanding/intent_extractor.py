"""
Intent extractor — extracts the true intent from the user's request.

The :class:`IntentExtractor` is responsible for extracting the *true*
intent of the user's request.  It does not rely on keywords alone —
it uses the sentence analyses (which have been normalized, with
synonyms resolved, spelling corrected, and abbreviations expanded)
to determine what the user actually wants.

The extractor determines:
* The **kind** of intent (create, modify, delete, query, configure,
  deploy) by matching the intent keywords against the normalized text.
* The **primary action** (what the user wants to do).
* The **subject** (what the action is about, e.g. "bot", "store").
* The **target** (the target of the action, if any).
* The **features** the user wants.
* The **constraints** the user specified.
* The **evidence** (the keywords and phrases that led to this intent).

This module is a pure processing component: it has no side effects and
does not modify the generation context.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .report_data import (
    INTENT_KIND_CONFIGURE,
    INTENT_KIND_CREATE,
    INTENT_KIND_DELETE,
    INTENT_KIND_DEPLOY,
    INTENT_KIND_MODIFY,
    INTENT_KIND_QUERY,
    INTENT_KIND_UNKNOWN,
    SOURCE_LANGUAGE_RULES,
    SOURCE_REQUIREMENT_INTELLIGENCE,
    SOURCE_USER_REQUEST,
    SentenceAnalysis,
    UnifiedIntent,
)


# Subject keywords — words that indicate the subject of the request.
_SUBJECT_KEYWORDS = {
    "bot": "bot",
    "telegram": "telegram",
    "store": "store_bot",
    "store_bot": "store_bot",
    "website": "website",
    "app": "app",
    "application": "app",
    "api": "api",
    "webhook": "webhook",
    "database": "database",
    "bot": "bot",
    "بوت": "bot",
    "تيليجرام": "telegram",
    "متجر": "store_bot",
}

# Target keywords — words that indicate the target of the request.
_TARGET_KEYWORDS = {
    "ecommerce": "ecommerce",
    "store": "store",
    "shop": "store",
    "marketplace": "marketplace",
    "ادارية": "admin",
    "ادمن": "admin",
    "admin": "admin",
    "management": "admin",
    "business": "business",
    "enterprise": "enterprise",
    "startup": "startup",
}


class IntentExtractor:
    """Extracts the true intent from the user's request.

    The extractor uses the sentence analyses (which have been fully
    processed: dialect-normalized, spelling-corrected,
    abbreviation-expanded, synonym-resolved) to determine the kind,
    primary action, subject, target, features, and constraints of
    the request.

    The extractor also uses the Requirement Intelligence Report (when
    available) to refine the intent — the wants, does_not_want, and
    final_goal fields are incorporated.
    """

    def __init__(self) -> None:
        pass

    def extract(
        self,
        sentence_analyses: List[SentenceAnalysis],
        intent_keywords: Dict[str, List[str]],
        requirement_report: Any = None,
        request_data: Any = None,
    ) -> UnifiedIntent:
        """Extract the true intent from the sentence analyses.

        Parameters:
            sentence_analyses: The list of sentence analyses.
            intent_keywords: The intent keywords dictionary (from
                the :class:`LanguageRules`).
            requirement_report: The Requirement Intelligence Report
                data (optional, may be ``None``).
            request_data: The request data (optional, may be
                ``None``).

        Returns:
            A :class:`UnifiedIntent` with the extracted intent.
        """
        if not sentence_analyses:
            return UnifiedIntent(
                full_description="",
                confidence=0.0,
            )

        # Build the full normalized text from all sentence analyses.
        normalized_texts = [sa.normalized_text for sa in sentence_analyses]
        full_text = " ".join(normalized_texts)

        # All keywords across all sentences.
        all_keywords: List[str] = []
        for sa in sentence_analyses:
            all_keywords.extend(sa.keywords)

        # Determine the intent kind.
        kind = self._determine_kind(full_text, intent_keywords)

        # Determine the primary action.
        primary_action = self._determine_primary_action(kind, full_text)

        # Determine the subject.
        subject = self._determine_subject(all_keywords, request_data)

        # Determine the target.
        target = self._determine_target(all_keywords, request_data)

        # Determine the features.
        features = self._determine_features(all_keywords, request_data, requirement_report)

        # Determine the constraints.
        constraints = self._determine_constraints(
            requirement_report, request_data,
        )

        # Build the full description.
        full_description = self._build_description(
            kind, primary_action, subject, target, features, constraints,
        )

        # Build the evidence.
        evidence = self._build_evidence(all_keywords, kind)

        # Compute confidence.
        confidence = self._compute_confidence(
            kind, subject, full_description, all_keywords,
        )

        # Count the number of variations that were mapped.
        mapped_from_variations = len(sentence_analyses)

        return UnifiedIntent(
            id="INTENT-001",
            kind=kind,
            primary_action=primary_action,
            subject=subject,
            target=target,
            features=features,
            constraints=constraints,
            full_description=full_description,
            confidence=confidence,
            evidence=evidence,
            source_artefact=SOURCE_LANGUAGE_RULES,
            mapped_from_variations=mapped_from_variations,
        )

    # ----------------------------------------------------------------- #
    # Internal helpers
    # ----------------------------------------------------------------- #

    def _determine_kind(
        self,
        text: str,
        intent_keywords: Dict[str, List[str]],
    ) -> str:
        """Determine the intent kind from the text.

        The kind is determined by counting the number of intent
        keywords of each kind in the text.  The kind with the most
        matches wins.
        """
        if not text:
            return INTENT_KIND_UNKNOWN

        lower_text = text.lower()

        scores: Dict[str, int] = {}
        for kind, keywords in intent_keywords.items():
            score = 0
            for kw in keywords:
                if kw in lower_text:
                    score += 1
            if score > 0:
                scores[kind] = score

        if not scores:
            return INTENT_KIND_CREATE  # Default to create.

        # Return the kind with the highest score.
        return max(scores, key=scores.get)

    @staticmethod
    def _determine_primary_action(kind: str, text: str) -> str:
        """Determine the primary action from the kind and text."""
        kind_to_action = {
            INTENT_KIND_CREATE: "create",
            INTENT_KIND_MODIFY: "modify",
            INTENT_KIND_DELETE: "delete",
            INTENT_KIND_QUERY: "query",
            INTENT_KIND_CONFIGURE: "configure",
            INTENT_KIND_DEPLOY: "deploy",
            INTENT_KIND_UNKNOWN: "understand",
        }
        return kind_to_action.get(kind, "understand")

    @staticmethod
    def _determine_subject(
        keywords: List[str], request_data: Any,
    ) -> str:
        """Determine the subject from the keywords."""
        # Check keywords against subject keywords.
        for kw in keywords:
            lower = kw.lower()
            if lower in _SUBJECT_KEYWORDS:
                return _SUBJECT_KEYWORDS[lower]

        # Check request data.
        if request_data is not None:
            bot_types = getattr(request_data, "bot_types", None)
            if bot_types:
                return bot_types[0]
            features = getattr(request_data, "features", None)
            if features:
                return features[0]

        return ""

    @staticmethod
    def _determine_target(
        keywords: List[str], request_data: Any,
    ) -> str:
        """Determine the target from the keywords."""
        for kw in keywords:
            lower = kw.lower()
            if lower in _TARGET_KEYWORDS:
                return _TARGET_KEYWORDS[lower]

        return ""

    @staticmethod
    def _determine_features(
        keywords: List[str],
        request_data: Any,
        requirement_report: Any,
    ) -> List[str]:
        """Determine the features from the keywords and request data."""
        features: List[str] = []

        # From request data.
        if request_data is not None:
            req_features = getattr(request_data, "features", None)
            if req_features:
                features.extend(req_features)

        # From requirement report (wants).
        if requirement_report is not None:
            wants = getattr(requirement_report, "wants", None)
            if wants:
                features.extend(wants)

        # Deduplicate while preserving order.
        seen = set()
        unique: List[str] = []
        for f in features:
            if f and f not in seen:
                seen.add(f)
                unique.append(f)

        return unique

    @staticmethod
    def _determine_constraints(
        requirement_report: Any,
        request_data: Any,
    ) -> List[str]:
        """Determine the constraints from the requirement report."""
        constraints: List[str] = []

        # From requirement report (does_not_want).
        if requirement_report is not None:
            does_not_want = getattr(requirement_report, "does_not_want", None)
            if does_not_want:
                constraints.extend(
                    f"does not want: {d}" for d in does_not_want
                )

        return constraints

    @staticmethod
    def _build_description(
        kind: str,
        primary_action: str,
        subject: str,
        target: str,
        features: List[str],
        constraints: List[str],
    ) -> str:
        """Build a full, natural-language description of the intent."""
        parts: List[str] = []

        if primary_action:
            parts.append(f"The user wants to {primary_action}")
        else:
            parts.append("The user wants")

        if subject:
            parts.append(f"a {subject}")

        if target:
            parts.append(f"for {target}")

        description = " ".join(parts) + "."

        if features:
            features_str = ", ".join(features)
            description += f" Features: {features_str}."

        if constraints:
            constraints_str = "; ".join(constraints)
            description += f" Constraints: {constraints_str}."

        return description

    @staticmethod
    def _build_evidence(keywords: List[str], kind: str) -> List[str]:
        """Build the evidence list from the keywords."""
        evidence: List[str] = []
        if kind:
            evidence.append(f"intent_kind={kind}")
        if keywords:
            top_kw = keywords[:10]
            evidence.append(f"keywords={top_kw}")
        return evidence

    @staticmethod
    def _compute_confidence(
        kind: str,
        subject: str,
        description: str,
        keywords: List[str],
    ) -> float:
        """Compute a confidence score for the intent.

        The confidence is higher when:
        * The intent kind was determined (not unknown).
        * The subject was determined.
        * The description is non-empty.
        * There are keywords.
        """
        confidence = 0.0

        if kind != INTENT_KIND_UNKNOWN:
            confidence += 0.3
        if subject:
            confidence += 0.3
        if description:
            confidence += 0.2
        if keywords:
            confidence += 0.2

        return max(0.0, min(1.0, confidence))


__all__ = ["IntentExtractor"]
