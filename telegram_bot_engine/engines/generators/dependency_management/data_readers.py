"""Tolerant data readers for Dependency Management (Spec 050)."""

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


class WorkspaceReader(_BaseReader):
    ARTEFACT_KEY = "workspace_management_report"
    LIST_KEY = "workspaces"


class FileSystemReader(_BaseReader):
    ARTEFACT_KEY = "file_system_report"
    LIST_KEY = "operations"


class ProjectContextReader(_BaseReader):
    ARTEFACT_KEY = "project_context_report"
    LIST_KEY = "contexts"


class ArchitectureReader(_BaseReader):
    ARTEFACT_KEY = "architecture_compliance_report"
    LIST_KEY = "violations"


class UserRequestReader(_BaseReader):
    ARTEFACT_KEY = "user_request"
    LIST_KEY = "dependencies"

    def read(self, ctx: GenerationContext) -> GenericData:
        d = GenericData()
        try:
            a = ctx.get(self.ARTEFACT_KEY)
            if a is None:
                a = ctx.get("dependency_request") or ctx.get("package_request")
            if a is None:
                d.error = "missing user_request"
                return d
            raw = _safe(a)
            d.raw, d.available = raw, True
            deps = raw.get("dependencies") or raw.get("packages") or []
            if isinstance(deps, list):
                d.items = deps
            elif deps:
                d.items = [deps]
        except Exception as e:
            d.error = str(e)
        return d


__all__ = [
    "GenericData",
    "WorkspaceReader",
    "FileSystemReader",
    "ProjectContextReader",
    "ArchitectureReader",
    "UserRequestReader",
]
