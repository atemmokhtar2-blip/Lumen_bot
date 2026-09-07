"""GitHub connection — official api.github.com via GitHubClient."""
from __future__ import annotations

import logging

from .base import ConnectionResource, ConnectionStatus

logger = logging.getLogger("lumen.connections.github")

PROVIDER_ID = "github"
LABEL_AR = "GitHub"


def _token_for_user(user_id: int) -> str | None:
    """Resolve user PAT without consuming (connection must stay usable)."""
    try:
        from lumen.platform.secret_inbox import get_secret

        tok = get_secret(user_id=int(user_id), kind="github")
        if tok:
            return tok.strip()
    except Exception:
        logger.debug("get_secret github failed uid=%s", user_id, exc_info=True)
    return None


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
            all_repos = client.list_user_repos(per_page=30, max_pages=max(page, 3))
            start = (page - 1) * per_page
            end = start + per_page
            chunk = all_repos[start:end]
            out: list[ConnectionResource] = []
            for row in chunk:
                rid = str(row.get("id") or "")
                if not rid:
                    continue
                full = str(row.get("full_name") or row.get("name") or rid)
                priv = bool(row.get("private"))
                lock = "🔒 " if priv else ""
                title = f"{lock}{full}"[:60]
                out.append(
                    ConnectionResource(
                        resource_id=rid,
                        title=title,
                        url=str(row.get("html_url") or ""),
                        private=priv,
                        meta={
                            "full_name": full,
                            "default_branch": row.get("default_branch") or "main",
                            "language": row.get("language") or "",
                            "html_url": row.get("html_url") or "",
                        },
                    )
                )
            return out
        except Exception:
            logger.exception("list_user_repos failed uid=%s", uid)
            return []


def store_github_connection_token(user_id: int, token: str) -> bool:
    """Persist PAT for connection use (long TTL, encrypted secret_inbox)."""
    try:
        from lumen.platform.secret_inbox import put_secret

        return bool(
            put_secret(
                user_id=int(user_id),
                kind="github",
                plaintext=token.strip(),
                purpose="connection",
                ttl_sec=30 * 24 * 3600,
                meta={"provider": "github"},
            )
        )
    except Exception:
        logger.exception("store_github_connection_token failed")
        return False
