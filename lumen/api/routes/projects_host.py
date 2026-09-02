"""User-facing project hosting API — REST paths under /v1/projects.

Maps product paths to HostingService (permanent host plane).
"""
from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from lumen.api.auth import require_tenant
from lumen.api.ownership import reject_identity_spoof
from lumen.api.security import (
    safe_json_body,
    stable_tenant_uid,
    validate_tenant_project_path,
)
from lumen.engine.services.hosting import get_hosting_service

logger = logging.getLogger("api.projects_host")


def _uid(tenant_id: str) -> int:
    return stable_tenant_uid(tenant_id)


def _inst_json(i) -> dict:
    if i is None:
        return None
    return {
        "id": i.instance_id,
        "instance_id": i.instance_id,
        "status": i.status,
        "project_path": i.project_path,
        "bot_username": i.bot_username,
        "public_base_url": getattr(i, "public_base_url", "") or "",
        "version_ref": getattr(i, "version_ref", "") or "",
        "sandbox_backend": getattr(i, "sandbox_backend", "") or "",
        "last_health_at": getattr(i, "last_health_at", 0) or 0,
        "last_error": i.last_error or "",
        "pid": i.pid,
    }


async def list_projects(request: web.Request) -> web.Response:
    """GET /v1/projects — list hosted instances for tenant."""
    tenant = require_tenant(request)
    items = get_hosting_service().list_for_user(_uid(tenant.tenant_id))
    return web.json_response({"ok": True, "projects": [_inst_json(i) for i in items]})


async def project_logs(request: web.Request) -> web.Response:
    """GET /v1/projects/{id}/logs"""
    tenant = require_tenant(request)
    instance_id = str(request.match_info.get("id") or "").strip()
    limit = int(request.rel_url.query.get("limit") or 100)
    uid = _uid(tenant.tenant_id)
    result = await asyncio.to_thread(
        lambda: get_hosting_service().logs(user_id=uid, instance_id=instance_id, limit=limit)
    )
    return web.json_response(
        {"ok": result.ok, "id": instance_id, "logs": result.message, "details": result.details},
        status=200 if result.ok else 422,
    )


async def project_redeploy(request: web.Request) -> web.Response:
    """POST /v1/projects/{id}/redeploy  body: {bot_token}"""
    tenant = require_tenant(request)
    instance_id = str(request.match_info.get("id") or "").strip()
    body = await safe_json_body(request, max_bytes=65536)
    reject_identity_spoof(body, tenant_id=tenant.tenant_id)
    bot_token = str(body.get("bot_token") or body.get("token") or "").strip()
    if not bot_token:
        raise web.HTTPBadRequest(
            text='{"error":"bot_token_required"}', content_type="application/json"
        )
    uid = _uid(tenant.tenant_id)
    svc = get_hosting_service()
    inst = svc.get(instance_id, user_id=uid)
    if inst is None:
        raise web.HTTPNotFound(text='{"error":"project_not_found"}', content_type="application/json")
    await asyncio.to_thread(lambda: svc.stop(instance_id=instance_id, user_id=uid))
    result = await asyncio.to_thread(
        lambda: svc.start(
            user_id=uid,
            project_path=inst.project_path,
            bot_token=bot_token,
            bot_username=inst.bot_username or "",
            entry_point=getattr(inst, "entry_point", "") or "",
        )
    )
    return web.json_response(
        {"ok": result.ok, "message": result.message, "project": _inst_json(result.instance)},
        status=200 if result.ok else 422,
    )


async def project_delete(request: web.Request) -> web.Response:
    """DELETE /v1/projects/{id}"""
    tenant = require_tenant(request)
    instance_id = str(request.match_info.get("id") or "").strip()
    uid = _uid(tenant.tenant_id)
    svc = get_hosting_service()
    inst = svc.get(instance_id, user_id=uid)
    if inst is None:
        raise web.HTTPNotFound(text='{"error":"project_not_found"}', content_type="application/json")
    await asyncio.to_thread(lambda: svc.stop(instance_id=instance_id, user_id=uid))
    try:
        svc._instances.pop(instance_id, None)
        svc._save()
        from lumen.engine.services.hosting.redis_state import delete_instance

        delete_instance(instance_id, user_id=uid)
    except Exception:
        pass
    return web.json_response({"ok": True, "deleted": instance_id})


async def project_restart(request: web.Request) -> web.Response:
    """POST /v1/projects/{id}/restart — uses sealed secrets if bot_token omitted."""
    tenant = require_tenant(request)
    instance_id = str(request.match_info.get("id") or "").strip()
    body = await safe_json_body(request, required=False, max_bytes=65536)
    reject_identity_spoof(body, tenant_id=tenant.tenant_id)
    bot_token = str((body or {}).get("bot_token") or (body or {}).get("token") or "").strip()
    uid = _uid(tenant.tenant_id)
    result = await asyncio.to_thread(
        lambda: get_hosting_service().restart(
            instance_id=instance_id, user_id=uid, bot_token=bot_token
        )
    )
    return web.json_response(
        {"ok": result.ok, "message": result.message, "project": _inst_json(result.instance)},
        status=200 if result.ok else 422,
    )


async def project_start(request: web.Request) -> web.Response:

    """POST /v1/projects — start host: {project_path, bot_token}"""
    from lumen.api.routes import hosts as hosts_mod

    return await hosts_mod.host_start(request)


__all__ = [
    "list_projects",
    "project_logs",
    "project_redeploy",
    "project_delete",
    "project_start",
    "project_restart",
]
