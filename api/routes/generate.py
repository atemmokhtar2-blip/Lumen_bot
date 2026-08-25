"""B2B generate — enqueue heavy work, return task_id immediately."""
from __future__ import annotations

import os

from aiohttp import web

from api.auth import require_tenant
from api.ownership import reject_identity_spoof
from b2b_platform.billing import get_billing
from b2b_platform.jobs import get_job_runner
from b2b_platform.rate_limit import get_rate_limiter
from b2b_platform.tenants import get_tenant_store

# Hard caps against memory DoS (env-overridable)
_MAX_DESCRIPTION = int(os.getenv("GENERATE_MAX_DESCRIPTION_CHARS") or "20000")
_MAX_BODY_BYTES = int(os.getenv("GENERATE_MAX_BODY_BYTES") or "65536")  # 64 KiB
_GEN_RPM = int(os.getenv("GENERATE_RPM") or "10")  # per-tenant generate RPM



_SAFE_ERROR_CODES = frozenset({
    "invalid_json", "payload_too_large", "description_required", "description_too_long",
    "job_input_too_large", "job_queue_full", "job_queue_tenant_full", "generation_denied",
    "unauthorized", "forbidden", "rate_limited", "internal_error",
    "backpressure", "docker_required",
})


def _safe_error_code(exc: BaseException, *, default: str = "internal_error") -> str:
    """Map exceptions to client-safe codes — never raw paths or messages."""
    raw = str(exc or "").strip()
    if not raw:
        return default
    # take prefix before colon for structured codes
    code = raw.split(":", 1)[0].strip()
    if code in _SAFE_ERROR_CODES:
        return code
    if raw in _SAFE_ERROR_CODES:
        return raw
    # known prefixes
    for prefix in ("backpressure", "dependency_scan", "llm_budget"):
        if raw.startswith(prefix) or code.startswith(prefix):
            return prefix
    return default


async def generate(request: web.Request) -> web.Response:
    """Enqueue generation job.

    Returns 202 + job_id. Client polls GET /v1/jobs/{job_id}.
    Optional query/body flag wait=1 runs synchronously (dev only, discouraged).
    """
    tenant = require_tenant(request)

    # Strict per-tenant generate rate limit (defense in depth beyond plan quotas)
    lim = get_rate_limiter()
    if not lim.allow(f"generate:{tenant.tenant_id}", limit=max(1, _GEN_RPM), window_sec=60.0):
        retry = lim.seconds_until_allow(
            f"generate:{tenant.tenant_id}", limit=max(1, _GEN_RPM), window_sec=60.0
        )
        raise web.HTTPTooManyRequests(
            text=f'{{"error":"generate_rate_limited","retry_after":{retry}}}',
            content_type="application/json",
            headers={"Retry-After": str(retry)},
        )

    # Body: RAW_BODY_PATHS — capped read + single root parser (no request.json()).
    ok, reason = get_billing().enforce_generation(tenant.tenant_id)
    if not ok:
        raise web.HTTPPaymentRequired(
            text=f'{{"error":"{reason}"}}',
            content_type="application/json",
        )

    from api.security import parse_json_object_bytes, read_capped_body

    try:
        raw = await read_capped_body(request, max_bytes=_MAX_BODY_BYTES)
        body = parse_json_object_bytes(raw, empty_ok=False)
    except ValueError as exc:
        code = _safe_error_code(exc, default="invalid_json")
        if code == "payload_too_large":
            raise web.HTTPRequestEntityTooLarge(
                max_size=_MAX_BODY_BYTES,
                actual_size=_MAX_BODY_BYTES + 1,
                text='{"error":"payload_too_large"}',
                content_type="application/json",
            )
        raise web.HTTPBadRequest(
            text=f'{{"error":"{code}"}}',
            content_type="application/json",
        )

    reject_identity_spoof(body, tenant_id=tenant.tenant_id)
    description = str(body.get("description") or body.get("prompt") or "").strip()
    if len(description) < 3:
        raise web.HTTPBadRequest(
            text='{"error":"description_required"}',
            content_type="application/json",
        )
    if len(description) > _MAX_DESCRIPTION:
        raise web.HTTPBadRequest(
            text=f'{{"error":"description_too_long","max":{_MAX_DESCRIPTION}}}',
            content_type="application/json",
        )

    wait = str(body.get("wait") or request.rel_url.query.get("wait") or "").lower() in {
        "1",
        "true",
        "yes",
    }

    runner = get_job_runner()
    try:
        job = runner.enqueue(
            tenant_id=tenant.tenant_id,
            kind="generate",
            input_data={
                "description": description,
                "brand": tenant.brand_name or tenant.name,
            },
            message="generation queued",
        )
    except ValueError as exc:
        code = _safe_error_code(exc, default="invalid_json")
        if code == "job_input_too_large":
            raise web.HTTPRequestEntityTooLarge(
                max_size=1024 * 1024,
                actual_size=1024 * 1024 + 1,
                text='{"error":"job_input_too_large"}',
                content_type="application/json",
            )
        raise web.HTTPBadRequest(
            text=f'{{"error":"{code}"}}',
            content_type="application/json",
        )
    except RuntimeError as exc:
        code = _safe_error_code(exc, default="internal_error")
        if code in {"job_queue_full", "job_queue_tenant_full", "backpressure"}:
            raise web.HTTPTooManyRequests(
                text=f'{{"error":"{code}"}}',
                content_type="application/json",
                headers={"Retry-After": "30"},
            )
        raise

    brand = tenant.brand_name or tenant.name
    if wait:
        # Sync wait is dev-only. Never block the aiohttp event loop with time.sleep.
        import asyncio
        from telegram_bot_engine.services.isolation_policy import is_multi_tenant, is_dev_environment

        if is_multi_tenant() and not is_dev_environment():
            return web.json_response(
                {
                    "ok": False,
                    "error": "sync_wait_disabled",
                    "detail": "wait=true is disabled in multi-tenant production; poll /v1/jobs/{id}",
                    "job_id": job.job_id,
                    "poll_url": f"/v1/jobs/{job.job_id}",
                },
                status=400,
            )

        deadline = asyncio.get_event_loop().time() + float(
            os.getenv("JOB_SYNC_WAIT_SECONDS") or "300"
        )
        while asyncio.get_event_loop().time() < deadline:
            cur = runner.store.get(job.job_id)
            if cur and cur.status in ("succeeded", "failed", "cancelled"):
                payload = cur.public_dict()
                payload["brand"] = brand
                status = 200 if cur.status == "succeeded" and cur.result.get("ok") else 422
                if cur.status == "failed":
                    status = 500
                return web.json_response(payload, status=status)
            await asyncio.sleep(0.5)
        return web.json_response(
            {"ok": False, "error": "sync_wait_timeout", "job_id": job.job_id},
            status=504,
        )

    return web.json_response(
        {
            "ok": True,
            "accepted": True,
            "job_id": job.job_id,
            "status": job.status,
            "brand": brand,
            "poll_url": f"/v1/jobs/{job.job_id}",
            "message": "Generation accepted. Poll job status until terminal.",
        },
        status=202,
    )
