"""
Requirement intelligence reader — reads the Requirement Intelligence
Report from the generation context.

The :class:`RequirementIntelligenceReader` is responsible for
obtaining the ``requirement_intelligence_report`` artefact (produced
by the
:class:`~telegram_bot_engine.engines.generators.requirement_intelligence.RequirementIntelligenceEngine`)
and returning a normalised :class:`RequirementIntelligenceData`
object.

The reader is tolerant: it never raises when the requirement
intelligence report is not available.  It returns a
:class:`RequirementIntelligenceData` with ``available=False`` in that
case.

This module is a pure reader: it has no side effects and does not
modify the generation context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from ....core.context import GenerationContext
from .report_data import SOURCE_REQUIREMENT_INTELLIGENCE


# ---------------------------------------------------------------------------#
# Requirement intelligence data
# ---------------------------------------------------------------------------#

@dataclass
class RawRequirement:
    """A single raw requirement from the Requirement Intelligence
    Report.

    Attributes:
        id: The original ID (e.g. ``"REQ-001"``).
        name: The original name.
        display_name: The original display name.
        description: The original description.
        category: The original category.
        priority: The original priority.
        goal: The goal of the requirement.
        reason: The reason for the requirement.
    """

    id: str = ""
    name: str = ""
    display_name: str = ""
    description: str = ""
    category: str = ""
    priority: str = ""
    goal: str = ""
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "category": self.category,
            "priority": self.priority,
            "goal": self.goal,
            "reason": self.reason,
        }


@dataclass
class RequirementIntelligenceData:
    """Normalised view of the Requirement Intelligence Report.

    This is a lightweight container that holds the information the
    Architecture Decision Engine needs from the Requirement
    Intelligence Report.

    Attributes:
        intent_wants: The list of things the user wants.
        intent_does_not_want: The list of things the user does
            not want.
        final_goal: The final goal the user is trying to achieve.
        quality_level: The quality level the user specified.
        intent_confidence: The confidence of the intent
            analysis.
        requirements: The list of raw requirements.
        required_questions: The list of required questions.
        ambiguities: The list of ambiguity descriptions.
        conflicts: The list of conflict descriptions.
        summary: The summary of the requirement intelligence
            report.
        ready: Whether the requirement intelligence report was
            ready.
        available: Whether the requirement intelligence report
            was available.
    """

    intent_wants: List[str] = field(default_factory=list)
    intent_does_not_want: List[str] = field(default_factory=list)
    final_goal: str = ""
    quality_level: str = ""
    intent_confidence: float = 0.0
    requirements: List[RawRequirement] = field(default_factory=list)
    required_questions: List[str] = field(default_factory=list)
    ambiguities: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    summary: str = ""
    ready: bool = False
    available: bool = False

    @property
    def source_artefact(self) -> str:
        return SOURCE_REQUIREMENT_INTELLIGENCE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent_wants": list(self.intent_wants),
            "intent_does_not_want": list(self.intent_does_not_want),
            "final_goal": self.final_goal,
            "quality_level": self.quality_level,
            "intent_confidence": self.intent_confidence,
            "requirements": [r.to_dict() for r in self.requirements],
            "required_questions": list(self.required_questions),
            "ambiguities": list(self.ambiguities),
            "conflicts": list(self.conflicts),
            "summary": self.summary,
            "ready": self.ready,
            "available": self.available,
        }


class RequirementIntelligenceReader:
    """Reads the Requirement Intelligence Report from the generation
    context.

    The reader looks for the ``requirement_intelligence_report``
    artefact.  When present, it extracts the intent analysis,
    requirements, required questions, ambiguities, conflicts, and
    summary.  When absent, it returns a
    :class:`RequirementIntelligenceData` with ``available=False``.
    """

    def read(
        self, context: GenerationContext,
    ) -> RequirementIntelligenceData:
        """Read the requirement intelligence report and return a
        :class:`RequirementIntelligenceData`.
        """
        report = context.get("requirement_intelligence_report")
        if report is None:
            return RequirementIntelligenceData(available=False)

        return self._read_from_report(report)

    # ----------------------------------------------------------------- #
    # Internal helpers
    # ----------------------------------------------------------------- #

    def _read_from_report(
        self, report: Any,
    ) -> RequirementIntelligenceData:
        """Extract data from the requirement intelligence report
        artefact."""
        def get_attr(name: str, default: Any = None) -> Any:
            if hasattr(report, name):
                return getattr(report, name)
            if isinstance(report, dict):
                return report.get(name, default)
            return default

        # Intent analysis.
        intent = get_attr("intent")
        wants: List[str] = []
        does_not_want: List[str] = []
        final_goal = ""
        quality_level = ""
        intent_confidence = 0.0

        if intent is not None:
            if hasattr(intent, "to_dict"):
                intent_dict = intent.to_dict()
            elif isinstance(intent, dict):
                intent_dict = intent
            else:
                intent_dict = {}
            wants = self._as_string_list(intent_dict.get("wants", []))
            does_not_want = self._as_string_list(
                intent_dict.get("does_not_want", [])
            )
            final_goal = str(intent_dict.get("final_goal", "") or "")
            quality_level = str(
                intent_dict.get("quality_level", "") or ""
            )
            intent_confidence = float(
                intent_dict.get("confidence", 0.0) or 0.0
            )

        # Requirements.
        requirements_raw = get_attr("requirements", []) or []
        requirements: List[RawRequirement] = []
        if isinstance(requirements_raw, (list, tuple)):
            for req in requirements_raw:
                if isinstance(req, dict):
                    req_id = str(req.get("id", "") or "")
                    req_name = str(req.get("name", "") or "")
                    req_display = str(req.get("display_name", "") or "")
                    req_desc = str(req.get("description", "") or "")
                    req_cat = str(req.get("category", "") or "")
                    req_pri = str(req.get("priority", "") or "")
                    req_goal = str(req.get("goal", "") or "")
                    req_reason = str(req.get("reason", "") or "")
                else:
                    req_id = str(getattr(req, "id", "") or "")
                    req_name = str(getattr(req, "name", "") or "")
                    req_display = str(
                        getattr(req, "display_name", "") or ""
                    )
                    req_desc = str(
                        getattr(req, "description", "") or ""
                    )
                    req_cat = str(getattr(req, "category", "") or "")
                    req_pri = str(getattr(req, "priority", "") or "")
                    req_goal = str(getattr(req, "goal", "") or "")
                    req_reason = str(getattr(req, "reason", "") or "")
                requirements.append(RawRequirement(
                    id=req_id,
                    name=req_name,
                    display_name=req_display,
                    description=req_desc,
                    category=req_cat,
                    priority=req_pri,
                    goal=req_goal,
                    reason=req_reason,
                ))

        # Required questions.
        questions_raw = get_attr("required_questions", []) or []
        required_questions = self._extract_descriptions(questions_raw)

        # Ambiguities.
        ambiguities_raw = get_attr("ambiguities", []) or []
        ambiguities = self._extract_descriptions(ambiguities_raw)

        # Conflicts.
        conflicts_raw = get_attr("conflicts", []) or []
        conflicts = self._extract_descriptions(conflicts_raw)

        # Summary and ready flag.
        summary = str(get_attr("summary", "") or "")
        ready = bool(get_attr("ready", False))

        return RequirementIntelligenceData(
            intent_wants=wants,
            intent_does_not_want=does_not_want,
            final_goal=final_goal,
            quality_level=quality_level,
            intent_confidence=intent_confidence,
            requirements=requirements,
            required_questions=required_questions,
            ambiguities=ambiguities,
            conflicts=conflicts,
            summary=summary,
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

    @staticmethod
    def _extract_descriptions(items: Any) -> List[str]:
        """Extract the ``description`` field from a list of
        objects/dicts.
        """
        if not isinstance(items, (list, tuple)):
            return []
        result: List[str] = []
        for item in items:
            if isinstance(item, str):
                result.append(item)
                continue
            value: Any = None
            if isinstance(item, dict):
                value = item.get("description") or item.get("text")
            elif hasattr(item, "description"):
                value = getattr(item, "description", "")
            elif hasattr(item, "text"):
                value = getattr(item, "text", "")
            if value:
                result.append(str(value))
        return result


__all__ = [
    "RequirementIntelligenceReader",
    "RequirementIntelligenceData",
    "RawRequirement",
]
