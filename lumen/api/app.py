"""aiohttp application factory — B2B API + health."""
from __future__ import annotations

import hashlib
import logging
import os

from aiohttp import web

from lumen.api.routes import audit, billing, dashboard, generate, github_webhooks, health, hosts, jobs, tenants, usage, runs_ux, secrets

logger = logging.getLogger("lumen_api")

# Isolation: decide_isolation() only — do not mutate os.environ here.


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



def _apply_security_headers(resp: web.StreamResponse, request: web.Request) -> None:
    path = request.path or ""
    if path.startswith("/v1/") and path not in {"/v1/plans"}:
        resp.headers.setdefault("Cache-Control", "no-store")
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    resp.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
    )
    # ROOT: HSTS always in production — do not depend on X-Forwarded-Proto
    # (missing proxy header or SSL-strip must not drop HSTS).
    try:
        from lumen.platform.runtime_config import is_dev
        _prod = not is_dev()
    except Exception:
        _prod = (request.headers.get("X-Forwarded-Proto") or request.scheme or "").lower() == "https"
    if _prod:
        resp.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains; preload"
        )
    resp.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")


@web.middleware
async def security_headers_middleware(request: web.Request, handler):
    """OWASP headers + production HTTPS enforcement (redirect) and always-on HSTS."""
    try:
        from lumen.platform.runtime_config import is_dev
        prod = not is_dev()
    except Exception:
        prod = False
    if prod:
        proto = (request.headers.get("X-Forwarded-Proto") or request.scheme or "").lower()
        if proto != "https":
            # Force TLS — blocks cleartext credential capture after SSL-strip attempts
            https_url = request.url.with_scheme("https")
            raise web.HTTPPermanentRedirect(location=str(https_url))
    try:
        resp = await handler(request)
    except web.HTTPException as ex:
        _apply_security_headers(ex, request)
        raise
    _apply_security_headers(resp, request)
    return resp


def _apply_cors(resp: web.StreamResponse, request: web.Request) -> None:
    origin = _cors_origin_for(request)
    if origin:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Vary"] = "Origin"
        if origin != "*":
            resp.headers["Access-Control-Allow-Credentials"] = "true"
    resp.headers["Access-Control-Allow-Headers"] = (
        "Authorization, Content-Type, X-Api-Key, X-Admin-Token"
    )
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")


@web.middleware
async def cors_middleware(request: web.Request, handler):
    if request.method == "OPTIONS":
        resp = web.Response(status=204)
        _apply_cors(resp, request)
        return resp
    try:
        resp = await handler(request)
    except web.HTTPException as ex:
        _apply_cors(ex, request)
        raise
    _apply_cors(resp, request)
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
            from lumen.bot.sanitize import sanitize_error, install_secret_log_filter
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

    from lumen.api.security import (
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
        from lumen.platform.rate_limit import get_rate_limiter
        limit = int(os.getenv("API_IP_RPM") or "120")
        if limit > 0:
            ip = _client_ip(request)
            lim = get_rate_limiter()

            # --- Bucket 1: IP (ALWAYS checked, never skipped) ---
            # SECURITY (Vuln #2): The IP bucket is independent and mandatory.
            # An authenticated identity must NOT replace the IP key — that lets
            # a single attacker behind a proxy rotate tenants/tokens to bypass
            # the per-IP limit entirely (rate-limit bypass).
            ip_key = f"ip:{ip}"
            if not lim.allow(ip_key, limit=limit, window_sec=60.0):
                retry = lim.seconds_until_allow(ip_key, limit=limit, window_sec=60.0)
                return web.json_response(
                    {"ok": False, "error": "ip_rate_limited", "retry_after": retry},
                    status=429,
                    headers={"Retry-After": str(retry)},
                )

            # --- Bucket 2: authenticated identity (ADDITIONAL, not replacement) ---
            # When present, enforce a second independent bucket keyed by tenant or
            # auth-token digest. This prevents one tenant from consuming the entire
            # IP allowance shared across a proxy/NAT. Both buckets must pass.
            identity_key: str | None = None
            try:
                tenant = getattr(request, "tenant", None)
                if tenant and getattr(tenant, "tenant_id", None):
                    identity_key = f"tenant:{tenant.tenant_id}"
                else:
                    auth = (request.headers.get("Authorization") or "").strip()
                    if auth:
                        digest = hashlib.sha256(auth.encode("utf-8")).hexdigest()[:32]
                        identity_key = f"auth:{digest}"
            except Exception:
                pass
            if identity_key:
                if not lim.allow(identity_key, limit=limit, window_sec=60.0):
                    retry = lim.seconds_until_allow(identity_key, limit=limit, window_sec=60.0)
                    return web.json_response(
                        {"ok": False, "error": "identity_rate_limited", "retry_after": retry},
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
        # Fail closed: Redis is the sole rate-limit backend. No in-process Memory
        # fallback (multi-worker DoS hole). Return 503 so callers retry / ops alert.
        logger.exception("ip_rate_limit_middleware failure — refusing request")
        return web.json_response(
            {"ok": False, "error": "rate_limit_unavailable"},
            status=503,
            headers={"Retry-After": "5"},
        )
    return await handler(request)


def create_app() -> web.Application:
    # Log isolation posture (read-only) — never write os.environ.
    try:
        from lumen.engine.services.isolation_policy import decide_isolation
        d = decide_isolation()
        logger.info(
            "isolation_policy require_strong=%s allow_local=%s reason=%s",
            d.require_strong_isolation,
            d.allow_local,
            d.reason,
        )
        if d.allow_local and d.require_strong_isolation is False:
            logger.warning(
                "isolation_policy allows host LocalProcess (dev/single-tenant only)"
            )
    except Exception:
        logger.exception("isolation_policy snapshot failed")
    try:
        from lumen.platform.observability import setup_observability
        setup_observability(service_name=os.getenv("OTEL_SERVICE_NAME") or "lumen-api")
    except Exception:
        logger.exception("observability setup failed")
    from lumen.platform.runtime_config import require_production_data_plane, is_dev
    from lumen.platform.prod_security_gate import assert_production_security
    assert_production_security()
    if not is_dev():
        require_production_data_plane()
    else:
        # Dev still validates pepper shape if API_KEY_PEPPER is set (warn-only path is inside require)
        try:
            from lumen.platform.tenants import require_api_key_pepper
            require_api_key_pepper()
        except Exception:
            pass
    # client_max_size: hard cap on request body (default 256 KiB)
    max_size = int(os.getenv("API_CLIENT_MAX_SIZE") or str(256 * 1024))
    try:
        from lumen.bot.sanitize import install_secret_log_filter
        install_secret_log_filter()
    except Exception:
        pass
    _mws = [
        error_middleware,
        body_size_guard_middleware,
        json_body_middleware,
        ip_rate_limit_middleware,
        security_headers_middleware,
        cors_middleware,
    ]
    try:
        from lumen.platform.observability.metrics_http import instrument_app_middleware
        _prom_mw = instrument_app_middleware()
        if _prom_mw is not None:
            _mws.insert(0, _prom_mw)
    except Exception:
        logger.exception("prometheus middleware skipped")
    app = web.Application(
        middlewares=_mws,
        client_max_size=max(4096, max_size),
    )
    app.router.add_get("/health", health.health)
    app.router.add_get("/health/cost-stack", health.cost_stack)

    # OpenAPI + interactive docs (Swagger UI + Redoc) for B2B developers
    async def _openapi_yaml(request):
        from pathlib import Path as _P
        path = _P(__file__).resolve().parent / "openapi.yaml"
        return web.Response(
            text=path.read_text(encoding="utf-8"),
            content_type="application/yaml",
            headers={"Cache-Control": "public, max-age=60"},
        )

    async def _swagger_ui(request):
        # Pinned Swagger UI 5.x from unpkg (standard vendor distribution)
        html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Lumen B2B API</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5.17.14/swagger-ui.css"/>
  <style>body{margin:0} .topbar{display:none}</style>
</head>
<body>
<div id="swagger-ui"></div>
<script src="https://unpkg.com/swagger-ui-dist@5.17.14/swagger-ui-bundle.js" crossorigin></script>
<script src="https://unpkg.com/swagger-ui-dist@5.17.14/swagger-ui-standalone-preset.js" crossorigin></script>
<script>
window.ui = SwaggerUIBundle({
  url: '/openapi.yaml',
  dom_id: '#swagger-ui',
  deepLinking: true,
  presets: [SwaggerUIBundle.presets.apis, SwaggerUIStandalonePreset],
  layout: 'StandaloneLayout',
  tryItOutEnabled: true,
  persistAuthorization: true
});
</script>
</body></html>"""
        return web.Response(text=html, content_type="text/html")

    async def _redoc_ui(request):
        html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Lumen API Reference</title>
  <style>body{margin:0;padding:0}</style>
</head>
<body>
  <redoc spec-url="/openapi.yaml" hide-hostname="false" expand-responses="200,201"></redoc>
  <script src="https://cdn.redoc.ly/redoc/v2.1.5/bundles/redoc.standalone.js"></script>
</body></html>"""
        return web.Response(text=html, content_type="text/html")

    async def _metrics(request):
        """Prometheus scrape endpoint — requires METRICS_TOKEN or admin token.

        Open metrics leak process/tenant cardinality and enable targeted attacks.
        """
        import hmac as _hmac
        expected = (
            (os.getenv("METRICS_TOKEN") or "").strip()
            or (os.getenv("PLATFORM_ADMIN_TOKEN") or "").strip()
        )
        if not expected:
            return web.Response(text="metrics_disabled\n", status=404)
        auth = (request.headers.get("Authorization") or "").strip()
        got = ""
        if auth.lower().startswith("bearer "):
            got = auth[7:].strip()
        elif request.headers.get("X-Metrics-Token"):
            got = (request.headers.get("X-Metrics-Token") or "").strip()
        if not got or not _hmac.compare_digest(got, expected):
            return web.Response(text="unauthorized\n", status=401)
        try:
            from lumen.platform.observability.metrics_http import metrics_payload, prometheus_available
            if not prometheus_available():
                return web.Response(text="prometheus_client not installed\n", status=501)
            body, ctype = metrics_payload()
            return web.Response(body=body, content_type=ctype)
        except Exception as exc:
            return web.Response(text=f"metrics_unavailable:{type(exc).__name__}\n", status=503)

    app.router.add_get("/openapi.yaml", _openapi_yaml)
    app.router.add_get("/docs", _swagger_ui)
    app.router.add_get("/swagger", _swagger_ui)
    app.router.add_get("/redoc", _redoc_ui)
    app.router.add_get("/metrics", _metrics)

    app.router.add_get("/ready", health.ready)
    # Public
    app.router.add_get("/v1/plans", tenants.list_plans)
    app.router.add_post("/v1/tenants", tenants.create_tenant)
    app.router.add_post("/v1/billing/webhook/stripe", billing.stripe_webhook)
    app.router.add_post("/v1/integrations/github/webhook", github_webhooks.github_webhook)
    # Real consumer for GitHub PR webhooks (not emit-only)
    try:
        from lumen.engine.services.integrations.github.pr_agent import register_event_handlers
        register_event_handlers()
    except Exception:
        logging.getLogger(__name__).exception("github pr_agent register failed")

    app.router.add_get("/v1/billing/checkout/success", billing.checkout_success)
    app.router.add_get("/v1/billing/checkout/cancel", billing.checkout_cancel)
    # Authenticated
    app.router.add_post("/v1/telegram/secrets", secrets.submit_telegram_secret)
    app.router.add_post("/v1/telegram/secrets/status", secrets.secret_status)
    app.router.add_get("/v1/me", tenants.me)
    app.router.add_post("/v1/me/rotate_key", tenants.rotate_key)
    app.router.add_patch("/v1/me/white-label", tenants.update_white_label)
    app.router.add_post("/v1/generate", generate.generate)
    app.router.add_get("/v1/jobs/{job_id}", jobs.get_job)
    app.router.add_get("/v1/jobs", jobs.list_jobs)
    app.router.add_post("/v1/jobs/{job_id}/cancel", jobs.cancel_job)
    app.router.add_post("/v1/jobs/{job_id}/pause", jobs.pause_job)
    app.router.add_post("/v1/jobs/{job_id}/resume", jobs.resume_job)
    app.router.add_post("/v1/jobs/{job_id}/steer", jobs.steer_job)
    app.router.add_post("/v1/jobs/{job_id}/events-ticket", jobs.create_events_ticket)
    app.router.add_get("/v1/jobs/{job_id}/events", jobs.stream_job)
    app.router.add_get("/v1/jobs/{job_id}/files", runs_ux.job_diff_files)
    app.router.add_get("/v1/jobs/{job_id}/file", runs_ux.job_file_content)
    app.router.add_get("/v1/runs/agent-reports", runs_ux.list_agent_reports)
    app.router.add_post("/v1/hosts/start", hosts.host_start)
    from lumen.api.routes import host_webhooks
    app.router.add_post(
        "/v1/hooks/telegram/{instance_id}", host_webhooks.telegram_host_webhook
    )
    app.router.add_post("/v1/hosts/stop", hosts.host_stop)
    app.router.add_get("/v1/hosts", hosts.host_status)
    app.router.add_post("/v1/hosts/diagnose", hosts.host_diagnose)
    app.router.add_post("/v1/hosts/versions", hosts.host_list_versions)
    app.router.add_post("/v1/hosts/versions/restore", hosts.host_restore_version)
    app.router.add_post("/v1/hosts/logs", hosts.host_logs)
    app.router.add_post("/v1/hosts/redeploy", hosts.host_redeploy)
    app.router.add_post("/v1/hosts/delete", hosts.host_delete)
    from lumen.api.routes import projects_host as projects_host
    app.router.add_get("/v1/projects", projects_host.list_projects)
    app.router.add_post("/v1/projects", projects_host.project_start)
    app.router.add_get("/v1/projects/{id}/logs", projects_host.project_logs)
    app.router.add_post("/v1/projects/{id}/redeploy", projects_host.project_redeploy)
    app.router.add_post("/v1/projects/{id}/restart", projects_host.project_restart)
    app.router.add_post("/projects/{id}/restart", projects_host.project_restart)
    app.router.add_delete("/v1/projects/{id}", projects_host.project_delete)
    # Product paths (no version prefix) — same handlers
    app.router.add_get("/projects", projects_host.list_projects)
    app.router.add_post("/projects", projects_host.project_start)
    app.router.add_get("/projects/{id}/logs", projects_host.project_logs)
    app.router.add_post("/projects/{id}/redeploy", projects_host.project_redeploy)
    app.router.add_delete("/projects/{id}", projects_host.project_delete)
    app.router.add_get("/v1/usage", billing.usage)
    app.router.add_get("/v1/usage/cost", usage.cost_report)
    app.router.add_get("/v1/billing/balance", billing.balance_status)
    app.router.add_get("/v1/invoices", billing.invoices)
    app.router.add_post("/v1/invoices", billing.create_invoice)
    app.router.add_post("/v1/billing/checkout", billing.checkout)
    app.router.add_post("/v1/billing/credits/checkout", billing.credits_checkout)
    app.router.add_post("/v1/billing/portal", billing.portal)
    app.router.add_post("/v1/billing/dev/activate", billing.dev_activate)
    app.router.add_get("/v1/dashboard", dashboard.overview)
    # Phase 5 audit
    app.router.add_get("/v1/me/credits/ledger", audit.me_ledger)
    app.router.add_get("/v1/me/credits/reconcile", audit.me_reconcile)
    app.router.add_get("/v1/me/credits/overview", audit.me_overview)
    app.router.add_get("/v1/admin/credits/{tenant_id}/overview", audit.admin_tenant_overview)
    app.router.add_get("/v1/admin/credits/{tenant_id}/ledger", audit.admin_tenant_ledger)
    app.router.add_get("/v1/admin/credits/{tenant_id}/reconcile", audit.admin_tenant_reconcile)
    return app


def run_api(host: str | None = None, port: int | None = None) -> None:
    host = host or os.getenv("API_HOST", "0.0.0.0")
    port = int(port or os.getenv("API_PORT") or os.getenv("PORT") or 8080)
    app = create_app()
    logger.info("B2B API listening on %s:%s", host, port)
    web.run_app(app, host=host, port=port, print=lambda *a, **k: None)
