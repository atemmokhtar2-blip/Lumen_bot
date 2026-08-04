"""Tolerant data readers for Service Management (Spec 061)."""

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


class SecurityReader(_BaseReader):
    ARTEFACT_KEY = "security_permission_report"
    LIST_KEY = "roles"


class ConfigReader(_BaseReader):
    ARTEFACT_KEY = "configuration_management_report"
    LIST_KEY = "entries"


class MonitoringReader(_BaseReader):
    ARTEFACT_KEY = "system_monitoring_report"
    LIST_KEY = "engine_statuses"


class ResourceReader(_BaseReader):
    ARTEFACT_KEY = "resource_management_report"
    LIST_KEY = "quotas"


class ExecutionContextReader(_BaseReader):
    ARTEFACT_KEY = "execution_context_report"
    LIST_KEY = "shared_keys"


class EcosystemReader(_BaseReader):
    ARTEFACT_KEY = "engine_ecosystem_report"
    LIST_KEY = "manifests"


class UserRequestReader(_BaseReader):
    ARTEFACT_KEY = "user_request"
    LIST_KEY = "services"

    def read(self, ctx: GenerationContext) -> GenericData:
        d = GenericData()
        try:
            a = ctx.get(self.ARTEFACT_KEY)
            if a is None:
                a = ctx.get("service_request")
            if a is None:
                d.error = "missing user_request"
                return d
            raw = _safe(a)
            d.raw, d.available = raw, True
            services = raw.get("services") or raw.get("engines") or []
            if isinstance(services, list):
                d.items = services
            elif services:
                d.items = [services]
        except Exception as e:
            d.error = str(e)
        return d


__all__ = [
    "GenericData",
    "SecurityReader",
    "ConfigReader",
    "MonitoringReader",
    "ResourceReader",
    "ExecutionContextReader",
    "EcosystemReader",
    "UserRequestReader",
]
