"""Tolerant data readers for Synchronization Engine (Spec 055)."""

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


class ExecutionContextReader(_BaseReader):
    ARTEFACT_KEY = "execution_context_report"
    LIST_KEY = "changes"


class OrchestratorReader(_BaseReader):
    ARTEFACT_KEY = "engine_orchestrator_report"
    LIST_KEY = "plan"


class EcosystemReader(_BaseReader):
    ARTEFACT_KEY = "engine_ecosystem_report"
    LIST_KEY = "manifests"


class WorkspaceReader(_BaseReader):
    ARTEFACT_KEY = "workspace_management_report"
    LIST_KEY = "workspaces"


class UserRequestReader(_BaseReader):
    ARTEFACT_KEY = "user_request"
    LIST_KEY = "updates"

    def read(self, ctx: GenerationContext) -> GenericData:
        d = GenericData()
        try:
            a = ctx.get(self.ARTEFACT_KEY)
            if a is None:
                a = ctx.get("sync_request")
            if a is None:
                d.error = "missing user_request"
                return d
            raw = _safe(a)
            d.raw, d.available = raw, True
            updates = raw.get("updates") or raw.get("sync_events") or []
            if isinstance(updates, list):
                d.items = updates
            elif updates:
                d.items = [updates]
        except Exception as e:
            d.error = str(e)
        return d


__all__ = [
    "GenericData",
    "ExecutionContextReader",
    "OrchestratorReader",
    "EcosystemReader",
    "WorkspaceReader",
    "UserRequestReader",
]
