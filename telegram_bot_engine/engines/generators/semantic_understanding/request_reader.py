"""
Request reader — reads the user request from the generation context.

The :class:`RequestReader` is responsible for obtaining the user's
request from the generation context.  It prefers the
``analysis_report`` artefact (produced by the
:class:`~telegram_bot_engine.engines.generators.analyzer.AnalyzerEngine`)
because it is the *authoritative* description of the user's request.
When the analysis report is not available it falls back to the raw
``context.request``.

The reader is tolerant: it never raises on missing fields.  It
returns a :class:`RequestData` with ``available=False`` when no
request data is present at all.

This module is a pure reader: it has no side effects and does not
modify the generation context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from ....core.context import GenerationContext
from .report_data import SOURCE_USER_REQUEST


# ---------------------------------------------------------------------------#
# Request data
# ---------------------------------------------------------------------------#

@dataclass
class RequestData:
    """Normalised view of the user's request.

    Attributes:
        raw_request: The original, unmodified user request.
        cleaned_request: The request after cleaning (from the
            analysis report, or the raw request when the analysis
            report is not available).
        project_name: The suggested project name (from the
            analysis report, if available).
        description: A full description of what the bot should
            do (from the analysis report, if available).
        features: The list of feature names detected by the
            analyzer (from the analysis report, if available).
        keywords: The list of keyword strings detected by the
            analyzer (from the analysis report, if available).
        bot_types: The list of bot type identifiers detected by
            the analyzer (from the analysis report, if available).
        has_analysis_report: Whether the analysis report was
            available.
        available: Whether any request data was available at all.
    """

    raw_request: str = ""
    cleaned_request: str = ""
    project_name: str = ""
    description: str = ""
    features: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    bot_types: List[str] = field(default_factory=list)
    has_analysis_report: bool = False
    available: bool = False

    @property
    def source_artefact(self) -> str:
        return SOURCE_USER_REQUEST

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_request": self.raw_request,
            "cleaned_request": self.cleaned_request,
            "project_name": self.project_name,
            "description": self.description,
            "features": list(self.features),
            "keywords": list(self.keywords),
            "bot_types": list(self.bot_types),
            "has_analysis_report": self.has_analysis_report,
            "available": self.available,
        }


class RequestReader:
    """Reads the user request from the generation context.

    The reader first looks for the ``analysis_report`` artefact.  When
    present, it extracts the structured fields (cleaned request,
    project name, description, features, keywords, bot types).  When
    the analysis report is not present, it falls back to the raw
    ``context.request``.
    """

    def read(self, context: GenerationContext) -> RequestData:
        """Read the user request and return a :class:`RequestData`."""
        raw_request = ""
        if hasattr(context, "request"):
            raw_request = str(context.request or "").strip()

        # Try the analysis_report artefact first.
        analysis_report = context.get("analysis_report")

        if analysis_report is not None:
            return self._read_from_analysis_report(
                raw_request, analysis_report,
            )

        # Fall back to the raw request.
        if not raw_request:
            return RequestData(available=False)

        return RequestData(
            raw_request=raw_request,
            cleaned_request=raw_request,
            available=True,
        )

    # ----------------------------------------------------------------- #
    # Internal helpers
    # ----------------------------------------------------------------- #

    def _read_from_analysis_report(
        self,
        raw_request: str,
        analysis_report: Any,
    ) -> RequestData:
        """Extract request data from the analysis report artefact."""
        def get_attr(name: str, default: Any = None) -> Any:
            if hasattr(analysis_report, name):
                return getattr(analysis_report, name)
            if isinstance(analysis_report, dict):
                return analysis_report.get(name, default)
            return default

        cleaned = str(get_attr("cleaned_request", "") or "").strip()
        if not cleaned:
            cleaned = str(get_attr("raw_request", "") or "").strip()
        if not cleaned:
            cleaned = raw_request

        project_name = str(get_attr("project_name", "") or "")
        description = str(get_attr("description", "") or "")

        features_raw = get_attr("features", []) or []
        keywords_raw = get_attr("keywords", []) or []
        bot_types_raw = get_attr("bot_types", []) or []

        features = self._extract_names(features_raw, "name")
        keywords = self._extract_strings(keywords_raw, "keyword")
        bot_types = self._extract_names(bot_types_raw, "type")

        return RequestData(
            raw_request=raw_request,
            cleaned_request=cleaned,
            project_name=project_name,
            description=description,
            features=features,
            keywords=keywords,
            bot_types=bot_types,
            has_analysis_report=True,
            available=bool(cleaned),
        )

    @staticmethod
    def _extract_names(items: Any, attr: str) -> List[str]:
        if not isinstance(items, (list, tuple)):
            return []
        result: List[str] = []
        for item in items:
            value: Any = None
            if isinstance(item, dict):
                value = item.get(attr)
            elif hasattr(item, attr):
                value = getattr(item, attr)
            if value:
                result.append(str(value))
        return result

    @staticmethod
    def _extract_strings(items: Any, attr: str) -> List[str]:
        if not isinstance(items, (list, tuple)):
            return []
        result: List[str] = []
        for item in items:
            if isinstance(item, str):
                result.append(item)
                continue
            value: Any = None
            if isinstance(item, dict):
                value = item.get(attr)
            elif hasattr(item, attr):
                value = getattr(item, attr)
            if value:
                result.append(str(value))
        return result


__all__ = ["RequestReader", "RequestData"]
