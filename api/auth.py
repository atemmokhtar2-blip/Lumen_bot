"""API authentication helpers."""
from __future__ import annotations

from aiohttp import web

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
        raise web.HTTPUnauthorized(text='{"error":"missing_api_key"}', content_type="application/json")
    tenant = get_tenant_store().authenticate(key)
    if not tenant:
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
