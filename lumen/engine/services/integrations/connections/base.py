"""Connection provider contract — one interface for GitHub and future providers."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ConnectionStatus:
    provider_id: str
    connected: bool
    display_name: str = ""  # e.g. GitHub login
    detail: str = ""


@dataclass(frozen=True)
class ConnectionResource:
    """A selectable remote resource (repo, project, …)."""

    resource_id: str  # stable id for callbacks (str of GitHub repo id)
    title: str  # button label
    url: str = ""
    private: bool = False
    meta: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ConnectionProvider(Protocol):
    provider_id: str
    label_ar: str

    def status(self, user_id: int) -> ConnectionStatus: ...

    def list_resources(
        self, user_id: int, *, page: int = 1, per_page: int = 10
    ) -> list[ConnectionResource]: ...
