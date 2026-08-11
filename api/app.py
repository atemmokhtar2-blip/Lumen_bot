"""aiohttp application factory — B2B API + health."""
from __future__ import annotations

import logging
import os

from aiohttp import web

from api.routes import billing, dashboard, generate, health, hosts, jobs, tenants

logger = logging.getLogger("ai_agent_7h_api")


def _cors_origin_for(request: web.Request) -> str | None:
    """Return an allowed Origin or None (no ACAO header → browser blocks).

    Default is DENY (empty). Set API_CORS_ORIGIN to a comma-separated allowlist
    of exact origins, e.g. https://app.example.com,https://admin.example.com
    Never defaults to *.
    """
    raw = (os.getenv("API_CORS_ORIGIN") or "").strip()
    if not raw or raw == "*":
        # Explicit * only if operator sets API_CORS_ALLOW_WILDCARD=1 (discouraged)
        if raw == "*" and (os.getenv("API_CORS_ALLOW_WILDCARD") or "").strip().lower() in {
            "1", "true", "yes", "on",
        }:
            return "*"
        return None
    allowed = {o.strip() for o in raw.split(",") if o.strip()}
    origin = (request.headers.get("Origin") or "").strip()
    if origin and origin in allowed:
        return origin
    return None


@web.middleware
async def cors_middleware(request: web.Request, handler):
    if request.method == "OPTIONS":
        resp = web.Response(status=204)
    else:
        try:
            resp = await handler(request)
        except web.HTTPException as ex:
            resp = ex
    origin = _cors_origin_for(request)
    if origin:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Vary"] = "Origin"
        resp.headers["Access-Control-Allow-Credentials"] = "true"
    resp.headers["Access-Control-Allow-Headers"] = (
        "Authorization, Content-Type, X-Api-Key, X-Admin-Token"
    )
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
    # Basic hardening headers
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    return resp


@web.middleware
async def error_middleware(request: web.Request, handler):
    try:
        return await handler(request)
    except web.HTTPException:
        raise
    except Exception:
        # Never leak exception text / paths / stack traces to clients
        logger.exception("unhandled api error path=%s", request.path)
        return web.json_response(
            {"ok": False, "error": "internal_error"},
            status=500,
        )


def create_app() -> web.Application:
    app = web.Application(middlewares=[error_middleware, cors_middleware])
    app.router.add_get("/health", health.health)
    app.router.add_get("/ready", health.ready)
    # Public
    app.router.add_get("/v1/plans", tenants.list_plans)
    app.router.add_post("/v1/tenants", tenants.create_tenant)
    app.router.add_post("/v1/billing/webhook/stripe", billing.stripe_webhook)
    app.router.add_get("/v1/billing/checkout/success", billing.checkout_success)
    app.router.add_get("/v1/billing/checkout/cancel", billing.checkout_cancel)
    # Authenticated
    app.router.add_get("/v1/me", tenants.me)
    app.router.add_post("/v1/me/rotate_key", tenants.rotate_key)
    app.router.add_patch("/v1/me/white-label", tenants.update_white_label)
    app.router.add_post("/v1/generate", generate.generate)
    app.router.add_get("/v1/jobs/{job_id}", jobs.get_job)
    app.router.add_get("/v1/jobs", jobs.list_jobs)
    app.router.add_post("/v1/hosts/start", hosts.host_start)
    app.router.add_post("/v1/hosts/stop", hosts.host_stop)
    app.router.add_get("/v1/hosts", hosts.host_status)
    app.router.add_post("/v1/hosts/diagnose", hosts.host_diagnose)
    app.router.add_get("/v1/usage", billing.usage)
    app.router.add_get("/v1/invoices", billing.invoices)
    app.router.add_post("/v1/invoices", billing.create_invoice)
    app.router.add_post("/v1/billing/checkout", billing.checkout)
    app.router.add_post("/v1/billing/portal", billing.portal)
    app.router.add_post("/v1/billing/dev/activate", billing.dev_activate)
    app.router.add_get("/v1/dashboard", dashboard.overview)
    return app


def run_api(host: str | None = None, port: int | None = None) -> None:
    host = host or os.getenv("API_HOST", "0.0.0.0")
    port = int(port or os.getenv("API_PORT") or os.getenv("PORT") or 8080)
    app = create_app()
    logger.info("B2B API listening on %s:%s", host, port)
    web.run_app(app, host=host, port=port, print=lambda *a, **k: None)
