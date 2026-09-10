"""Single source of truth for per-user GitHub credentials.

Phase 1 professional wiring:
  UI / provider / bind_repo / clone  →  resolve_github_credentials(user_id)
                                    →  PAT decrypt  OR  App installation token

Never call token_store.load_github_token for product paths when App installs
exist — that helper is PAT-only. This module is the only resolver.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("lumen.connections.credentials")


@dataclass(frozen=True)
class GitHubCredentials:
    """Resolved short-lived or durable credential for API/git use."""

    token: str
    auth_kind: str  # "pat" | "github_app"
    user_id: int
    login: str = ""
    installation_id: str = ""
    account_type: str = ""
    repo_selection: str = ""
    source: str = ""  # mongo|redis|session|minted

    @property
    def connected(self) -> bool:
        return bool(self.token) and self.auth_kind in {"pat", "github_app"}

    def public_dict(self) -> dict[str, Any]:
        """Safe for logs / UI — never includes the token."""
        return {
            "auth_kind": self.auth_kind,
            "login": self.login,
            "installation_id": self.installation_id,
            "account_type": self.account_type,
            "repo_selection": self.repo_selection,
            "source": self.source,
            "connected": self.connected,
            "token_present": bool(self.token),
        }


def _profile_for(user_id: int) -> dict[str, Any]:
    uid = int(user_id or 0)
    if uid <= 0:
        return {}
    # Prefer durable store (Mongo + Redis + session)
    try:
        from lumen.bot.ui.github_connection_store import read_github_profile

        prof = read_github_profile(uid)
        if isinstance(prof, dict) and prof.get("connected"):
            return dict(prof)
    except Exception:
        logger.debug("read_github_profile failed uid=%s", uid, exc_info=True)
    try:
        from lumen.engine.services.integrations.connections import token_store as ts

        prof = ts.load_connection_profile(uid)
        if isinstance(prof, dict) and prof.get("connected"):
            return dict(prof)
    except Exception:
        logger.debug("load_connection_profile failed uid=%s", uid, exc_info=True)
    return {}


def is_github_connected(user_id: int) -> bool:
    """True when a durable connection record exists (App install or PAT).

    Does not mint tokens — cheap check for UI badges.
    """
    uid = int(user_id or 0)
    if uid <= 0:
        return False
    prof = _profile_for(uid)
    if not prof or not prof.get("connected"):
        return False
    auth_kind = str(prof.get("auth_kind") or "").strip().lower()
    if auth_kind == "github_app":
        return bool(str(prof.get("installation_id") or "").strip())
    if auth_kind == "pat":
        return True
    # Legacy records without auth_kind: connected flag + (token or install)
    if str(prof.get("installation_id") or "").strip():
        return True
    try:
        from lumen.engine.services.integrations.connections import token_store as ts

        return bool(ts.load_github_token(uid))
    except Exception:
        return False


def resolve_github_credentials(user_id: int) -> GitHubCredentials | None:
    """Resolve a usable Bearer token for this Telegram user.

    Order:
      1. auth_kind=github_app + installation_id → mint/cache installation token
      2. PAT from github_connection_store / token_store
    """
    uid = int(user_id or 0)
    if uid <= 0:
        return None

    prof = _profile_for(uid)
    auth_kind = str(prof.get("auth_kind") or "").strip().lower()
    installation_id = str(prof.get("installation_id") or "").strip()
    login = str(prof.get("account_login") or prof.get("login") or "").strip()

    # --- GitHub App path ---
    if auth_kind == "github_app" or (installation_id and auth_kind != "pat"):
        if not installation_id:
            logger.warning("github_app profile missing installation_id uid=%s", uid)
            return None
        try:
            from lumen.engine.services.integrations.github.app_auth import (
                get_installation_token,
            )

            token = get_installation_token(installation_id)
        except Exception:
            logger.exception(
                "resolve credentials: installation token failed uid=%s install=%s",
                uid,
                installation_id,
            )
            return None
        if not token:
            return None
        return GitHubCredentials(
            token=token,
            auth_kind="github_app",
            user_id=uid,
            login=login,
            installation_id=installation_id,
            account_type=str(prof.get("account_type") or ""),
            repo_selection=str(prof.get("repo_selection") or ""),
            source="app_mint",
        )

    # --- PAT path (legacy + explicit) ---
    token: str | None = None
    source = "pat"
    try:
        from lumen.engine.services.integrations.connections import token_store as ts

        token = ts.load_github_token(uid)
        source = "redis_pat"
        if not token:
            token = _read_pat_from_mongo_only(uid)
            source = "mongo_pat" if token else source
    except Exception:
        logger.debug("PAT resolve failed uid=%s", uid, exc_info=True)
        token = None

    if not token:
        return None
    return GitHubCredentials(
        token=token,
        auth_kind="pat",
        user_id=uid,
        login=login,
        installation_id="",
        account_type=str(prof.get("account_type") or "user"),
        repo_selection="",
        source=source,
    )


def _read_pat_from_mongo_only(user_id: int) -> str | None:
    """Decrypt PAT ciphertext from Mongo without App minting side effects."""
    try:
        from lumen.bot.ui import github_connection_store as gcs

        rec = gcs._load_raw_connection_record(int(user_id))  # noqa: SLF001
        if not isinstance(rec, dict):
            return None
        if str(rec.get("auth_kind") or "").lower() == "github_app":
            return None
        cipher = str(rec.get("ciphertext") or "")
        if not cipher:
            return None
        return gcs._decrypt_token(int(user_id), cipher)  # noqa: SLF001
    except Exception:
        logger.debug("mongo PAT-only read failed uid=%s", user_id, exc_info=True)
        return None


def resolve_github_token(user_id: int) -> str | None:
    """Convenience: token string only (clone / GitHubClient)."""
    creds = resolve_github_credentials(user_id)
    return creds.token if creds else None


def github_client_for_user(user_id: int):
    """GitHubClient for this Telegram user (no platform token fallback)."""
    from lumen.engine.services.integrations.github.client import client_for_user

    return client_for_user(int(user_id))


__all__ = [
    "GitHubCredentials",
    "is_github_connected",
    "resolve_github_credentials",
    "resolve_github_token",
    "github_client_for_user",
]
