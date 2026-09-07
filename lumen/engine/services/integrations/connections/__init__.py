"""Extensible account connections (GitHub first; more providers later)."""
from __future__ import annotations

from .base import ConnectionProvider, ConnectionResource, ConnectionStatus
from .github_provider import GitHubConnectionProvider
from .bind_repo import BindRepoResult, bind_github_repo
from .registry import get_provider, list_providers

__all__ = [
    "ConnectionProvider",
    "ConnectionResource",
    "ConnectionStatus",
    "GitHubConnectionProvider",
    "BindRepoResult",
    "bind_github_repo",
    "get_provider",
    "list_providers",
]
