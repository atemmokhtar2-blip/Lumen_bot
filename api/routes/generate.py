"""B2B generate — enqueue heavy work, return task_id immediately."""
from __future__ import annotations

import os

from aiohttp import web

from api.auth import require_tenant
from b2b_platform.billing import get_billing
from b2b_platform.jobs import get_job_runner
from b2b_platform.rate_limit import get_rate_limiter
from b2b_platform.tenants import get_tenant_store

# Hard caps against memory DoS (env-overridable)
_MAX_DESCRIPTION = int(os.getenv("GENERATE_MAX_DESCRIPTION_CHARS") or "20000")
_MAX_BODY_BYTES = int(os.getenv("GENERATE_MAX_BODY_BYTES") or "65536")  # 64 KiB
_GEN_RPM = int(os.getenv("GENERATE_RPM") or "10")  # per-tenant generate RPM


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

    # Reject oversized bodies early (Content-Length when present)
    cl = request.headers.get("Content-Length")
    if cl and cl.isdigit() and int(cl) > _MAX_BODY_BYTES:
        raise web.HTTPRequestEntityTooLarge(
            text='{"error":"payload_too_large"}',
            content_type="application/json",
        )

    ok, reason = get_billing().enforce_generation(tenant.tenant_id)
    if not ok:
        raise web.HTTPPaymentRequired(
            text=f'{{"error":"{reason}"}}',
            content_type="application/json",
        )

    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(
            text='{"error":"invalid_json"}',
            content_type="application/json",
        )

    if not isinstance(body, dict):
        raise web.HTTPBadRequest(
            text='{"error":"body_must_be_object"}',
            content_type="application/json",
        )

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
    job = runner.enqueue(
        tenant_id=tenant.tenant_id,
        kind="generate",
        input_data={
            "description": description,
            "brand": tenant.brand_name or tenant.name,
        },
        message="generation queued",
    )

    brand = tenant.brand_name or tenant.name
    if wait:
        # Dev/sync path: block this request only (still on dedicated pool via future)
        import time

        deadline = time.time() + float(
            os.getenv("JOB_SYNC_WAIT_SECONDS") or "300"
        )
        while time.time() < deadline:
            cur = runner.store.get(job.job_id)
            if cur and cur.status in ("succeeded", "failed", "cancelled"):
                payload = cur.public_dict()
                payload["brand"] = brand
                status = 200 if cur.status == "succeeded" and cur.result.get("ok") else 422
                if cur.status == "failed":
                    status = 500
                return web.json_response(payload, status=status)
            time.sleep(0.5)
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
