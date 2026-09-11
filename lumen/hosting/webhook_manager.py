"""Webhook manager — product control plane for hosted-bot Telegram webhooks.

Responsibilities:
  - Build stable webhook URL per instance (API ingress OR serverless public URL)
  - Register / clear Telegram setWebhook (via serverless_verify for real API)
  - Enqueue inbound updates (Redis) for guest/sidecar consumers
  - Optional secret rotation metadata on instance diagnosis
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
    """Register webhook using the same real Telegram path as phase-3 verify."""
    if not bot_token or not str(webhook_url).startswith("https://"):
        return {"ok": False, "error": "invalid_args"}
    sec = (secret or "").strip()
    if not sec:
        return {"ok": False, "error": "secret_required"}
    try:
        from lumen.hosting.serverless_verify import set_webhook, get_webhook_info, urls_equivalent

        reg = set_webhook(bot_token, webhook_url, secret=sec, retries=3)
        if not reg.get("ok"):
            return {"ok": False, "error": reg.get("error") or "setWebhook_failed", "url": webhook_url}
        info = get_webhook_info(bot_token)
        if not info.get("ok"):
            return {
                "ok": False,
                "error": info.get("error") or "getWebhookInfo_failed",
                "url": webhook_url,
                "registered_at": time.time(),
            }
        if not urls_equivalent(str(info.get("url") or ""), webhook_url):
            return {
                "ok": False,
                "error": "webhook_url_mismatch",
                "url": webhook_url,
                "reported": str(info.get("url") or ""),
            }
        return {
            "ok": True,
            "url": webhook_url,
            "registered_at": time.time(),
            "verified": True,
            "pending_update_count": info.get("pending_update_count"),
        }
    except Exception as exc:
        logger.warning("register_webhook failed: %s", type(exc).__name__)
        return {"ok": False, "error": type(exc).__name__}


def clear_webhook(bot_token: str) -> dict[str, Any]:
    if not bot_token:
        return {"ok": False, "error": "no_token"}
    try:
        from lumen.hosting.serverless_verify import delete_webhook

        return delete_webhook(bot_token)
    except Exception as exc:
        try:
            from lumen.bot.singleton import clear_telegram_webhook
            ok = clear_telegram_webhook(bot_token)
            return {"ok": bool(ok)}
        except Exception:
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
    """Fill webhook fields and register with Telegram when needed."""
    url = webhook_url_for(instance_id)
    backend = str(getattr(inst, "sandbox_backend", "") or "")
    diag = dict(getattr(inst, "last_diagnosis", None) or {})

    if backend == "lumen_serverless":
        # Prefer URL already verified in orchestration phase-3
        verified_url = str(diag.get("webhook_url") or "").strip()
        pub = str(getattr(inst, "public_base_url", "") or "").rstrip("/")
        path = str(diag.get("webhook_path") or "/api")
        if not path.startswith("/"):
            path = "/" + path
        if verified_url.startswith("https://"):
            url = verified_url
        elif pub.startswith("https://"):
            url = pub + path

    inst.webhook_public_url = url
    secret = str(diag.get("webhook_secret") or "").strip() or ensure_secret(diag)
    diag["webhook_secret"] = secret
    result: dict[str, Any] = {"url": url, "registered": False, "backend": backend}

    # Already verified in phase-3 orchestration — do not re-register weakly
    if (
        backend == "lumen_serverless"
        and diag.get("verify_ok")
        and diag.get("webhook_verified")
        and str(diag.get("webhook_url") or "").startswith("https://")
    ):
        result["registered"] = True
        result["already_verified"] = True
        diag["webhook_registered"] = True
        diag["webhook_url"] = str(diag.get("webhook_url") or url)
        inst.last_diagnosis = diag
        return result

    if should_register(url) and str(getattr(inst, "status", "") or "") == "running":
        reg = register_webhook(bot_token, url, secret=secret)
        result["registered"] = bool(reg.get("ok"))
        result["verify"] = {k: reg.get(k) for k in ("verified", "reported", "error") if k in reg}
        diag["webhook_registered"] = bool(reg.get("ok"))
        diag["webhook_verified"] = bool(reg.get("verified"))
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
