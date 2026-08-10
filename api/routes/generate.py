"""B2B generate endpoint — zero-AI generation + anti-hallucination."""
from __future__ import annotations

import asyncio
from pathlib import Path

from aiohttp import web

from api.auth import require_tenant
from b2b_platform.billing import get_billing
from b2b_platform.metering import get_metering
from b2b_platform.tenants import get_tenant_store


async def generate(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    ok, reason = get_billing().enforce_generation(tenant.tenant_id)
    if not ok:
        raise web.HTTPPaymentRequired(text=f'{{"error":"{reason}"}}', content_type="application/json")

    body = await request.json()
    description = str(body.get("description") or body.get("prompt") or "").strip()
    if len(description) < 3:
        raise web.HTTPBadRequest(text='{"error":"description_required"}', content_type="application/json")

    from telegram_bot_engine import generate_bot
    from telegram_bot_engine.services.user_sandbox import get_user_sandbox
    import os

    base = os.getenv("OUTPUT_DIR", "/tmp/generated")
    # Tenant-scoped sandbox (white-label isolation)
    work = get_user_sandbox(abs(hash(tenant.tenant_id)) % (10**9), base).new_project_dir(label="api")

    result = await asyncio.to_thread(generate_bot, description, str(work))
    success = bool(getattr(result, "success", False))
    meta = getattr(result, "metadata", None) or {}
    project_path = getattr(result, "project_path", None)
    errors = list(getattr(result, "errors", None) or [])

    # generation unit already reserved atomically in enforce_generation(reserve=True)
    get_metering().record(tenant.tenant_id, event="generate_completed")

    # White-label stamp
    brand = tenant.brand_name or tenant.name
    payload = {
        "ok": success,
        "tenant_id": tenant.tenant_id,
        "brand": brand,
        "project_path": project_path,
        "ready_for_token": bool(meta.get("ready_for_token")),
        "verified_commands": meta.get("verified_commands") or [],
        "anti_hallucination": meta.get("anti_hallucination") or {},
        "errors": errors,
        "metadata": {
            "engine": meta.get("engine"),
            "preset": meta.get("preset"),
            "zero_ai": True,
            "elapsed_ms": meta.get("elapsed_ms"),
        },
    }
    return web.json_response(payload, status=200 if success else 422)
