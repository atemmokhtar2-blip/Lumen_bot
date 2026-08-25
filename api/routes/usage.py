"""Usage batch API — hardened phase 2 telemetry (no credit deduction)."""
from __future__ import annotations

from aiohttp import web

from api.auth import require_tenant
from api.security import safe_json_body
from b2b_platform.usage_batches import get_usage_batch_service, register_bot


async def post_batch(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    body = await safe_json_body(request, required=True, max_bytes=65536)
    body.pop("tenant_id", None)  # never trust client tenant
    result = get_usage_batch_service().ingest(
        tenant.tenant_id, body, source="api", require_ownership=True
    )
    if not result.ok:
        status = 429 if result.reason == "rate_limited" else 400
        if result.reason == "bot_not_registered_for_tenant":
            status = 403
        return web.json_response({"ok": False, "error": result.reason}, status=status)
    b = result.batch
    assert b is not None
    return web.json_response(
        {
            "ok": True,
            "replay": result.replay,
            "batch": {
                "batch_id": b.batch_id,
                "tenant_id": b.tenant_id,
                "bot_id": b.bot_id,
                "window_start": b.window_start,
                "window_end": b.window_end,
                "messages_processed": b.messages_processed,
                "llm_tokens_used": b.llm_tokens_used,
                "uptime_seconds": b.uptime_seconds,
                "ram_mb": b.ram_mb,
                "cpu_millicores": b.cpu_millicores,
                "status": b.status,
                "content_hash": b.content_hash,
                "idempotency_key": b.idempotency_key,
            },
        },
        status=200 if result.replay else 201,
    )


async def register_bot_route(request: web.Request) -> web.Response:
    """Register bot_id under the authenticated tenant (call on host start)."""
    tenant = require_tenant(request)
    body = await safe_json_body(request, required=True, max_bytes=4096)
    bot_id = str(body.get("bot_id") or "").strip()[:120]
    if not bot_id:
        return web.json_response({"ok": False, "error": "bot_id_required"}, status=400)
    register_bot(tenant.tenant_id, bot_id)
    return web.json_response({"ok": True, "tenant_id": tenant.tenant_id, "bot_id": bot_id})


async def list_batches(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    try:
        limit = min(200, max(1, int(request.rel_url.query.get("limit") or "50")))
    except ValueError:
        limit = 50
    status = str(request.rel_url.query.get("status") or "")
    rows = get_usage_batch_service().list_batches(tenant.tenant_id, limit=limit, status=status)
    return web.json_response(
        {
            "ok": True,
            "batches": [
                {
                    "batch_id": b.batch_id,
                    "bot_id": b.bot_id,
                    "window_start": b.window_start,
                    "window_end": b.window_end,
                    "messages_processed": b.messages_processed,
                    "llm_tokens_used": b.llm_tokens_used,
                    "uptime_seconds": b.uptime_seconds,
                    "ram_mb": b.ram_mb,
                    "cpu_millicores": b.cpu_millicores,
                    "status": b.status,
                    "source": b.source,
                    "content_hash": b.content_hash,
                    "created_at": b.created_at,
                }
                for b in rows
            ],
        }
    )


async def list_ratings(request: web.Request) -> web.Response:
    """List credit ratings for the authenticated tenant."""
    tenant = require_tenant(request)
    try:
        limit = min(200, max(1, int(request.rel_url.query.get("limit") or "50")))
    except ValueError:
        limit = 50
    from b2b_platform.rating_engine import get_rating_engine
    rows = get_rating_engine().list_ratings(tenant.tenant_id, limit=limit)
    return web.json_response({"ok": True, "ratings": rows})
