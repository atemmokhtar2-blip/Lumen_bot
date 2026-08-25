"""API authentication helpers."""
from __future__ import annotations

import os

from aiohttp import web

from api.security import admin_token_matches
from b2b_platform.tenants import Tenant, get_tenant_store
from b2b_platform.billing import get_billing
from b2b_platform.metering import get_metering


def extract_bearer(request: web.Request) -> str:
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (request.headers.get("X-Api-Key") or "").strip()


def require_tenant(request: web.Request) -> Tenant:
    key = extract_bearer(request)
    if not key:
        try:
            from b2b_platform.security_events import client_ip, emit
            emit("auth.missing_api_key", severity="warning", ip=client_ip(request), path=str(request.path))
        except Exception:
            pass
        raise web.HTTPUnauthorized(text='{"error":"missing_api_key"}', content_type="application/json")
    tenant = get_tenant_store().authenticate(key)
    if not tenant:
        try:
            from b2b_platform.security_events import client_ip, emit
            emit(
                "auth.invalid_api_key",
                severity="warning",
                ip=client_ip(request),
                path=str(request.path),
                detail={"key_prefix": (key[:8] + "…") if len(key) > 8 else "short"},
            )
        except Exception:
            pass
        raise web.HTTPUnauthorized(text='{"error":"invalid_api_key"}', content_type="application/json")
    ok, reason = get_billing().enforce_api(tenant.tenant_id)
    if not ok:
        raise web.HTTPTooManyRequests(
            text=f'{{"error":"{reason}"}}',
            content_type="application/json",
        )
    get_metering().record(tenant.tenant_id, api_calls=1)
    request["tenant"] = tenant
    return tenant


def require_admin(request: web.Request) -> None:
    """Root gate for platform-admin operations (tenant bootstrap, etc.).

    Fail-closed: missing PLATFORM_ADMIN_TOKEN → 403.
    Wrong / missing X-Admin-Token → 401 (timing-safe compare).
    """
    admin = (os.getenv("PLATFORM_ADMIN_TOKEN") or "").strip()
    if not admin:
        try:
            from b2b_platform.security_events import client_ip, emit
            emit(
                "auth.admin_token_unset",
                severity="critical",
                ip=client_ip(request),
                path=str(request.path),
            )
        except Exception:
            pass
        raise web.HTTPForbidden(
            text='{"error":"admin_token_required","detail":"set PLATFORM_ADMIN_TOKEN"}',
            content_type="application/json",
        )
    provided = request.headers.get("X-Admin-Token") or ""
    if not admin_token_matches(provided, admin):
        try:
            from b2b_platform.security_events import client_ip, emit
            emit(
                "auth.admin_rejected",
                severity="critical",
                ip=client_ip(request),
                path=str(request.path),
                detail={"has_header": bool(provided)},
            )
        except Exception:
            pass
        raise web.HTTPUnauthorized(
            text='{"error":"admin_required"}',
            content_type="application/json",
        )
