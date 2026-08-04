"""Tolerant data readers for Configuration Management (Spec 059)."""

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


class LoggingReader(_BaseReader):
    ARTEFACT_KEY = "central_logging_report"
    LIST_KEY = "entries"


class MonitoringReader(_BaseReader):
    ARTEFACT_KEY = "system_monitoring_report"
    LIST_KEY = "metrics"


class ResourceReader(_BaseReader):
    ARTEFACT_KEY = "resource_management_report"
    LIST_KEY = "quotas"


class EnvironmentReader(_BaseReader):
    ARTEFACT_KEY = "environment_config_report"
    LIST_KEY = "variables"


class WorkspaceReader(_BaseReader):
    ARTEFACT_KEY = "workspace_management_report"
    LIST_KEY = "workspaces"


class UserRequestReader(_BaseReader):
    ARTEFACT_KEY = "user_request"
    LIST_KEY = "config"

    def read(self, ctx: GenerationContext) -> GenericData:
        d = GenericData()
        try:
            a = ctx.get(self.ARTEFACT_KEY)
            if a is None:
                a = ctx.get("config_request")
            if a is None:
                d.error = "missing user_request"
                return d
            raw = _safe(a)
            d.raw, d.available = raw, True
            cfg = raw.get("config") or raw.get("settings") or raw.get("entries") or []
            if isinstance(cfg, list):
                d.items = cfg
            elif isinstance(cfg, dict):
                d.items = [{"key": k, "value": v} for k, v in cfg.items()]
            elif cfg:
                d.items = [cfg]
        except Exception as e:
            d.error = str(e)
        return d


__all__ = [
    "GenericData",
    "LoggingReader",
    "MonitoringReader",
    "ResourceReader",
    "EnvironmentReader",
    "WorkspaceReader",
    "UserRequestReader",
]
