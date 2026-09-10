"""GitHub webhooks — official X-Hub-Signature-256 verification + event bus.

Env:
  GITHUB_WEBHOOK_SECRET — required to accept events
  GITHUB_TOKEN — optional for follow-up API calls
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os

from aiohttp import web

logger = logging.getLogger(__name__)


def _secret() -> str:
    try:
        from lumen.platform.secrets_provider import get_secret
        v = (get_secret("GITHUB_WEBHOOK_SECRET", "") or get_secret("GITHUB_APP_WEBHOOK_SECRET", "") or "").strip()
        if v:
            return v
    except Exception:
        pass
    return (os.getenv("GITHUB_WEBHOOK_SECRET") or os.getenv("GITHUB_APP_WEBHOOK_SECRET") or "").strip()


def verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    secret = _secret()
    if not secret:
        return False
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = signature_header.split("=", 1)[1].strip()
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, expected)


async def github_webhook(request: web.Request) -> web.Response:
    """POST /v1/integrations/github/webhook"""
    raw = await request.read()
    sig = request.headers.get("X-Hub-Signature-256") or request.headers.get("X-Hub-Signature")
    if not _secret():
        return web.json_response({"ok": False, "error": "GITHUB_WEBHOOK_SECRET not set"}, status=503)
    if not verify_signature(raw, sig):
        logger.warning("github webhook signature failed")
        try:
            from lumen.platform.security_events import emit, client_ip
            emit(
                "webhook.github_signature_failed",
                severity="critical",
                ip=client_ip(request),
                path=str(request.path),
                detail={"has_signature": bool(sig)},
            )
        except Exception:
            pass
        return web.json_response({"ok": False, "error": "invalid_signature"}, status=401)

    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        return web.json_response({"ok": False, "error": "invalid_json"}, status=400)

    event = (request.headers.get("X-GitHub-Event") or "unknown").strip()
    action = str(payload.get("action") or "")
    repo = (payload.get("repository") or {}).get("full_name") or ""
    delivery = request.headers.get("X-GitHub-Delivery") or ""

    event_name = f"github.{event}"
    if action:
        event_name = f"github.{event}.{action}"

    try:
        from lumen.engine.services.events import emit
        emit(
            event_name,
            {
                "delivery": delivery,
                "event": event,
                "action": action,
                "repo": repo,
                "number": (payload.get("pull_request") or payload.get("issue") or {}).get("number"),
                "title": (payload.get("pull_request") or payload.get("issue") or {}).get("title"),
                "sender": (payload.get("sender") or {}).get("login"),
            },
            source="github_webhook",
        )
    except Exception:
        logger.exception("emit github event failed")

    # GitHub App lifecycle — keep Lumen bindings in sync with installations.
    install_sync = None
    if event in {"installation", "installation_repositories"}:
        try:
            install_sync = _handle_installation_event(event, action, payload)
        except Exception:
            logger.exception("github installation sync failed event=%s action=%s", event, action)

    # Direct PR agent (not emit-only): analysis + optional clone/hybrid + comment
    agent_result = None
    if event == "pull_request" and action in {"opened", "synchronize", "reopened"}:
        try:
            from lumen.engine.services.integrations.github.pr_agent import handle_pr_event
            pr = payload.get("pull_request") or {}
            agent_result = handle_pr_event({
                "name": event_name,
                "payload": {
                    "repo": repo,
                    "number": (pr.get("number") or payload.get("number")),
                    "action": action,
                    "title": pr.get("title"),
                },
            })
            logger.info("github pr_agent result=%s", {k: agent_result.get(k) for k in ("ok", "files", "comment_id", "job_id")})
        except Exception:
            logger.exception("github pr_agent failed")

    out = {"ok": True, "event": event_name, "delivery": delivery}
    if install_sync is not None:
        out["installation_sync"] = install_sync
    if agent_result is not None:
        out["agent"] = {
            "ok": agent_result.get("ok"),
            "files": agent_result.get("files"),
            "comment_id": agent_result.get("comment_id"),
            "job_id": agent_result.get("job_id"),
            "code_intel_ok": (agent_result.get("code_intel") or {}).get("ok"),
        }
    return web.json_response(out)


def _handle_installation_event(event: str, action: str, payload: dict) -> dict:
    """Map GitHub App installation webhooks to local connection state."""
    installation = payload.get("installation") or {}
    iid = installation.get("id")
    if not iid:
        return {"ok": False, "error": "missing_installation_id"}

    from lumen.engine.services.integrations.github.app_oauth_state import (
        clear_installation_index,
        lookup_user_for_installation,
    )
    from lumen.engine.services.integrations.github.app_auth import (
        clear_installation_token_cache,
    )

    uid = lookup_user_for_installation(iid)
    account = (installation.get("account") or {})
    login = str(account.get("login") or "")

    # Uninstall / suspend → drop local binding for that Telegram user
    if event == "installation" and action in {"deleted", "suspend"}:
        clear_installation_token_cache(iid)
        if uid:
            try:
                from lumen.bot.ui.github_connection_store import delete_github_connection

                delete_github_connection(int(uid))
            except Exception:
                logger.exception("delete connection on uninstall failed uid=%s", uid)
        clear_installation_index(iid, user_id=uid)
        logger.info(
            "github installation %s install=%s uid=%s login=%s",
            action,
            iid,
            uid,
            login or "—",
        )
        return {"ok": True, "action": action, "installation_id": str(iid), "uid": uid}

    # Repo selection changed under an existing install
    if event == "installation_repositories" and uid:
        try:
            from lumen.bot.ui.github_connection_store import (
                read_github_profile,
                write_github_app_connection,
            )

            prof = read_github_profile(int(uid)) or {}
            selection = str(
                (payload.get("repository_selection") or installation.get("repository_selection") or
                 prof.get("repo_selection") or "")
            )
            write_github_app_connection(
                int(uid),
                iid,
                login=str(prof.get("login") or login),
                account_login=str(prof.get("account_login") or login),
                account_type=str(prof.get("account_type") or account.get("type") or ""),
                repo_selection=selection,
            )
        except Exception:
            logger.exception("refresh repo_selection failed uid=%s install=%s", uid, iid)
            return {"ok": False, "error": "profile_refresh_failed", "uid": uid}
        return {"ok": True, "action": action, "installation_id": str(iid), "uid": uid}

    # New install without prior state (user installed from GitHub UI, not Telegram)
    if event == "installation" and action in {"created", "unsuspend"}:
        logger.info(
            "github installation %s install=%s login=%s (no telegram bind yet)",
            action,
            iid,
            login or "—",
        )
        return {"ok": True, "action": action, "installation_id": str(iid), "uid": uid}

    return {"ok": True, "action": action, "installation_id": str(iid), "uid": uid}


__all__ = ["github_webhook", "verify_signature"]
