"""Telegram webhooks for permanently hosted bots — stable URL by instance id.

POST /v1/hooks/telegram/{instance_id}

Traefik/Caddy route Host(`{instance_id}.{TBE_HOST_BASE_DOMAIN}`) → this path
(or path-based: /v1/hooks/telegram/{instance_id} on the API host).

Security:
  - Optional X-Telegram-Bot-Api-Secret-Token must match TBE_HOST_WEBHOOK_SECRET
    or per-instance secret stored in Redis meta.
  - Instance must exist in Redis/host registry and status=running.

Delivery:
  Updates are stored in Redis list ``lumen:host:tgq:{instance_id}`` for guests
  or side-cars that consume webhook mode. Polling bots keep deleteWebhook
  unless TBE_HOST_WEBHOOK_MODE=1 at start time.
"""
from __future__ import annotations

import json
import logging
import os

from aiohttp import web

logger = logging.getLogger("api.host_webhooks")


def _secret_ok(request: web.Request, instance_id: str) -> bool:
    expected = (os.environ.get("TBE_HOST_WEBHOOK_SECRET") or "").strip()
    header = (request.headers.get("X-Telegram-Bot-Api-Secret-Token") or "").strip()
    if expected:
        return bool(header) and header == expected
    # Per-instance secret from Redis
    try:
        from lumen.engine.services.hosting.redis_state import get_instance

        inst = get_instance(instance_id) or {}
        inst_secret = str((inst.get("last_diagnosis") or {}).get("webhook_secret") or "")
        if inst_secret:
            return bool(header) and header == inst_secret
    except Exception:
        pass
    # If no secret configured, only allow when explicit open mode (dev)
    env = (os.environ.get("ENVIRONMENT") or os.environ.get("TBE_ENV") or "").lower()
    return env in {"dev", "development", "local", "test"}


async def telegram_host_webhook(request: web.Request) -> web.Response:
    instance_id = str(request.match_info.get("instance_id") or "").strip()
    if not instance_id or len(instance_id) > 128:
        raise web.HTTPNotFound()
    if not _secret_ok(request, instance_id):
        logger.warning("host webhook secret failed instance=%s", instance_id)
        raise web.HTTPForbidden()

    inst = None
    try:
        from lumen.engine.services.hosting.redis_state import get_instance

        inst = get_instance(instance_id)
    except Exception:
        inst = None
    if not inst or str((inst or {}).get("status") or "") != "running":
        # Fallback: control-plane HostingService registry
        try:
            from lumen.engine.services.hosting import get_hosting_service
            from lumen.bot.config import OUTPUT_DIR

            live = get_hosting_service(OUTPUT_DIR).get(instance_id)
            if live is not None and str(getattr(live, "status", "") or "") == "running":
                inst = {
                    "instance_id": live.instance_id,
                    "status": live.status,
                    "last_diagnosis": dict(getattr(live, "last_diagnosis", None) or {}),
                }
        except Exception:
            pass
    if not inst or str(inst.get("status") or "") != "running":
        return web.json_response({"ok": True, "ignored": "not_running"})

    try:
        raw = await request.read()
        if len(raw) > 1_000_000:
            raise web.HTTPRequestEntityTooLarge()
        data = json.loads(raw.decode("utf-8"))
    except web.HTTPException:
        raise
    except Exception:
        raise web.HTTPBadRequest()

    try:
        from lumen.hosting.webhook_manager import enqueue_update
        enqueue_update(instance_id, data)
    except Exception:
        logger.exception("host webhook enqueue failed instance=%s", instance_id)

    try:
        from lumen.engine.services.hosting.usage_billing import record_request
        record_request(instance_id, 1)
    except Exception:
        pass
    return web.json_response({"ok": True})


__all__ = ["telegram_host_webhook"]
