"""Tolerant data readers for Code Optimization (Spec 034)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ....core.context import GenerationContext


def _safe(a: Any) -> Dict[str, Any]:
    if hasattr(a, "to_dict"):
        return a.to_dict()
    if isinstance(a, dict):
        return a
    return {"value": str(a)}


@dataclass
class GenericData:
    available: bool = False
    raw: Optional[Dict[str, Any]] = None
    items: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""


class _BaseReader:
    ARTEFACT_KEY = ""
    LIST_KEY = ""

    def read(self, ctx: GenerationContext) -> GenericData:
        d = GenericData()
        try:
            a = ctx.get(self.ARTEFACT_KEY)
            if a is None:
                d.error = f"missing {self.ARTEFACT_KEY}"
                return d
            raw = _safe(a)
            d.raw, d.available = raw, True
            if self.LIST_KEY:
                d.items = raw.get(self.LIST_KEY) or []
        except Exception as e:
            d.error = str(e)
        return d


class BusinessLogicReader(_BaseReader):
    ARTEFACT_KEY = "business_logic_report"
    LIST_KEY = "bodies"


class ClassGenerationReader(_BaseReader):
    ARTEFACT_KEY = "class_generation_report"
    LIST_KEY = "classes"


class FunctionGenerationReader(_BaseReader):
    ARTEFACT_KEY = "function_generation_report"
    LIST_KEY = "methods"


class ProjectBuilderReader(_BaseReader):
    ARTEFACT_KEY = "project_builder_report"
    LIST_KEY = "files"


class ArchitectureDecisionReader(_BaseReader):
    ARTEFACT_KEY = "architecture_decision_report"
    LIST_KEY = "decisions"


class CodePlanReader(_BaseReader):
    ARTEFACT_KEY = "code_generation_plan"
    LIST_KEY = "units"


__all__ = [
    "GenericData",
    "BusinessLogicReader",
    "ClassGenerationReader",
    "FunctionGenerationReader",
    "ProjectBuilderReader",
    "ArchitectureDecisionReader",
    "CodePlanReader",
]
