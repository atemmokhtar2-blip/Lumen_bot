"""Tenant + white-label management."""
from __future__ import annotations

from aiohttp import web

from api.auth import require_tenant
from b2b_platform.plans import PLANS, get_plan
from b2b_platform.tenants import get_tenant_store


async def create_tenant(request: web.Request) -> web.Response:
    """Bootstrap a tenant (protected by PLATFORM_ADMIN_TOKEN if set)."""
    import os

    admin = (os.getenv("PLATFORM_ADMIN_TOKEN") or "").strip()
    if admin:
        token = (request.headers.get("X-Admin-Token") or "").strip()
        if token != admin:
            raise web.HTTPUnauthorized(text='{"error":"admin_required"}', content_type="application/json")
    body = await request.json()
    name = str(body.get("name") or "Tenant").strip()
    plan_id = str(body.get("plan_id") or "free").lower()
    if plan_id not in PLANS:
        plan_id = "free"
    tenant, raw_key = get_tenant_store().create(
        name,
        plan_id=plan_id,
        brand_name=str(body.get("brand_name") or name),
        owner_telegram_id=int(body.get("owner_telegram_id") or 0),
        brand_logo_url=body.get("brand_logo_url") or "",
        primary_color=body.get("primary_color") or "#2563eb",
        support_email=body.get("support_email") or "",
        custom_domain=body.get("custom_domain") or "",
    )
    return web.json_response(
        {
            "ok": True,
            "tenant": tenant.public_dict(),
            "api_key": raw_key,  # shown once
            "plan": get_plan(tenant.plan_id).__dict__,
        },
        status=201,
    )


async def me(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    plan = get_plan(tenant.plan_id)
    return web.json_response({"ok": True, "tenant": tenant.public_dict(), "plan": plan.__dict__})


async def update_white_label(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    plan = get_plan(tenant.plan_id)
    if not plan.white_label and plan.id not in ("business", "enterprise"):
        raise web.HTTPForbidden(
            text='{"error":"plan_lacks_white_label"}',
            content_type="application/json",
        )
    body = await request.json()
    updated = get_tenant_store().update_white_label(tenant.tenant_id, **body)
    return web.json_response({"ok": True, "tenant": updated.public_dict() if updated else None})


async def rotate_key(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    raw = get_tenant_store().rotate_key(tenant.tenant_id)
    return web.json_response({"ok": True, "api_key": raw})


async def list_plans(request: web.Request) -> web.Response:
    return web.json_response(
        {"ok": True, "plans": [p.__dict__ for p in PLANS.values()]},
    )
