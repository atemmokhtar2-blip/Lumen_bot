"""Managed bot hosting API — sandbox-scoped paths only."""
from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from api.auth import require_tenant
from api.security import stable_tenant_uid, validate_tenant_project_path
from b2b_platform.billing import get_billing
from b2b_platform.metering import get_metering
from telegram_bot_engine.services.hosting import get_hosting_service

logger = logging.getLogger("api.hosts")


def _tenant_user_id(tenant_id: str) -> int:
    return stable_tenant_uid(tenant_id)


async def host_start(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    cl = request.headers.get("Content-Length")
    if cl and cl.isdigit() and int(cl) > 65536:
        raise web.HTTPRequestEntityTooLarge(
            text='{"error":"payload_too_large"}',
            content_type="application/json",
        )
    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(
            text='{"error":"invalid_json"}',
            content_type="application/json",
        )
    if not isinstance(body, dict):
        raise web.HTTPBadRequest(
            text='{"error":"body_must_be_object"}',
            content_type="application/json",
        )
    project_path = str(body.get("project_path") or "").strip()
    bot_token = str(body.get("bot_token") or body.get("token") or "").strip()

    try:
        safe_path = validate_tenant_project_path(tenant.tenant_id, project_path)
    except ValueError as exc:
        logger.warning(
            "host_start path rejected tenant=%s reason=%s",
            tenant.tenant_id,
            exc,
        )
        raise web.HTTPBadRequest(
            text='{"error":"project_path_outside_sandbox"}',
            content_type="application/json",
        )

    if not bot_token or ":" not in bot_token or len(bot_token) < 30:
        raise web.HTTPBadRequest(
            text='{"error":"bot_token_required"}',
            content_type="application/json",
        )

    svc = get_hosting_service()
    uid = _tenant_user_id(tenant.tenant_id)
    current = len(svc.list_for_user(uid))
    ok, reason = get_billing().enforce_hosting(tenant.tenant_id, current)
    if not ok:
        raise web.HTTPPaymentRequired(
            text=f'{{"error":"{reason}"}}',
            content_type="application/json",
        )

    result = await asyncio.to_thread(
        lambda: svc.start(
            user_id=uid,
            project_path=str(safe_path),
            bot_token=bot_token,
            bot_username=str(body.get("bot_username") or ""),
        )
    )
    if result.ok:
        get_metering().record(tenant.tenant_id, host_starts=1, event="host_start")
    inst = result.instance
    return web.json_response(
        {
            "ok": result.ok,
            "message": result.message,
            "instance": None
            if not inst
            else {
                "instance_id": inst.instance_id,
                "status": inst.status,
                # never echo raw host filesystem beyond sandbox-relative hint
                "project_path": inst.project_path,
                "bot_username": inst.bot_username,
                "pid": inst.pid,
            },
        },
        status=200 if result.ok else 422,
    )


async def host_stop(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    body = await request.json()
    instance_id = str(body.get("instance_id") or "").strip()
    uid = _tenant_user_id(tenant.tenant_id)
    result = await asyncio.to_thread(
        lambda: get_hosting_service().stop(instance_id=instance_id, user_id=uid)
    )
    return web.json_response({"ok": result.ok, "message": result.message})


async def host_status(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    uid = _tenant_user_id(tenant.tenant_id)
    instances = get_hosting_service().list_for_user(uid)
    return web.json_response(
        {
            "ok": True,
            "instances": [
                {
                    "instance_id": i.instance_id,
                    "status": i.status,
                    "project_path": i.project_path,
                    "bot_username": i.bot_username,
                    "pid": i.pid,
                    "last_error": i.last_error,
                }
                for i in instances
            ],
        }
    )


async def host_diagnose(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    body = await request.json() if request.can_read_body else {}
    instance_id = str(
        (body or {}).get("instance_id") or request.rel_url.query.get("instance_id") or ""
    )
    uid = _tenant_user_id(tenant.tenant_id)
    result = await asyncio.to_thread(
        lambda: get_hosting_service().diagnose(
            user_id=uid, instance_id=instance_id or None
        )
    )
    return web.json_response(
        {"ok": result.ok, "message": result.message, "details": result.details}
    )
