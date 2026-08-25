"""Managed bot hosting API — sandbox-scoped paths only."""
from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from api.auth import require_tenant
from api.ownership import reject_identity_spoof
from api.security import (
    safe_json_body,
    stable_tenant_uid,
    validate_tenant_project_path,
)
from b2b_platform.billing import get_billing
from b2b_platform.metering import get_metering
from telegram_bot_engine.services.hosting import get_hosting_service

logger = logging.getLogger("api.hosts")


def _tenant_user_id(tenant_id: str) -> int:
    return stable_tenant_uid(tenant_id)


async def host_start(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    # Balance lifecycle gate — fail-closed in production
    import os as _os
    _dev = (_os.getenv("ENVIRONMENT") or _os.getenv("TBE_ENV") or "").strip().lower() in {
        "dev", "development", "local", "test",
    }
    try:
        from b2b_platform.balance_lifecycle import get_balance_lifecycle
        from b2b_platform.rating_engine import reserve_for_hosting
        from b2b_platform.credits import get_credit_service
        import time as _time
        ok_h, reason_h = get_balance_lifecycle().is_hosting_allowed(tenant.tenant_id)
        if not ok_h:
            return web.json_response({"ok": False, "error": reason_h}, status=402)
        res = reserve_for_hosting(
            get_credit_service(),
            tenant.tenant_id,
            hours=1,
            ram_mb=256,
            reference_id="host_start",
            idempotency_key=f"reserve-host-{tenant.tenant_id}-{int(_time.time()) // 3600}",
        )
        if not res.ok and "insufficient" in (res.reason or ""):
            return web.json_response(
                {"ok": False, "error": res.reason, "hint": "top up credits before hosting"},
                status=402,
            )
    except Exception as _bal_exc:
        logger.exception("balance gate error")
        if not _dev:
            return web.json_response(
                {"ok": False, "error": "balance_gate_unavailable"},
                status=503,
            )
    body = await safe_json_body(request, max_bytes=65536)
    reject_identity_spoof(body, tenant_id=tenant.tenant_id)
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
    body = await safe_json_body(request, max_bytes=65536)
    reject_identity_spoof(body, tenant_id=tenant.tenant_id)
    instance_id = str(body.get("instance_id") or "").strip()
    if not instance_id or len(instance_id) > 128:
        raise web.HTTPNotFound(
            text='{"error":"instance_not_found"}',
            content_type="application/json",
        )
    uid = _tenant_user_id(tenant.tenant_id)
    # Explicit ownership probe before stop (uniform 404)
    svc = get_hosting_service()
    inst = svc.get(instance_id, user_id=uid)
    if inst is None:
        raise web.HTTPNotFound(
            text='{"error":"instance_not_found"}',
            content_type="application/json",
        )
    result = await asyncio.to_thread(
        lambda: svc.stop(instance_id=instance_id, user_id=uid)
    )
    try:
        from bot_interface.sanitize import sanitize_error
        msg = sanitize_error(str(result.message or ""), max_len=300)
    except Exception:
        msg = "host_operation_completed" if result.ok else "host_operation_failed"
    return web.json_response({"ok": result.ok, "message": msg})


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
    body = await safe_json_body(request, required=False, max_bytes=65536)
    reject_identity_spoof(body, tenant_id=tenant.tenant_id)
    instance_id = str(
        body.get("instance_id") or request.rel_url.query.get("instance_id") or ""
    ).strip()
    uid = _tenant_user_id(tenant.tenant_id)
    result = await asyncio.to_thread(
        lambda: get_hosting_service().diagnose(
            user_id=uid, instance_id=instance_id or None
        )
    )
    return web.json_response(
        {"ok": result.ok, "message": result.message, "details": result.details}
    )
