"""Tolerant data readers for Execution Context (Spec 054)."""

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


class OrchestratorReader(_BaseReader):
    ARTEFACT_KEY = "engine_orchestrator_report"
    LIST_KEY = "plan"


class EcosystemReader(_BaseReader):
    ARTEFACT_KEY = "engine_ecosystem_report"
    LIST_KEY = "manifests"


class WorkspaceReader(_BaseReader):
    ARTEFACT_KEY = "workspace_management_report"
    LIST_KEY = "workspaces"


class ProjectContextReader(_BaseReader):
    ARTEFACT_KEY = "project_context_report"
    LIST_KEY = "contexts"


class UserRequestReader(_BaseReader):
    ARTEFACT_KEY = "user_request"
    LIST_KEY = "keys"

    def read(self, ctx: GenerationContext) -> GenericData:
        d = GenericData()
        try:
            a = ctx.get(self.ARTEFACT_KEY)
            if a is None:
                a = ctx.get("context_request") or ctx.get("execution_request")
            if a is None:
                d.error = "missing user_request"
                return d
            raw = _safe(a)
            d.raw, d.available = raw, True
            keys = raw.get("keys") or raw.get("shared_state") or []
            if isinstance(keys, list):
                d.items = keys
            elif isinstance(keys, dict):
                d.items = [{"key": k, "value": v} for k, v in keys.items()]
            elif keys:
                d.items = [keys]
        except Exception as e:
            d.error = str(e)
        return d


__all__ = [
    "GenericData",
    "OrchestratorReader",
    "EcosystemReader",
    "WorkspaceReader",
    "ProjectContextReader",
    "UserRequestReader",
]
