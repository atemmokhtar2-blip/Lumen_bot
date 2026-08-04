"""Tolerant data readers for Security & Permission (Spec 060)."""

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
                lst = raw.get(self.LIST_KEY)
                if isinstance(lst, list):
                    d.items = lst
        except Exception as e:
            d.error = str(e)
        return d


class ConfigReader(_BaseReader):
    ARTEFACT_KEY = "configuration_management_report"
    LIST_KEY = "entries"


class LoggingReader(_BaseReader):
    ARTEFACT_KEY = "central_logging_report"
    LIST_KEY = "entries"


class MonitoringReader(_BaseReader):
    ARTEFACT_KEY = "system_monitoring_report"
    LIST_KEY = "engine_statuses"


class ExecutionContextReader(_BaseReader):
    ARTEFACT_KEY = "execution_context_report"
    LIST_KEY = "shared_keys"


class WorkspaceReader(_BaseReader):
    ARTEFACT_KEY = "workspace_management_report"
    LIST_KEY = "workspaces"


class EcosystemReader(_BaseReader):
    ARTEFACT_KEY = "engine_ecosystem_report"
    LIST_KEY = "manifests"


class UserRequestReader(_BaseReader):
    ARTEFACT_KEY = "user_request"
    LIST_KEY = "engines"

    def read(self, ctx: GenerationContext) -> GenericData:
        d = GenericData()
        try:
            a = ctx.get(self.ARTEFACT_KEY)
            if a is None:
                a = ctx.get("security_request")
            if a is None:
                d.error = "missing user_request"
                return d
            raw = _safe(a)
            d.raw, d.available = raw, True
            engines = raw.get("engines") or raw.get("roles") or []
            if isinstance(engines, list):
                d.items = engines
            elif engines:
                d.items = [engines]
        except Exception as e:
            d.error = str(e)
        return d


__all__ = [
    "GenericData",
    "ConfigReader",
    "LoggingReader",
    "MonitoringReader",
    "ExecutionContextReader",
    "WorkspaceReader",
    "EcosystemReader",
    "UserRequestReader",
]
