"""Phase 5 — audit APIs (tenant self-service + admin)."""
from __future__ import annotations

from aiohttp import web

from api.auth import require_admin, require_tenant
from api.ownership import normalize_tenant_id
from b2b_platform.audit import ledger_audit, reconcile_tenant, tenant_overview
from b2b_platform.credits import get_credit_service


async def me_ledger(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    try:
        limit = min(200, max(1, int(request.rel_url.query.get("limit") or "50")))
    except ValueError:
        limit = 50
    type_f = str(request.rel_url.query.get("type") or "")
    data = ledger_audit(get_credit_service(), tenant.tenant_id, limit=limit, type_filter=type_f)
    return web.json_response({"ok": True, **data})


async def me_reconcile(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    data = reconcile_tenant(get_credit_service(), tenant.tenant_id)
    return web.json_response({"ok": True, **data})


async def me_overview(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    try:
        from b2b_platform.rating_engine import get_rating_engine
        from b2b_platform.balance_lifecycle import get_balance_lifecycle
        re = get_rating_engine()
        lc = get_balance_lifecycle()
    except Exception:
        re, lc = None, None
    data = tenant_overview(
        tenant.tenant_id,
        credit_service=get_credit_service(),
        rating_engine=re,
        lifecycle=lc,
    )
    return web.json_response({"ok": True, **data})


async def admin_tenant_overview(request: web.Request) -> web.Response:
    require_admin(request)
    tenant_id = normalize_tenant_id(str(request.match_info.get("tenant_id") or ""))
    try:
        limit = min(500, max(1, int(request.rel_url.query.get("limit") or "100")))
    except ValueError:
        limit = 100
    try:
        from b2b_platform.rating_engine import get_rating_engine
        from b2b_platform.balance_lifecycle import get_balance_lifecycle
        re = get_rating_engine()
        lc = get_balance_lifecycle()
    except Exception:
        re, lc = None, None
    data = tenant_overview(
        tenant_id,
        credit_service=get_credit_service(),
        rating_engine=re,
        lifecycle=lc,
        ledger_limit=limit,
    )
    return web.json_response({"ok": True, **data})


async def admin_tenant_ledger(request: web.Request) -> web.Response:
    require_admin(request)
    tenant_id = normalize_tenant_id(str(request.match_info.get("tenant_id") or ""))
    try:
        limit = min(500, max(1, int(request.rel_url.query.get("limit") or "100")))
    except ValueError:
        limit = 100
    type_f = str(request.rel_url.query.get("type") or "")
    data = ledger_audit(get_credit_service(), tenant_id, limit=limit, type_filter=type_f)
    return web.json_response({"ok": True, **data})


async def admin_tenant_reconcile(request: web.Request) -> web.Response:
    require_admin(request)
    tenant_id = normalize_tenant_id(str(request.match_info.get("tenant_id") or ""))
    data = reconcile_tenant(get_credit_service(), tenant_id)
    status = 200 if data.get("ok") else 409
    return web.json_response({"ok": bool(data.get("ok")), **data}, status=status)
