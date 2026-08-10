"""Tolerant data readers for Repository Management (Spec 046)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..common.tolerant_readers import GenericData, BaseReader as _BaseReader, _safe
from ....core.context import GenerationContext


class ProjectContextReader(_BaseReader):
    ARTEFACT_KEY = "project_context_report"
    LIST_KEY = "contexts"


class ProductionReadinessReader(_BaseReader):
    ARTEFACT_KEY = "production_readiness_report"
    LIST_KEY = "axes"


class UserRequestReader(_BaseReader):
    ARTEFACT_KEY = "user_request"
    LIST_KEY = "operations"

    def read(self, ctx: GenerationContext) -> GenericData:
        d = GenericData()
        try:
            a = ctx.get(self.ARTEFACT_KEY)
            if a is None:
                # Also try nested keys commonly used
                a = ctx.get("repository_request") or ctx.get("repo_request")
            if a is None:
                d.error = "missing user_request"
                return d
            raw = _safe(a)
            d.raw, d.available = raw, True
            ops = raw.get("operations") or raw.get("requested_operations") or []
            if isinstance(ops, list):
                d.items = ops
            elif ops:
                d.items = [ops]
        except Exception as e:
            d.error = str(e)
        return d


__all__ = [
    "GenericData",
    "ProjectContextReader",
    "ProductionReadinessReader",
    "UserRequestReader",
]
