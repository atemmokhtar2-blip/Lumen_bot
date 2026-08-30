"""Tenant + white-label management — presentation adapter.

Transport (HTTP) only. Business rules live in lumen.application handlers.
"""
from __future__ import annotations

from aiohttp import web

from lumen.api.auth import require_admin, require_tenant
from lumen.api.ownership import reject_identity_spoof
from lumen.api.security import safe_json_body
from lumen.application.commands.create_tenant import CreateTenantCommand
from lumen.application.handlers.tenant_handlers import handle_create_tenant
from lumen.bootstrap import get_tenant_repository
from lumen.platform.plans import PLANS, get_plan, normalize_plan_id, public_plan_dict


def _safe_telegram_id(value) -> int:
    if value is None or value == "":
        return 0
    try:
        n = int(value)
        return n if n > 0 else 0
    except (TypeError, ValueError):
        return 0


async def create_tenant(request: web.Request) -> web.Response:
    """Bootstrap a tenant — always requires PLATFORM_ADMIN_TOKEN."""
    require_admin(request)
    body = await safe_json_body(request, max_bytes=65536)
    name = str(body.get("name") or "Tenant").strip()
    plan_id = normalize_plan_id(str(body.get("plan_id") or "free").lower())
    if plan_id not in PLANS:
        plan_id = "free"

    try:
        tenant, raw_key = handle_create_tenant(
            CreateTenantCommand(
                name=name,
                plan_id=plan_id,
                owner_telegram_id=_safe_telegram_id(body.get("owner_telegram_id")),
                brand_name=str(body.get("brand_name") or name),
                brand_logo_url=str(body.get("brand_logo_url") or ""),
                primary_color=str(body.get("primary_color") or "#2563eb"),
                support_email=str(body.get("support_email") or ""),
                custom_domain=str(body.get("custom_domain") or ""),
            ),
            tenants=get_tenant_repository(),
        )
    except ValueError as exc:
        raise web.HTTPBadRequest(
            text=f'{{"error":"{exc}"}}',
            content_type="application/json",
        ) from exc

    return web.json_response(
        {
            "ok": True,
            "tenant": tenant.public_dict(),
            "api_key": raw_key,
            "plan": public_plan_dict(get_plan(tenant.plan_id)),
        },
        status=201,
    )


async def me(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    plan = get_plan(tenant.plan_id)
    return web.json_response(
        {"ok": True, "tenant": tenant.public_dict(), "plan": plan.__dict__}
    )


async def update_white_label(request: web.Request) -> web.Response:
    """Update brand fields only — never plan_id / active (billing owns those)."""
    tenant = require_tenant(request)
    plan = get_plan(tenant.plan_id)
    if not plan.white_label:
        raise web.HTTPForbidden(
            text='{"error":"plan_lacks_white_label"}',
            content_type="application/json",
        )
    body = await safe_json_body(request, max_bytes=65536)
    reject_identity_spoof(body)
    # Still via platform store until UpdateWhiteLabelCommand exists
    from lumen.platform.tenants import get_tenant_store

    updated = get_tenant_store().update_white_label(
        tenant.tenant_id,
        brand_name=body.get("brand_name"),
        brand_logo_url=body.get("brand_logo_url"),
        primary_color=body.get("primary_color"),
        support_email=body.get("support_email"),
        custom_domain=body.get("custom_domain"),
        name=body.get("name"),
    )
    if not updated:
        raise web.HTTPNotFound(
            text='{"error":"tenant_not_found"}',
            content_type="application/json",
        )
    return web.json_response({"ok": True, "tenant": updated.public_dict()})


async def rotate_key(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    from lumen.platform.tenants import get_tenant_store

    raw = get_tenant_store().rotate_key(tenant.tenant_id)
    if not raw:
        raise web.HTTPNotFound(
            text='{"error":"tenant_not_found"}',
            content_type="application/json",
        )
    return web.json_response({"ok": True, "api_key": raw})
