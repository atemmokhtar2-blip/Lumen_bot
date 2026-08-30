"""Billing — credits only (subscription plans removed)."""
from __future__ import annotations

import logging

from aiohttp import web

from lumen.api.auth import require_admin, require_tenant
from lumen.api.ownership import reject_identity_spoof
from lumen.api.security import safe_json_body
from lumen.platform.billing import get_billing
from lumen.platform.metering import get_metering
from lumen.platform.stripe_client import stripe_configured, verify_webhook_signature

logger = logging.getLogger("api.billing")


def _plans_gone() -> web.Response:
    return web.json_response(
        {
            "ok": False,
            "error": "plans_removed",
            "detail": "Subscription plans are removed. Use credits checkout.",
            "billing": "credits_only",
        },
        status=410,
    )


async def usage(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    snap = get_metering().snapshot(tenant.tenant_id)
    balance = None
    try:
        from lumen.application.handlers.billing_handlers import handle_get_balance
        from lumen.application.queries.get_balance import GetBalanceQuery
        from lumen.bootstrap import get_billing_gateway

        bal = handle_get_balance(
            GetBalanceQuery(tenant_id=tenant.tenant_id),
            billing=get_billing_gateway(),
        )
        balance = bal.public_dict()
    except Exception:
        balance = None
    return web.json_response(
        {
            "ok": True,
            "usage": snap,
            "balance": balance,
            "billing": "credits_only",
            "stripe_configured": stripe_configured(),
        }
    )


async def invoices(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    return web.json_response(
        {"ok": True, "invoices": get_billing().list_invoices(tenant.tenant_id)}
    )


async def create_invoice(request: web.Request) -> web.Response:
    return _plans_gone()


async def checkout(request: web.Request) -> web.Response:
    """Legacy plan checkout — removed."""
    return _plans_gone()


async def credits_checkout(request: web.Request) -> web.Response:
    """POST /v1/billing/credits/checkout — buy credits pack via Stripe."""
    tenant = require_tenant(request)
    body = await safe_json_body(request, max_bytes=65536)
    reject_identity_spoof(body, tenant_id=tenant.tenant_id)
    try:
        amount = int(body.get("credits_amount") or body.get("amount") or 0)
    except (TypeError, ValueError):
        amount = 0
    if amount <= 0:
        raise web.HTTPBadRequest(
            text='{"error":"credits_amount_required"}',
            content_type="application/json",
        )
    result = get_billing().start_credits_checkout(
        tenant.tenant_id,
        credits_amount=amount,
        success_url=str(body.get("success_url") or ""),
        cancel_url=str(body.get("cancel_url") or ""),
    )
    status = 200 if result.get("ok") else 400
    return web.json_response(result, status=status)


async def checkout_success(request: web.Request) -> web.Response:
    """Browser return URL after Stripe Checkout (credits)."""
    session_id = (request.rel_url.query.get("session_id") or "").strip()
    if not session_id:
        raise web.HTTPBadRequest(
            text='{"error":"session_id_required"}',
            content_type="application/json",
        )
    result = get_billing().complete_checkout_session(session_id)
    ok = bool(result.get("ok"))
    msg = (
        "Payment successful — credits granted."
        if ok
        else f"Pending: {result.get('error') or result}"
    )
    return web.Response(
        text=f"<!doctype html><html><body><h1>{msg}</h1></body></html>",
        content_type="text/html",
    )


async def checkout_cancel(request: web.Request) -> web.Response:
    return web.Response(
        text="<!doctype html><html><body><h1>Checkout cancelled</h1></body></html>",
        content_type="text/html",
    )


async def portal(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    result = get_billing().billing_portal(tenant.tenant_id)
    status = 200 if result.get("ok") else 400
    return web.json_response(result, status=status)


async def dev_activate(request: web.Request) -> web.Response:
    """Legacy plan activate — removed."""
    return _plans_gone()


async def stripe_webhook(request: web.Request) -> web.Response:
    payload = await request.read()
    sig = request.headers.get("Stripe-Signature") or ""
    try:
        event = verify_webhook_signature(payload, sig)
    except Exception as exc:
        logger.warning("stripe webhook verify failed: %s", exc)
        raise web.HTTPBadRequest(
            text='{"error":"invalid_signature"}',
            content_type="application/json",
        ) from exc
    result = get_billing().handle_stripe_webhook(event)
    return web.json_response(result)
