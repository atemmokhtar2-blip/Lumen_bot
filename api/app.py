"""aiohttp application factory — B2B API + health."""
from __future__ import annotations

import logging
import os

from aiohttp import web

from api.routes import billing, dashboard, generate, health, hosts, tenants

logger = logging.getLogger("ai_agent_7h_api")


@web.middleware
async def cors_middleware(request: web.Request, handler):
    if request.method == "OPTIONS":
        resp = web.Response(status=204)
    else:
        try:
            resp = await handler(request)
        except web.HTTPException as ex:
            resp = ex
    resp.headers["Access-Control-Allow-Origin"] = os.getenv("API_CORS_ORIGIN", "*")
    resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, X-Api-Key, X-Admin-Token"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
    return resp


@web.middleware
async def error_middleware(request: web.Request, handler):
    try:
        return await handler(request)
    except web.HTTPException:
        raise
    except Exception as exc:
        logger.exception("unhandled api error")
        return web.json_response({"ok": False, "error": "internal_error", "detail": str(exc)[:200]}, status=500)


def create_app() -> web.Application:
    app = web.Application(middlewares=[error_middleware, cors_middleware])
    app.router.add_get("/health", health.health)
    app.router.add_get("/ready", health.ready)
    # Public
    app.router.add_get("/v1/plans", tenants.list_plans)
    app.router.add_post("/v1/tenants", tenants.create_tenant)
    app.router.add_post("/v1/billing/webhook/stripe", billing.stripe_webhook)
    # Authenticated
    app.router.add_get("/v1/me", tenants.me)
    app.router.add_post("/v1/me/rotate_key", tenants.rotate_key)
    app.router.add_patch("/v1/me/white-label", tenants.update_white_label)
    app.router.add_post("/v1/generate", generate.generate)
    app.router.add_post("/v1/hosts/start", hosts.host_start)
    app.router.add_post("/v1/hosts/stop", hosts.host_stop)
    app.router.add_get("/v1/hosts", hosts.host_status)
    app.router.add_post("/v1/hosts/diagnose", hosts.host_diagnose)
    app.router.add_get("/v1/usage", billing.usage)
    app.router.add_get("/v1/invoices", billing.invoices)
    app.router.add_post("/v1/invoices", billing.create_invoice)
    app.router.add_get("/v1/dashboard", dashboard.overview)
    return app


def run_api(host: str | None = None, port: int | None = None) -> None:
    host = host or os.getenv("API_HOST", "0.0.0.0")
    port = int(port or os.getenv("API_PORT") or os.getenv("PORT") or 8080)
    app = create_app()
    logger.info("B2B API listening on %s:%s", host, port)
    web.run_app(app, host=host, port=port, print=lambda *a, **k: None)
