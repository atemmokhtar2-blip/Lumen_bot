"""Webhook manager — product control plane for hosted-bot Telegram webhooks.

Responsibilities:
  - Build stable webhook URL per instance
  - Register / clear Telegram setWebhook
  - Enqueue inbound updates (Redis) for guest/sidecar consumers
  - Optional secret rotation metadata on instance diagnosis

Gateway path (API):
  POST /v1/hooks/telegram/{instance_id}  →  lumen.api.routes.host_webhooks
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import time
from typing import Any

logger = logging.getLogger("tbe.hosting.webhook_manager")


def webhook_url_for(instance_id: str) -> str:
    api_base = (os.environ.get("TBE_PUBLIC_API_BASE") or "").rstrip("/")
    if api_base.startswith("https://"):
        return f"{api_base}/v1/hooks/telegram/{instance_id}"
    domain = (os.environ.get("TBE_HOST_BASE_DOMAIN") or "").strip().lstrip(".")
    scheme = (os.environ.get("TBE_PUBLIC_URL_SCHEME") or "https").strip() or "https"
    if domain:
        return f"{scheme}://{instance_id}.{domain}/v1/hooks/telegram/{instance_id}"
    return ""


def queue_key(instance_id: str) -> str:
    return f"lumen:host:tgq:{instance_id}"


def mode() -> str:
    return (os.environ.get("TBE_HOST_WEBHOOK_MODE") or "auto").strip().lower()


def should_register(webhook_url: str) -> bool:
    m = mode()
    if m in {"0", "false", "no", "off", "polling"}:
        return False
    if m in {"1", "true", "yes", "on", "webhook"}:
        return bool(webhook_url.startswith("https://"))
    # auto
    return bool(webhook_url.startswith("https://"))


def ensure_secret(inst_diagnosis: dict | None = None) -> str:
    diag = dict(inst_diagnosis or {})
    existing = str(diag.get("webhook_secret") or "").strip()
    if existing:
        return existing
    global_secret = (os.environ.get("TBE_HOST_WEBHOOK_SECRET") or "").strip()
    if global_secret:
        return global_secret
    return secrets.token_urlsafe(24)


def register_webhook(bot_token: str, webhook_url: str, *, secret: str = "") -> dict[str, Any]:
    if not bot_token or not webhook_url.startswith("https://"):
        return {"ok": False, "error": "invalid_args"}
    try:
        from lumen.bot.singleton import set_telegram_webhook

        ok = set_telegram_webhook(bot_token, webhook_url, secret_token=secret or None)
        return {"ok": bool(ok), "url": webhook_url, "registered_at": time.time()}
    except Exception as exc:
        logger.warning("register_webhook failed: %s", type(exc).__name__)
        return {"ok": False, "error": type(exc).__name__}


def clear_webhook(bot_token: str) -> dict[str, Any]:
    if not bot_token:
        return {"ok": False, "error": "no_token"}
    try:
        from lumen.bot.singleton import clear_telegram_webhook

        ok = clear_telegram_webhook(bot_token)
        return {"ok": bool(ok)}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__}


def enqueue_update(instance_id: str, update: dict[str, Any]) -> bool:
    try:
        from lumen.engine.services.hosting.redis_state import _client

        r = _client()
        if r is None:
            return False
        key = queue_key(instance_id)
        r.lpush(key, json.dumps(update, ensure_ascii=False))
        r.ltrim(key, 0, 99)
        r.expire(key, 3600)
        return True
    except Exception:
        logger.exception("enqueue_update failed instance=%s", instance_id)
        return False


def apply_to_instance(
    *,
    instance_id: str,
    bot_token: str,
    inst: Any,
) -> dict[str, Any]:
    """Fill webhook fields on HostInstance and register with Telegram when appropriate."""
    url = webhook_url_for(instance_id)
    inst.webhook_public_url = url
    diag = dict(getattr(inst, "last_diagnosis", None) or {})
    secret = ensure_secret(diag)
    diag["webhook_secret"] = secret
    result: dict[str, Any] = {"url": url, "registered": False}
    if should_register(url) and str(getattr(inst, "status", "") or "") == "running":
        reg = register_webhook(bot_token, url, secret=secret)
        result["registered"] = bool(reg.get("ok"))
        diag["webhook_registered"] = bool(reg.get("ok"))
        diag["webhook_url"] = url
        if not reg.get("ok"):
            diag["webhook_error"] = str(reg.get("error") or "register_failed")
    elif mode() in {"0", "false", "no", "off", "polling"}:
        clear_webhook(bot_token)
        diag["webhook_mode"] = "polling"
    inst.last_diagnosis = diag
    return result


__all__ = [
    "webhook_url_for",
    "queue_key",
    "mode",
    "should_register",
    "ensure_secret",
    "register_webhook",
    "clear_webhook",
    "enqueue_update",
    "apply_to_instance",
]
