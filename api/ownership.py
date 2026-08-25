"""Tenant ownership & anti-IDOR primitives — fail closed.

World-class multi-tenant APIs do not trust body/query tenant_id.
Authenticated identity is the only authority.
"""
from __future__ import annotations

import re
from typing import Any, Mapping, Optional

from aiohttp import web

# Canonical tenant id: ten_<hex> (created by TenantStore) or legacy alphanumeric
_TENANT_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_\-.]{1,63}$")

# Keys that must never override the authenticated tenant
_SPOOF_KEYS = (
    "tenant_id",
    "tenant",
    "user_id",
    "owner_id",
    "account_id",
    "org_id",
)


def normalize_tenant_id(raw: str) -> str:
    tid = (raw or "").strip()
    if not tid or not _TENANT_ID_RE.match(tid):
        raise web.HTTPBadRequest(
            text='{"error":"invalid_tenant_id"}',
            content_type="application/json",
        )
    # Path-ish payloads never valid
    if ".." in tid or "/" in tid or "\\" in tid or "\x00" in tid:
        raise web.HTTPBadRequest(
            text='{"error":"invalid_tenant_id"}',
            content_type="application/json",
        )
    return tid


def reject_identity_spoof(
    body: Optional[Mapping[str, Any]],
    *,
    tenant_id: str,
) -> None:
    """Reject requests that try to act as another tenant via body fields.

    Raises HTTP 403 on mismatch. Ignores missing keys.
    """
    if not body or not isinstance(body, Mapping):
        return
    for key in _SPOOF_KEYS:
        if key not in body:
            continue
        claimed = body.get(key)
        if claimed is None or claimed == "":
            continue
        if str(claimed).strip() != str(tenant_id).strip():
            try:
                from b2b_platform.security_events import emit

                emit(
                    "idor.identity_spoof",
                    severity="critical",
                    tenant_id=tenant_id,
                    detail={"field": key, "claimed": str(claimed)[:80]},
                )
            except Exception:
                pass
            raise web.HTTPForbidden(
                text='{"error":"tenant_spoof_rejected"}',
                content_type="application/json",
            )


def assert_job_owned(job: Any, tenant_id: str) -> None:
    """Uniform 404 whether missing or cross-tenant (no existence oracle)."""
    if job is None or str(getattr(job, "tenant_id", "")) != str(tenant_id):
        raise web.HTTPNotFound(
            text='{"error":"job_not_found"}',
            content_type="application/json",
        )


def assert_host_owned(instance: Any, user_id: int) -> None:
    if instance is None or int(getattr(instance, "user_id", -1)) != int(user_id):
        raise web.HTTPNotFound(
            text='{"error":"instance_not_found"}',
            content_type="application/json",
        )
