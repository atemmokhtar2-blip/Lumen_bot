"""Tolerant data readers for Message Queue (Spec 062)."""

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


class ServiceReader(_BaseReader):
    ARTEFACT_KEY = "service_management_report"
    LIST_KEY = "services"


class SecurityReader(_BaseReader):
    ARTEFACT_KEY = "security_permission_report"
    LIST_KEY = "roles"


class MonitoringReader(_BaseReader):
    ARTEFACT_KEY = "system_monitoring_report"
    LIST_KEY = "engine_statuses"


class OrchestratorReader(_BaseReader):
    ARTEFACT_KEY = "engine_orchestrator_report"
    LIST_KEY = "plan"


class ExecutionContextReader(_BaseReader):
    ARTEFACT_KEY = "execution_context_report"
    LIST_KEY = "shared_keys"


class UserRequestReader(_BaseReader):
    ARTEFACT_KEY = "user_request"
    LIST_KEY = "messages"

    def read(self, ctx: GenerationContext) -> GenericData:
        d = GenericData()
        try:
            a = ctx.get(self.ARTEFACT_KEY)
            if a is None:
                a = ctx.get("queue_request")
            if a is None:
                d.error = "missing user_request"
                return d
            raw = _safe(a)
            d.raw, d.available = raw, True
            msgs = raw.get("messages") or raw.get("events") or raw.get("tasks") or []
            if isinstance(msgs, list):
                d.items = msgs
            elif msgs:
                d.items = [msgs]
        except Exception as e:
            d.error = str(e)
        return d


__all__ = [
    "GenericData",
    "ServiceReader",
    "SecurityReader",
    "MonitoringReader",
    "OrchestratorReader",
    "ExecutionContextReader",
    "UserRequestReader",
]
