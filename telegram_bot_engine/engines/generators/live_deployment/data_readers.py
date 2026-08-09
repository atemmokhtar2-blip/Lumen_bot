"""Data readers for Live Deployment Engine (Spec 065)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class GenericData:
    available: bool = False
    items: List[Dict[str, Any]] = field(default_factory=list)
    raw: Any = None


class _BaseReader:
    ARTEFACT_KEY = ""

    def read(self, context) -> GenericData:
        data = GenericData()
        if context is None:
            return data
        raw = context.get(self.ARTEFACT_KEY) if hasattr(context, "get") else None
        if raw is None:
            return data
        data.available = True
        data.raw = raw
        if hasattr(raw, "to_dict"):
            data.items = [raw.to_dict()]
        elif isinstance(raw, dict):
            data.items = [raw]
        elif isinstance(raw, list):
            data.items = [x if isinstance(x, dict) else {"value": x} for x in raw]
        return data


class ProjectOutputReader(_BaseReader):
    ARTEFACT_KEY = "final_project"


class MaterializeReader(_BaseReader):
    ARTEFACT_KEY = "materialize_report"


class ProductionReadinessReader(_BaseReader):
    ARTEFACT_KEY = "production_readiness_report"


class E2EReader(_BaseReader):
    ARTEFACT_KEY = "e2e_scenario_testing_report"


class ReviewReader(_BaseReader):
    ARTEFACT_KEY = "code_refactoring_report"
