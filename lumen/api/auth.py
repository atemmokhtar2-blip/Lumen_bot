"""API authentication helpers."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time

from aiohttp import web

from lumen.api.security import admin_token_matches
from lumen.platform.tenants import Tenant, get_tenant_store
from lumen.platform.billing import get_billing
from lumen.platform.metering import get_metering


# ---------------------------------------------------------------------------
# Short-lived SSE tickets (root fix for API-key-in-query leak)
# ---------------------------------------------------------------------------

_SSE_TICKET_MAX_TTL = 900  # 15 minutes hard cap
_SSE_TICKET_DEFAULT_TTL = 300  # 5 minutes


def _sse_ticket_secret() -> bytes:
    """Key material for HMAC-signed SSE tickets.

    Prefers TBE_TOKEN_SECRET / API_KEY_PEPPER. Never falls back to the
    long-lived tenant API key itself. No hardcoded secrets remain.
    In pure dev, reuses the same auto-generated local pepper as API key hashing.
    """
    raw = (
        (os.getenv("TBE_TOKEN_SECRET") or "").strip()
        or (os.getenv("API_KEY_PEPPER") or "").strip()
        or (os.getenv("PLATFORM_ADMIN_TOKEN") or "").strip()
    )
    if raw:
        return hashlib.sha256(raw.encode("utf-8")).digest()
    # Pure dev fallback: reuse the tenants pepper mechanism (strong, persisted)
    try:
        from lumen.platform.tenants import _key_pepper
        return hashlib.sha256(_key_pepper()).digest()
    except Exception:
        env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "").strip().lower()
        if env in {"production", "prod", "staging"} or not env:
            raise RuntimeError(
                "TBE_TOKEN_SECRET or API_KEY_PEPPER required to mint/verify SSE tickets"
            )
        # Last resort for unit tests with no filesystem
        import secrets as _secrets
        return hashlib.sha256(_secrets.token_bytes(32)).digest()


def mint_sse_ticket(tenant_id: str, job_id: str, ttl_sec: int = _SSE_TICKET_DEFAULT_TTL) -> str:
    """Mint a short-lived, job-scoped ticket for EventSource auth.

    Format (urlsafe): base64url( tenant_id:job_id:exp . hmac_sha256 )
    The long-lived API key never appears in the EventSource URL.
    """
    tid = (tenant_id or "").strip()
    jid = (job_id or "").strip()
    if not tid or not jid:
        raise ValueError("tenant_id and job_id required")
    ttl = max(60, min(int(ttl_sec), _SSE_TICKET_MAX_TTL))
    exp = int(time.time()) + ttl
    payload = f"{tid}:{jid}:{exp}".encode("utf-8")
    sig = hmac.new(_sse_ticket_secret(), payload, hashlib.sha256).digest()
    token = base64.urlsafe_b64encode(payload + b"." + sig).decode("ascii").rstrip("=")
    return token


def verify_sse_ticket(ticket: str) -> tuple[str, str] | None:
    """Verify ticket. Returns (tenant_id, job_id) or None on any failure."""
    raw = (ticket or "").strip()
    if not raw or len(raw) > 512:
        return None
    try:
        # restore padding
        pad = "=" * (-len(raw) % 4)
        data = base64.urlsafe_b64decode(raw + pad)
        if b"." not in data:
            return None
        payload, sig = data.rsplit(b".", 1)
        expect = hmac.new(_sse_ticket_secret(), payload, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expect):
            return None
        parts = payload.decode("utf-8").split(":")
        if len(parts) != 3:
            return None
        tid, jid, exp_s = parts
        if int(exp_s) < int(time.time()):
            return None
        if not tid or not jid or len(jid) > 128 or ".." in jid or "/" in jid:
            return None
        return tid, jid
    except Exception:
        return None


def extract_bearer(request: web.Request) -> str:
    """Extract long-lived API key from Authorization / X-Api-Key headers only.

    Query-string API keys are deliberately NOT accepted (even on SSE paths).
    Use a short-lived SSE ticket obtained from POST /v1/jobs/{id}/events-ticket.
    """
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    header = (request.headers.get("X-Api-Key") or "").strip()
    if header:
        return header
    return ""


def require_tenant(request: web.Request) -> Tenant:
    key = extract_bearer(request)
    if not key:
        try:
            from lumen.platform.security_events import client_ip, emit
            emit("auth.missing_api_key", severity="warning", ip=client_ip(request), path=str(request.path))
        except Exception:
            pass
        raise web.HTTPUnauthorized(text='{"error":"missing_api_key"}', content_type="application/json")
    tenant = get_tenant_store().authenticate(key)
    if not tenant:
        try:
            from lumen.platform.security_events import client_ip, emit
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


def require_tenant_for_sse(request: web.Request, job_id: str) -> Tenant:
    """Authenticate an SSE /events request via short-lived ticket only.

    Root security property: the long-lived tenant API key never appears in
    the EventSource URL and therefore is never written to reverse-proxy logs.
    """
    ticket = (request.rel_url.query.get("ticket") or "").strip()
    if not ticket:
        try:
            from lumen.platform.security_events import client_ip, emit
            emit(
                "auth.missing_sse_ticket",
                severity="warning",
                ip=client_ip(request),
                path=str(request.path),
            )
        except Exception:
            pass
        raise web.HTTPUnauthorized(
            text='{"error":"missing_sse_ticket","detail":"obtain a ticket via POST /v1/jobs/{id}/events-ticket"}',
            content_type="application/json",
        )

    verified = verify_sse_ticket(ticket)
    if not verified:
        try:
            from lumen.platform.security_events import client_ip, emit
            emit(
                "auth.invalid_sse_ticket",
                severity="warning",
                ip=client_ip(request),
                path=str(request.path),
            )
        except Exception:
            pass
        raise web.HTTPUnauthorized(
            text='{"error":"invalid_or_expired_sse_ticket"}',
            content_type="application/json",
        )

    tid, ticket_job_id = verified
    if ticket_job_id != job_id:
        raise web.HTTPForbidden(
            text='{"error":"ticket_job_mismatch"}',
            content_type="application/json",
        )

    tenant = get_tenant_store().get(tid)
    if not tenant or not tenant.active:
        raise web.HTTPUnauthorized(
            text='{"error":"invalid_tenant"}',
            content_type="application/json",
        )

    ok, reason = get_billing().enforce_api(tenant.tenant_id)
    if not ok:
        raise web.HTTPTooManyRequests(
            text=f'{{"error":"{reason}"}}',
            content_type="application/json",
        )
    # Do not increment api_calls metering for the long-lived stream itself
    # (ticket mint already counted). Keep request context consistent.
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
            from lumen.platform.security_events import client_ip, emit
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
            from lumen.platform.security_events import client_ip, emit
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
