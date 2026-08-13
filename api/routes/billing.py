"""Billing + Stripe Checkout + usage endpoints."""
from __future__ import annotations

import json
import logging

from aiohttp import web

from api.auth import require_tenant
from b2b_platform.billing import get_billing
from b2b_platform.metering import get_metering
from b2b_platform.plans import get_plan
from b2b_platform.stripe_client import stripe_configured, verify_webhook_signature

logger = logging.getLogger("api.billing")


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
            "stripe_configured": stripe_configured(),
        }
    )


async def invoices(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    return web.json_response({"ok": True, "invoices": get_billing().list_invoices(tenant.tenant_id)})


async def create_invoice(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    body = {}
    if request.can_read_body:
        try:
            body = await request.json()
        except Exception:
            body = {}
    plan_id = str((body or {}).get("plan_id") or tenant.plan_id)
    inv = get_billing().create_monthly_invoice(tenant.tenant_id, plan_id=plan_id)
    if not inv:
        raise web.HTTPBadRequest(text='{"error":"invoice_failed"}', content_type="application/json")
    return web.json_response({"ok": True, "invoice": inv.__dict__}, status=201)


async def checkout(request: web.Request) -> web.Response:
    """Start Stripe Checkout for plan upgrade (pro / business)."""
    tenant = require_tenant(request)
    body = await request.json()
    plan_id = str(body.get("plan_id") or "").strip().lower()
    if not plan_id:
        raise web.HTTPBadRequest(text='{"error":"plan_id_required"}', content_type="application/json")
    result = get_billing().start_checkout(
        tenant.tenant_id,
        plan_id,
        success_url=str(body.get("success_url") or ""),
        cancel_url=str(body.get("cancel_url") or ""),
        customer_email=str(body.get("email") or body.get("customer_email") or tenant.support_email or ""),
    )
    status = 200 if result.get("ok") else 422
    return web.json_response(result, status=status)


async def checkout_success(request: web.Request) -> web.Response:
    """Browser return URL after Stripe Checkout — applies plan if webhook delayed."""
    session_id = request.rel_url.query.get("session_id") or ""
    if not session_id:
        return web.json_response({"ok": False, "error": "session_id_required"}, status=400)
    result = get_billing().complete_checkout_session(session_id)
    # Friendly HTML for browser users
    if "text/html" in (request.headers.get("Accept") or ""):
        ok = result.get("ok")
        msg = "Payment successful — plan activated." if ok else f"Pending: {result.get('error') or result}"
        html = f"""<!doctype html><html><body style="font-family:system-ui;padding:2rem">
        <h1>{"✅" if ok else "⏳"} Checkout</h1>
        <p>{msg}</p>
        <pre style="background:#f4f4f5;padding:1rem;border-radius:8px">{json.dumps(result, indent=2)}</pre>
        </body></html>"""
        return web.Response(text=html, content_type="text/html")
    return web.json_response(result)


async def checkout_cancel(request: web.Request) -> web.Response:
    if "text/html" in (request.headers.get("Accept") or ""):
        return web.Response(
            text="<!doctype html><html><body style='font-family:system-ui;padding:2rem'>"
            "<h1>Checkout cancelled</h1><p>No charge was made.</p></body></html>",
            content_type="text/html",
        )
    return web.json_response({"ok": True, "cancelled": True})


async def portal(request: web.Request) -> web.Response:
    """Stripe Customer Billing Portal (manage subscription / payment methods)."""
    tenant = require_tenant(request)
    body = {}
    if request.can_read_body:
        try:
            body = await request.json()
        except Exception:
            body = {}
    result = get_billing().portal(
        tenant.tenant_id,
        return_url=str((body or {}).get("return_url") or ""),
    )
    status = 200 if result.get("ok") else 422
    return web.json_response(result, status=status)


async def stripe_webhook(request: web.Request) -> web.Response:
    """Stripe webhook — verifies signature when STRIPE_WEBHOOK_SECRET is set."""
    raw = await request.read()
    sig = request.headers.get("Stripe-Signature") or ""
    if not verify_webhook_signature(raw, sig):
        logger.warning("stripe webhook signature failed")
        raise web.HTTPBadRequest(text='{"error":"invalid_signature"}', content_type="application/json")
    try:
        event = json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        raise web.HTTPBadRequest(text='{"error":"invalid_json"}', content_type="application/json")
    result = get_billing().handle_stripe_event(event)
    logger.info("stripe webhook type=%s handled=%s", event.get("type"), result.get("handled"))
    return web.json_response(result)


async def dev_activate(request: web.Request) -> web.Response:
    """Dev-only plan activation — hard-gated; never free privilege escalation in SaaS."""
    import os
    from telegram_bot_engine.services.isolation_policy import is_dev_environment, is_multi_tenant

    allow = (os.getenv("ALLOW_DEV_BILLING") or "").strip().lower() in {"1", "true", "yes", "on"}
    if not allow:
        raise web.HTTPForbidden(
            text='{"error":"dev_activate_disabled","detail":"set ALLOW_DEV_BILLING=1 only in trusted dev"}',
            content_type="application/json",
        )
    # Multi-tenant or non-dev: require platform admin token always
    admin = (os.getenv("PLATFORM_ADMIN_TOKEN") or "").strip()
    if is_multi_tenant() or not is_dev_environment() or stripe_configured():
        if not admin or (request.headers.get("X-Admin-Token") or "").strip() != admin:
            raise web.HTTPUnauthorized(
                text='{"error":"admin_required_for_dev_activate"}',
                content_type="application/json",
            )
    tenant = require_tenant(request)
    body = await request.json()
    plan_id = str(body.get("plan_id") or "pro").lower()
    inv_id = str(body.get("invoice_id") or "")
    ok = get_billing().apply_plan(tenant.tenant_id, plan_id)
    if inv_id:
        get_billing().mark_paid(inv_id, provider_ref="dev_activate")
    return web.json_response({"ok": ok, "plan_id": plan_id, "tenant_id": tenant.tenant_id})
