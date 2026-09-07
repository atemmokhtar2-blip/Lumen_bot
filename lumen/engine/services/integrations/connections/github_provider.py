"""GitHub connection — official api.github.com via GitHubClient + durable token store."""
from __future__ import annotations

import logging

from .base import ConnectionResource, ConnectionStatus
from . import token_store

logger = logging.getLogger("lumen.connections.github")

PROVIDER_ID = "github"
LABEL_AR = "GitHub"


def _token_for_user(user_id: int) -> str | None:
    return token_store.load_github_token(int(user_id))


class GitHubConnectionProvider:
    provider_id = PROVIDER_ID
    label_ar = LABEL_AR

    def status(self, user_id: int) -> ConnectionStatus:
        uid = int(user_id or 0)
        if uid <= 0:
            return ConnectionStatus(PROVIDER_ID, False, detail="invalid_user")
        token = _token_for_user(uid)
        if not token:
            return ConnectionStatus(PROVIDER_ID, False, detail="not_connected")
        try:
            from lumen.engine.services.integrations.github.client import GitHubClient

            user = GitHubClient(token=token).get_user()
            login = str(user.get("login") or "").strip()
            return ConnectionStatus(
                PROVIDER_ID,
                True,
                display_name=login or "GitHub",
                detail="ok",
            )
        except Exception as exc:
            logger.info("github status check failed uid=%s err=%s", uid, type(exc).__name__)
            return ConnectionStatus(
                PROVIDER_ID,
                False,
                detail=f"auth_failed:{type(exc).__name__}",
            )

    def list_resources(
        self, user_id: int, *, page: int = 1, per_page: int = 10
    ) -> list[ConnectionResource]:
        uid = int(user_id or 0)
        token = _token_for_user(uid)
        if not token:
            return []
        page = max(1, int(page))
        per_page = max(1, min(30, int(per_page)))
        try:
            from lumen.engine.services.integrations.github.client import GitHubClient

            client = GitHubClient(token=token)
            # Official page parameter from GitHub API
            rows = client.list_user_repos(page=page, per_page=per_page, max_pages=1)
            out: list[ConnectionResource] = []
            cache_items: list[dict] = []
            for row in rows:
                rid = str(row.get("id") or "")
                if not rid:
                    continue
                full = str(row.get("full_name") or row.get("name") or rid)
                priv = bool(row.get("private"))
                lock = "🔒 " if priv else ""
                title = f"{lock}{full}"[:60]
                meta = {
                    "full_name": full,
                    "default_branch": row.get("default_branch") or "main",
                    "language": row.get("language") or "",
                    "html_url": row.get("html_url") or "",
                    "private": priv,
                }
                out.append(
                    ConnectionResource(
                        resource_id=rid,
                        title=title,
                        url=str(row.get("html_url") or ""),
                        private=priv,
                        meta=meta,
                    )
                )
                cache_items.append(
                    {
                        "resource_id": rid,
                        "full_name": full,
                        "html_url": meta["html_url"],
                        "default_branch": meta["default_branch"],
                        "private": priv,
                    }
                )
            token_store.cache_repo_page(uid, page, cache_items)
            return out
        except Exception:
            logger.exception("list_user_repos failed uid=%s", uid)
            return []


def store_github_connection_token(user_id: int, token: str, *, login: str = "") -> bool:
    """Persist PAT after successful official API verification."""
    return token_store.save_github_token(
        int(user_id),
        token,
        meta={"login": (login or "")[:80], "provider": "github"},
    )
