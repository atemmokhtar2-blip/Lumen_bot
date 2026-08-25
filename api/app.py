"""aiohttp application factory — B2B API + health."""
from __future__ import annotations

import hashlib
import logging
import os

from aiohttp import web

from api.routes import billing, dashboard, generate, health, hosts, jobs, tenants, usage

logger = logging.getLogger("ai_agent_7h_api")

# B2B API is multi-tenant by nature: require Docker isolation unless operator overrides.
# Set TBE_MULTI_TENANT=0 explicitly only for single-tenant local debugging.
if "TBE_MULTI_TENANT" not in os.environ:
    os.environ["TBE_MULTI_TENANT"] = "1"
if "TBE_REQUIRE_DOCKER" not in os.environ:
    os.environ["TBE_REQUIRE_DOCKER"] = "1"
if "TBE_ALLOW_LOCAL_PROCESS" not in os.environ:
    os.environ["TBE_ALLOW_LOCAL_PROCESS"] = "0"
if "TBE_PIP_WHEELS_ONLY" not in os.environ:
    os.environ["TBE_PIP_WHEELS_ONLY"] = "1"



def _cors_origin_for(request: web.Request) -> str | None:
    """Return an allowed Origin or None (no ACAO header → browser blocks).

    Default is DENY (empty). Set API_CORS_ORIGIN to a comma-separated allowlist
    of exact origins, e.g. https://app.example.com,https://admin.example.com
    Never defaults to *.
    """
    raw = (os.getenv("API_CORS_ORIGIN") or "").strip()
    if not raw or raw == "*":
        # Wildcard CORS is forbidden outside explicit dev — prevents credentialed cross-origin abuse
        env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "production").strip().lower()
        is_dev = env in {"dev", "development", "local", "test"}
        wild = (os.getenv("API_CORS_ALLOW_WILDCARD") or "").strip().lower() in {
            "1", "true", "yes", "on",
        }
        if raw == "*" and wild and is_dev:
            return "*"
        if raw == "*" and wild and not is_dev:
            logger.warning("API_CORS_ALLOW_WILDCARD ignored in production (fail-closed)")
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
        # Spec forbids Access-Control-Allow-Credentials: true together with
        # Access-Control-Allow-Origin: *. Browsers reject that combination.
        if origin != "*":
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
    except Exception as exc:
        # Never leak exception text / paths / stack traces to clients
        try:
            from bot_interface.sanitize import sanitize_error, install_secret_log_filter
            install_secret_log_filter()
            safe = sanitize_error(f"{type(exc).__name__}: {exc}", max_len=200)
            logger.exception("unhandled api error path=%s detail=%s", request.path, safe)
        except Exception:
            logger.exception("unhandled api error path=%s", request.path)
        return web.json_response(
            {"ok": False, "error": "internal_error"},
            status=500,
        )


def _client_ip(request: web.Request) -> str:
    """Return a stable client key without trusting spoofed forwarding headers."""
    peer = str(request.remote or "unknown").strip()
    trusted = {
        item.strip()
        for item in (os.getenv("TRUSTED_PROXY_IPS") or "").split(",")
        if item.strip()
    }
    if peer in trusted:
        xff = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        if xff:
            return xff[:64]
    return peer[:64]



@web.middleware
async def body_size_guard_middleware(request: web.Request, handler):
    """Reject clearly abusive size claims; rely on client_max_size for actual body.

    Content-Length can be spoofed; aiohttp still enforces client_max_size when
    reading the body. We only short-circuit obviously hostile declared sizes.
    """
    max_size = int(os.getenv("API_CLIENT_MAX_SIZE") or str(256 * 1024))
    cl = request.headers.get("Content-Length")
    if cl is not None:
        try:
            n = int(cl)
            if n < 0 or n > max_size:
                return web.json_response(
                    {"ok": False, "error": "payload_too_large"},
                    status=413,
                )
        except ValueError:
            return web.json_response(
                {"ok": False, "error": "invalid_content_length"},
                status=400,
            )
    return await handler(request)


@web.middleware
async def json_body_middleware(request: web.Request, handler):
    """Root JSON gate: bytes → parse_json_object_bytes before any route runs.

    Skips RAW_BODY_PATHS (Stripe webhook signature, generate size-cap path).
    Empty body is valid → {}. Invalid JSON / non-object → 400 at the edge.
    Never uses request.json(); single parser lives in api.security.
    """
    if request.method not in {"POST", "PUT", "PATCH"}:
        return await handler(request)

    from api.security import (
        RAW_BODY_PATHS,
        parse_json_object_bytes,
        read_capped_body,
    )

    path = request.path or ""
    if path in RAW_BODY_PATHS:
        return await handler(request)

    max_size = int(os.getenv("API_CLIENT_MAX_SIZE") or str(256 * 1024))
    try:
        raw = await read_capped_body(request, max_bytes=max_size)
        body = parse_json_object_bytes(raw, empty_ok=True)
    except ValueError as exc:
        code = str(exc) or "invalid_json"
        status = 413 if code == "payload_too_large" else 400
        return web.json_response({"ok": False, "error": code}, status=status)

    request["json_body"] = body
    request["json_body_parsed"] = True
    return await handler(request)


@web.middleware
async def ip_rate_limit_middleware(request: web.Request, handler):
    """Global per-IP rate limit for public/auth endpoints (DoS / brute-force)."""
    path = request.path or ""
    # Skip health probes
    if path in {"/health", "/ready"}:
        return await handler(request)
    try:
        from b2b_platform.rate_limit import get_rate_limiter
        limit = int(os.getenv("API_IP_RPM") or "120")
        if limit > 0:
            ip = _client_ip(request)
            key = f"ip:{ip}"
            # Authenticated tenants get a tenant bucket as well as the IP
            # bucket, preventing a shared proxy from collapsing all users.
            try:
                tenant = getattr(request, "tenant", None)
                if tenant and getattr(tenant, "tenant_id", None):
                    key = f"tenant:{tenant.tenant_id}"
                else:
                    auth = (request.headers.get("Authorization") or "").strip()
                    if auth:
                        digest = hashlib.sha256(auth.encode("utf-8")).hexdigest()[:32]
                        key = f"auth:{digest}"
            except Exception:
                pass
            lim = get_rate_limiter()
            if not lim.allow(key, limit=limit, window_sec=60.0):
                retry = lim.seconds_until_allow(key, limit=limit, window_sec=60.0)
                return web.json_response(
                    {"ok": False, "error": "ip_rate_limited", "retry_after": retry},
                    status=429,
                    headers={"Retry-After": str(retry)},
                )
            # Tighter limit on tenant creation (credential stuffing / spam tenants)
            if path == "/v1/tenants" and request.method == "POST":
                tlimit = int(os.getenv("API_TENANT_CREATE_RPM") or "5")
                tkey = f"ip_tenant:{ip}"
                if tlimit > 0 and not lim.allow(tkey, limit=tlimit, window_sec=60.0):
                    retry = lim.seconds_until_allow(tkey, limit=tlimit, window_sec=60.0)
                    return web.json_response(
                        {"ok": False, "error": "tenant_create_rate_limited", "retry_after": retry},
                        status=429,
                        headers={"Retry-After": str(retry)},
                    )
    except Exception:
        logger.exception("ip_rate_limit_middleware failure")
        env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "production").strip().lower()
        is_dev = env in {"dev", "development", "local", "test"}
        if not is_dev:
            # Production fail-closed for THIS request — never MemoryRateLimiter (multi-worker hole)
            # and never allow the request through unthrottled.
            return web.json_response(
                {"ok": False, "error": "rate_limit_unavailable"},
                status=503,
                headers={"Retry-After": "5"},
            )
        # Dev only: process-local limiter
        try:
            from b2b_platform.rate_limit import MemoryRateLimiter
            emergency = getattr(ip_rate_limit_middleware, "_emergency_limiter", None)
            if emergency is None:
                emergency = MemoryRateLimiter()
                ip_rate_limit_middleware._emergency_limiter = emergency  # type: ignore[attr-defined]
            ip = _client_ip(request)
            limit = int(os.getenv("API_IP_RPM") or "60")
            if limit > 0 and not emergency.allow(f"ip:{ip}", limit=limit, window_sec=60.0):
                return web.json_response(
                    {"ok": False, "error": "ip_rate_limited", "retry_after": 30},
                    status=429,
                    headers={"Retry-After": "30"},
                )
        except Exception:
            logger.exception("dev emergency rate limiter failed; allowing once")
    return await handler(request)


def create_app() -> web.Application:
    from b2b_platform.runtime_config import require_production_data_plane, is_dev
    if not is_dev():
        require_production_data_plane()
    # client_max_size: hard cap on request body (default 256 KiB)
    max_size = int(os.getenv("API_CLIENT_MAX_SIZE") or str(256 * 1024))
    try:
        from bot_interface.sanitize import install_secret_log_filter
        install_secret_log_filter()
    except Exception:
        pass
    app = web.Application(
        middlewares=[
            error_middleware,
            body_size_guard_middleware,
            json_body_middleware,
            ip_rate_limit_middleware,
            cors_middleware,
        ],
        client_max_size=max(4096, max_size),
    )
    app.router.add_get("/health", health.health)

    # OpenAPI / Swagger for B2B developers
    async def _openapi_yaml(request):
        from pathlib import Path as _P
        path = _P(__file__).resolve().parent / "openapi.yaml"
        return web.Response(text=path.read_text(encoding="utf-8"), content_type="application/yaml")

    async def _swagger_ui(request):
        html = """<!DOCTYPE html>
<html><head><title>Maestro API</title>
<link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
</head><body>
<div id="swagger-ui"></div>
<script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>
SwaggerUIBundle({ url: '/openapi.yaml', dom_id: '#swagger-ui' });
</script>
</body></html>"""
        return web.Response(text=html, content_type="text/html")

    app.router.add_get("/openapi.yaml", _openapi_yaml)
    app.router.add_get("/docs", _swagger_ui)
    app.router.add_get("/swagger", _swagger_ui)

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
    app.router.add_get("/v1/billing/balance", billing.balance_status)
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
