"""GitHub connection — official api.github.com via GitHubClient + durable token store."""
from __future__ import annotations

import logging

from .base import ConnectionResource, ConnectionStatus
from . import token_store

logger = logging.getLogger("lumen.connections.github")

PROVIDER_ID = "github"
LABEL_AR = "GitHub"


def _token_for_user(user_id: int) -> str | None:
    """Resolve via credentials only (App install token or PAT). Never PAT-store alone."""
    try:
        from lumen.engine.services.integrations.connections.credentials import (
            resolve_github_token,
        )

        return resolve_github_token(int(user_id))
    except Exception:
        logger.debug("credentials resolve failed uid=%s", user_id, exc_info=True)
        return None


class GitHubConnectionProvider:
    provider_id = PROVIDER_ID
    label_ar = LABEL_AR

    def status(self, user_id: int) -> ConnectionStatus:
        uid = int(user_id or 0)
        if uid <= 0:
            return ConnectionStatus(PROVIDER_ID, False, detail="invalid_user")
        try:
            from lumen.bot.ui.github_connection_store import read_github_profile

            profile = read_github_profile(uid) or token_store.load_connection_profile(uid) or {}
        except Exception:
            profile = token_store.load_connection_profile(uid) or {}
        auth_kind = str(profile.get("auth_kind") or "").strip().lower()
        installation_id = str(profile.get("installation_id") or "").strip()

        # GitHub App install: durable profile is enough; mint token only when needed.
        if auth_kind == "github_app" and installation_id:
            login = str(
                profile.get("account_login") or profile.get("login") or ""
            ).strip()
            if not login:
                try:
                    from lumen.engine.services.integrations.github.app_auth import (
                        get_installation,
                    )

                    inst = get_installation(installation_id)
                    account = inst.get("account") or {}
                    login = str(account.get("login") or "").strip()
                    if login:
                        token_store.save_connection_profile(
                            uid,
                            {
                                **profile,
                                "login": login,
                                "account_login": login,
                                "account_type": str(account.get("type") or ""),
                                "connected": True,
                                "auth_kind": "github_app",
                                "installation_id": installation_id,
                                "repo_selection": str(inst.get("repository_selection") or ""),
                            },
                        )
                except Exception as exc:
                    logger.info(
                        "github app status enrich failed uid=%s err=%s",
                        uid,
                        type(exc).__name__,
                    )
            return ConnectionStatus(
                PROVIDER_ID,
                True,
                display_name=login or "GitHub App",
                detail="github_app",
            )

        token = _token_for_user(uid)
        if not token:
            # Profile alone is not enough without token — force reconnect
            return ConnectionStatus(PROVIDER_ID, False, detail="not_connected")
        try:
            from lumen.engine.services.integrations.github.client import GitHubClient

            user = GitHubClient(token=token).get_user()
            login = str(user.get("login") or profile.get("login") or "").strip()
            token_store.save_connection_profile(
                uid,
                {
                    "login": login,
                    "connected": True,
                    "provider": "github",
                    "auth_kind": "pat",
                },
            )
            return ConnectionStatus(
                PROVIDER_ID,
                True,
                display_name=login or "GitHub",
                detail="ok",
            )
        except Exception as exc:
            # Transient API failure: stay connected using durable profile + token presence
            logger.info("github status check failed uid=%s err=%s", uid, type(exc).__name__)
            login = str(profile.get("login") or "").strip()
            return ConnectionStatus(
                PROVIDER_ID,
                True,
                display_name=login or "GitHub",
                detail=f"cached:{type(exc).__name__}",
            )

    def list_resources(
        self, user_id: int, *, page: int = 1, per_page: int = 10, prefer_cache: bool = False
    ) -> list[ConnectionResource]:
        uid = int(user_id or 0)
        if prefer_cache:
            cache = token_store.load_repo_cache(uid)
            if cache and int(cache.get("page") or 1) == max(1, int(page)):
                out: list[ConnectionResource] = []
                for item in (cache.get("items") or [])[:per_page]:
                    rid = str(item.get("resource_id") or "")
                    if not rid:
                        continue
                    full = str(item.get("full_name") or rid)
                    priv = bool(item.get("private"))
                    lock = "🔒 " if priv else ""
                    out.append(
                        ConnectionResource(
                            resource_id=rid,
                            title=f"{lock}{full}"[:60],
                            url=str(item.get("html_url") or ""),
                            private=priv,
                            meta={
                                "full_name": full,
                                "default_branch": item.get("default_branch") or "main",
                                "html_url": item.get("html_url") or "",
                                "private": priv,
                                "from_cache": True,
                            },
                        )
                    )
                if out:
                    return out
        page = max(1, int(page))
        per_page = max(1, min(30, int(per_page)))
        try:
            try:
                from lumen.bot.ui.github_connection_store import read_github_profile

                profile = (
                    read_github_profile(uid)
                    or token_store.load_connection_profile(uid)
                    or {}
                )
            except Exception:
                profile = token_store.load_connection_profile(uid) or {}
            auth_kind = str(profile.get("auth_kind") or "").strip().lower()
            installation_id = str(profile.get("installation_id") or "").strip()
            if auth_kind == "github_app" and installation_id:
                from lumen.engine.services.integrations.github.app_auth import (
                    list_installation_repos,
                )

                rows = list_installation_repos(
                    installation_id, page=page, per_page=per_page
                )
            else:
                token = _token_for_user(uid)
                if not token:
                    return []
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
    """Persist PAT after successful official API verification.

    MongoDB is the durable source of truth (deploy-safe); Redis is the cache.
    """
    try:
        from lumen.bot.ui.github_connection_store import write_github_connection

        return write_github_connection(int(user_id), token, login=login or "")
    except Exception:
        return token_store.save_github_token(
            int(user_id),
            token,
            meta={"login": (login or "")[:80], "provider": "github"},
        )
