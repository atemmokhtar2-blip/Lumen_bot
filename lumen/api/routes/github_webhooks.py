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
    return (os.getenv("GITHUB_WEBHOOK_SECRET") or "").strip()


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

    # Optional: trigger multi-agent resume / analysis hook for PR opened
    if event == "pull_request" and action in {"opened", "synchronize", "reopened"}:
        try:
            from lumen.engine.services.integrations.github.client import list_pull_files, get_pull
            pr = payload.get("pull_request") or {}
            number = int(pr.get("number") or 0)
            full = str(repo)
            if "/" in full and number and (os.getenv("GITHUB_TOKEN") or "").strip():
                owner, name = full.split("/", 1)
                files = list_pull_files(owner, name, number)
                logger.info("github pr %s#%s files=%s", full, number, len(files or []))
                emit(
                    "github.pr.files",
                    {"repo": full, "number": number, "files": [f.get("filename") for f in (files or [])[:50]]},
                    source="github_webhook",
                )
        except Exception:
            logger.exception("github pr follow-up failed")

    return web.json_response({"ok": True, "event": event_name, "delivery": delivery})


__all__ = ["github_webhook", "verify_signature"]
