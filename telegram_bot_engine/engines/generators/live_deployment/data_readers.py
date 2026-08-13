"""Data readers for Live Deployment Engine (Spec 065) — shared GenericData base."""
from __future__ import annotations

from typing import Any, Dict, List

from ..common.tolerant_readers import GenericData, BaseReader as _BaseReader


class ProjectOutputReader(_BaseReader):
    ARTEFACT_KEY = "final_project"

    def read(self, context) -> GenericData:
        data = GenericData()
        if context is None:
            return data
        raw = context.get(self.ARTEFACT_KEY) if hasattr(context, "get") else None
        if raw is None:
            return data
        data.available = True
        data.raw = raw if isinstance(raw, dict) else {"value": str(raw)}
        if hasattr(raw, "to_dict"):
            data.items = [raw.to_dict()]
        elif isinstance(raw, dict):
            data.items = [raw]
        elif isinstance(raw, list):
            data.items = [x if isinstance(x, dict) else {"value": x} for x in raw]
        return data


class MaterializeReader(_BaseReader):
    ARTEFACT_KEY = "materialize_report"


class ProductionReadinessReader(_BaseReader):
    ARTEFACT_KEY = "production_readiness_report"


class E2EReader(_BaseReader):
    ARTEFACT_KEY = "e2e_scenario_testing_report"


class ReviewReader(_BaseReader):
    ARTEFACT_KEY = "code_refactoring_report"


__all__ = [
    "GenericData",
    "ProjectOutputReader",
    "MaterializeReader",
    "ProductionReadinessReader",
    "E2EReader",
    "ReviewReader",
]
