"""Extensible account connections (GitHub first; more providers later)."""
from __future__ import annotations

from .base import ConnectionProvider, ConnectionResource, ConnectionStatus
from .github_provider import GitHubConnectionProvider
from .bind_repo import BindRepoResult, apply_bind_to_user_data, bind_github_repo
from .readiness import ReadinessResult, evaluate_readiness, missing_env_from_contract
from .registry import get_provider, list_providers
from .credentials import (
    GitHubCredentials,
    is_github_connected,
    resolve_github_credentials,
    resolve_github_token,
    github_client_for_user,
)

__all__ = [
    "ConnectionProvider",
    "ConnectionResource",
    "ConnectionStatus",
    "GitHubConnectionProvider",
    "BindRepoResult",
    "apply_bind_to_user_data",
    "bind_github_repo",
    "ReadinessResult",
    "evaluate_readiness",
    "missing_env_from_contract",
    "get_provider",
    "list_providers",
    "GitHubCredentials",
    "is_github_connected",
    "resolve_github_credentials",
    "resolve_github_token",
    "github_client_for_user",
]
