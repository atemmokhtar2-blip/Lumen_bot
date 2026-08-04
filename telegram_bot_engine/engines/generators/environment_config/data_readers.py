"""Tolerant data readers for Environment Configuration (Spec 051)."""

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


class DependencyReader(_BaseReader):
    ARTEFACT_KEY = "dependency_management_report"
    LIST_KEY = "dependencies"


class WorkspaceReader(_BaseReader):
    ARTEFACT_KEY = "workspace_management_report"
    LIST_KEY = "workspaces"


class FileSystemReader(_BaseReader):
    ARTEFACT_KEY = "file_system_report"
    LIST_KEY = "operations"


class ProjectContextReader(_BaseReader):
    ARTEFACT_KEY = "project_context_report"
    LIST_KEY = "contexts"


class UserRequestReader(_BaseReader):
    ARTEFACT_KEY = "user_request"
    LIST_KEY = "variables"

    def read(self, ctx: GenerationContext) -> GenericData:
        d = GenericData()
        try:
            a = ctx.get(self.ARTEFACT_KEY)
            if a is None:
                a = ctx.get("environment_request") or ctx.get("config_request")
            if a is None:
                d.error = "missing user_request"
                return d
            raw = _safe(a)
            d.raw, d.available = raw, True
            vars_ = raw.get("variables") or raw.get("env_vars") or raw.get("config") or []
            if isinstance(vars_, list):
                d.items = vars_
            elif isinstance(vars_, dict):
                d.items = [{"name": k, "value": v} for k, v in vars_.items()]
            elif vars_:
                d.items = [vars_]
        except Exception as e:
            d.error = str(e)
        return d


__all__ = [
    "GenericData",
    "DependencyReader",
    "WorkspaceReader",
    "FileSystemReader",
    "ProjectContextReader",
    "UserRequestReader",
]
