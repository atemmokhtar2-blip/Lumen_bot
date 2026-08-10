"""Billing + usage dashboard endpoints."""
from __future__ import annotations

from aiohttp import web

from api.auth import require_tenant
from b2b_platform.billing import get_billing
from b2b_platform.metering import get_metering
from b2b_platform.plans import get_plan


async def usage(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    snap = get_metering().snapshot(tenant.tenant_id)
    plan = get_plan(tenant.plan_id)
    return web.json_response(
        {
            "ok": True,
            "usage": snap,
            "quotas": {
                "generations_per_month": plan.generations_per_month,
                "hosted_bots": plan.hosted_bots,
                "api_rpm": plan.api_rpm,
            },
        }
    )


async def invoices(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    return web.json_response({"ok": True, "invoices": get_billing().list_invoices(tenant.tenant_id)})


async def create_invoice(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    inv = get_billing().create_monthly_invoice(tenant.tenant_id)
    if not inv:
        raise web.HTTPBadRequest(text='{"error":"invoice_failed"}', content_type="application/json")
    return web.json_response({"ok": True, "invoice": inv.__dict__}, status=201)


async def stripe_webhook(request: web.Request) -> web.Response:
    body = await request.json()
    result = get_billing().stripe_webhook_placeholder(body)
    return web.json_response(result)
