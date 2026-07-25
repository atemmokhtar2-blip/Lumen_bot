"""
Semantic understanding reader — reads the Semantic Understanding
Report from the generation context.

The :class:`SemanticUnderstandingReader` is responsible for obtaining
the ``semantic_understanding_report`` artefact (produced by the
:class:`~telegram_bot_engine.engines.generators.semantic_understanding.SemanticUnderstandingEngine`)
and returning a normalised :class:`SemanticUnderstandingData` object.

The reader is tolerant: it never raises when the semantic
understanding report is not available.  It returns a
:class:`SemanticUnderstandingData` with ``available=False`` in that
case.

This module is a pure reader: it has no side effects and does not
modify the generation context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from ....core.context import GenerationContext
from .report_data import SOURCE_SEMANTIC_UNDERSTANDING


# ---------------------------------------------------------------------------#
# Semantic understanding data
# ---------------------------------------------------------------------------#

@dataclass
class SemanticKeyword:
    """A keyword from the semantic understanding report.

    Attributes:
        word: The keyword.
        weight: The importance weight.
        normalized_form: The canonical form.
        original_forms: The different forms the keyword appeared
            in.
    """

    word: str = ""
    weight: float = 1.0
    normalized_form: str = ""
    original_forms: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "word": self.word,
            "weight": self.weight,
            "normalized_form": self.normalized_form,
            "original_forms": list(self.original_forms),
        }


@dataclass
class SemanticRequirement:
    """A requirement/feature from the semantic understanding report's
    intent.

    Attributes:
        name: The feature name.
        kind: The intent kind.
        primary_action: The primary action.
        subject: The subject of the action.
        target: The target of the action.
    """

    name: str = ""
    kind: str = ""
    primary_action: str = ""
    subject: str = ""
    target: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "primary_action": self.primary_action,
            "subject": self.subject,
            "target": self.target,
        }


@dataclass
class SemanticUnderstandingData:
    """Normalised view of the Semantic Understanding Report.

    This is a lightweight container that holds the information the
    Architecture Decision Engine needs from the Semantic
    Understanding Report.

    Attributes:
        intent_kind: The intent kind (create, modify, delete,
            query, configure, deploy).
        intent_description: The full description of the intent.
        intent_subject: The subject of the intent.
        intent_target: The target of the intent.
        intent_features: The features from the intent.
        intent_constraints: The constraints from the intent.
        intent_confidence: The confidence of the intent.
        keywords: The list of important keywords.
        normalized_request: The fully normalized request.
        original_request: The original, unmodified request.
        language: The detected language.
        style: The detected style.
        confidence: The overall confidence score.
        confidence_level: The confidence level.
        ready: Whether the semantic understanding report was
            ready.
        available: Whether the semantic understanding report was
            available.
    """

    intent_kind: str = ""
    intent_description: str = ""
    intent_subject: str = ""
    intent_target: str = ""
    intent_features: List[str] = field(default_factory=list)
    intent_constraints: List[str] = field(default_factory=list)
    intent_confidence: float = 0.0
    keywords: List[SemanticKeyword] = field(default_factory=list)
    normalized_request: str = ""
    original_request: str = ""
    language: str = ""
    style: str = ""
    confidence: float = 0.0
    confidence_level: str = ""
    ready: bool = False
    available: bool = False

    @property
    def source_artefact(self) -> str:
        return SOURCE_SEMANTIC_UNDERSTANDING

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent_kind": self.intent_kind,
            "intent_description": self.intent_description,
            "intent_subject": self.intent_subject,
            "intent_target": self.intent_target,
            "intent_features": list(self.intent_features),
            "intent_constraints": list(self.intent_constraints),
            "intent_confidence": self.intent_confidence,
            "keywords": [kw.to_dict() for kw in self.keywords],
            "normalized_request": self.normalized_request,
            "original_request": self.original_request,
            "language": self.language,
            "style": self.style,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level,
            "ready": self.ready,
            "available": self.available,
        }


class SemanticUnderstandingReader:
    """Reads the Semantic Understanding Report from the generation
    context.

    The reader looks for the ``semantic_understanding_report``
    artefact.  When present, it extracts the intent, keywords,
    normalized request, language, style, and confidence.  When
    absent, it returns a :class:`SemanticUnderstandingData` with
    ``available=False``.
    """

    def read(
        self, context: GenerationContext,
    ) -> SemanticUnderstandingData:
        """Read the semantic understanding report and return a
        :class:`SemanticUnderstandingData`.
        """
        report = context.get("semantic_understanding_report")
        if report is None:
            return SemanticUnderstandingData(available=False)

        return self._read_from_report(report)

    # ----------------------------------------------------------------- #
    # Internal helpers
    # ----------------------------------------------------------------- #

    def _read_from_report(
        self, report: Any,
    ) -> SemanticUnderstandingData:
        """Extract data from the semantic understanding report
        artefact.
        """
        def get_attr(name: str, default: Any = None) -> Any:
            if hasattr(report, name):
                return getattr(report, name)
            if isinstance(report, dict):
                return report.get(name, default)
            return default

        # Intent.
        intent = get_attr("intent")
        intent_kind = ""
        intent_description = ""
        intent_subject = ""
        intent_target = ""
        intent_features: List[str] = []
        intent_constraints: List[str] = []
        intent_confidence = 0.0

        if intent is not None:
            if hasattr(intent, "to_dict"):
                intent_dict = intent.to_dict()
            elif isinstance(intent, dict):
                intent_dict = intent
            else:
                intent_dict = {}
            intent_kind = str(intent_dict.get("kind", "") or "")
            intent_description = str(
                intent_dict.get("full_description", "") or ""
            )
            intent_subject = str(intent_dict.get("subject", "") or "")
            intent_target = str(intent_dict.get("target", "") or "")
            intent_features = self._as_string_list(
                intent_dict.get("features", [])
            )
            intent_constraints = self._as_string_list(
                intent_dict.get("constraints", [])
            )
            intent_confidence = float(
                intent_dict.get("confidence", 0.0) or 0.0
            )

        # Keywords.
        keywords_raw = get_attr("important_keywords", []) or []
        keywords: List[SemanticKeyword] = []
        if isinstance(keywords_raw, (list, tuple)):
            for kw in keywords_raw:
                if isinstance(kw, dict):
                    word = str(kw.get("word", "") or "")
                    weight = float(kw.get("weight", 1.0) or 1.0)
                    norm = str(kw.get("normalized_form", "") or "")
                    orig = self._as_string_list(
                        kw.get("original_forms", [])
                    )
                else:
                    word = str(getattr(kw, "word", "") or "")
                    weight = float(getattr(kw, "weight", 1.0) or 1.0)
                    norm = str(
                        getattr(kw, "normalized_form", "") or ""
                    )
                    orig = list(getattr(kw, "original_forms", []) or [])
                if word:
                    keywords.append(SemanticKeyword(
                        word=word,
                        weight=weight,
                        normalized_form=norm,
                        original_forms=orig,
                    ))

        # Normalized request.
        normalized_request = str(
            get_attr("normalized_request", "") or ""
        )
        original_request = str(
            get_attr("original_request", "") or ""
        )

        # Language and style.
        language = str(get_attr("language", "") or "")
        style = str(get_attr("style", "") or "")

        # Confidence.
        confidence = float(get_attr("confidence", 0.0) or 0.0)
        confidence_level = str(
            get_attr("confidence_level", "") or ""
        )
        ready = bool(get_attr("ready", False))

        return SemanticUnderstandingData(
            intent_kind=intent_kind,
            intent_description=intent_description,
            intent_subject=intent_subject,
            intent_target=intent_target,
            intent_features=intent_features,
            intent_constraints=intent_constraints,
            intent_confidence=intent_confidence,
            keywords=keywords,
            normalized_request=normalized_request,
            original_request=original_request,
            language=language,
            style=style,
            confidence=confidence,
            confidence_level=confidence_level,
            ready=ready,
            available=True,
        )

    @staticmethod
    def _as_string_list(value: Any) -> List[str]:
        """Convert a value to a list of strings."""
        if isinstance(value, (list, tuple)):
            return [str(v) for v in value if v is not None]
        if isinstance(value, str):
            return [value]
        return []


__all__ = [
    "SemanticUnderstandingReader",
    "SemanticUnderstandingData",
    "SemanticKeyword",
    "SemanticRequirement",
]
