"""Tenant + white-label management — presentation adapter.

Plans system removed. Billing is credits-only.
"""
from __future__ import annotations

from aiohttp import web

from lumen.api.auth import require_admin, require_tenant
from lumen.api.ownership import reject_identity_spoof
from lumen.api.security import safe_json_body
from lumen.application.commands.create_tenant import CreateTenantCommand
from lumen.application.commands.rotate_api_key import RotateApiKeyCommand
from lumen.application.commands.update_white_label import UpdateWhiteLabelCommand
from lumen.application.handlers.tenant_handlers import (
    handle_create_tenant,
    handle_rotate_api_key,
    handle_update_white_label,
)
from lumen.bootstrap import get_tenant_repository


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

    try:
        tenant, raw_key = handle_create_tenant(
            CreateTenantCommand(
                name=name,
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
            "billing": "credits_only",
        },
        status=201,
    )


async def me(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    return web.json_response(
        {"ok": True, "tenant": tenant.public_dict(), "billing": "credits_only"}
    )


async def update_white_label(request: web.Request) -> web.Response:
    """Update brand fields — no plan gate (plans removed)."""
    tenant = require_tenant(request)
    body = await safe_json_body(request, max_bytes=65536)
    reject_identity_spoof(body, tenant_id=tenant.tenant_id)
    try:
        updated = handle_update_white_label(
            UpdateWhiteLabelCommand(
                tenant_id=tenant.tenant_id,
                brand_name=body.get("brand_name"),
                brand_logo_url=body.get("brand_logo_url"),
                primary_color=body.get("primary_color"),
                support_email=body.get("support_email"),
                custom_domain=body.get("custom_domain"),
                name=body.get("name"),
            ),
            tenants=get_tenant_repository(),
        )
    except LookupError:
        raise web.HTTPNotFound(
            text='{"error":"tenant_not_found"}',
            content_type="application/json",
        )
    return web.json_response({"ok": True, "tenant": updated.public_dict()})


async def rotate_key(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    try:
        raw = handle_rotate_api_key(
            RotateApiKeyCommand(tenant_id=tenant.tenant_id),
            tenants=get_tenant_repository(),
        )
    except LookupError:
        raise web.HTTPNotFound(
            text='{"error":"tenant_not_found"}',
            content_type="application/json",
        )
    return web.json_response({"ok": True, "api_key": raw})
