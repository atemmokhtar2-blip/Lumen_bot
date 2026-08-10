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
        data.raw = raw if isinstance(raw, dict) else {"value": raw}
        if hasattr(raw, "to_dict"):
            data.items = [raw.to_dict()]
        elif isinstance(raw, dict):
            data.items = [raw]
        elif isinstance(raw, list):
            data.items = [x if isinstance(x, dict) else {"value": x} for x in raw]
        return data


__all__ = ["GenericData", "ProjectOutputReader"]
