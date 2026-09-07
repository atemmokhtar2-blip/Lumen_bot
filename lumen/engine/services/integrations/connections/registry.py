"""Provider registry — add new connections here without changing UI core."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import ConnectionProvider

_PROVIDERS: dict[str, "ConnectionProvider"] | None = None


def _build() -> dict[str, "ConnectionProvider"]:
    from .github_provider import GitHubConnectionProvider

    gh = GitHubConnectionProvider()
    return {gh.provider_id: gh}


def list_providers() -> list["ConnectionProvider"]:
    global _PROVIDERS
    if _PROVIDERS is None:
        _PROVIDERS = _build()
    return list(_PROVIDERS.values())


def get_provider(provider_id: str) -> "ConnectionProvider | None":
    global _PROVIDERS
    if _PROVIDERS is None:
        _PROVIDERS = _build()
    return _PROVIDERS.get((provider_id or "").strip().lower())
