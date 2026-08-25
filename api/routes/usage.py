"""Usage batch API — phase 2 telemetry ingest (no credit deduction)."""
from __future__ import annotations

from aiohttp import web

from api.auth import require_tenant
from api.security import safe_json_body
from b2b_platform.usage_batches import get_usage_batch_service


async def post_batch(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    body = await safe_json_body(request, required=True, max_bytes=65536)
    # Never trust tenant_id from body
    body.pop("tenant_id", None)
    result = get_usage_batch_service().ingest(tenant.tenant_id, body, source="api")
    if not result.ok:
        return web.json_response({"ok": False, "error": result.reason}, status=400)
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
                "status": b.status,
                "idempotency_key": b.idempotency_key,
            },
        },
        status=200 if result.replay else 201,
    )


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
                    "status": b.status,
                    "source": b.source,
                    "created_at": b.created_at,
                }
                for b in rows
            ],
        }
    )
