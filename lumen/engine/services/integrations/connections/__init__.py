"""Extensible account connections (GitHub first; more providers later)."""
from __future__ import annotations

from .base import ConnectionProvider, ConnectionResource, ConnectionStatus
from .github_provider import GitHubConnectionProvider
from .registry import get_provider, list_providers

__all__ = [
    "ConnectionProvider",
    "ConnectionResource",
    "ConnectionStatus",
    "GitHubConnectionProvider",
    "get_provider",
    "list_providers",
]
