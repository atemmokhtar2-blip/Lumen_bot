"""B2B generate — enqueue heavy work, return task_id immediately."""
from __future__ import annotations

from aiohttp import web

from api.auth import require_tenant
from b2b_platform.billing import get_billing
from b2b_platform.jobs import get_job_runner
from b2b_platform.tenants import get_tenant_store


async def generate(request: web.Request) -> web.Response:
    """Enqueue generation job.

    Returns 202 + job_id. Client polls GET /v1/jobs/{job_id}.
    Optional query/body flag wait=1 runs synchronously (dev only, discouraged).
    """
    tenant = require_tenant(request)
    ok, reason = get_billing().enforce_generation(tenant.tenant_id)
    if not ok:
        raise web.HTTPPaymentRequired(
            text=f'{{"error":"{reason}"}}',
            content_type="application/json",
        )

    body = await request.json()
    description = str(body.get("description") or body.get("prompt") or "").strip()
    if len(description) < 3:
        raise web.HTTPBadRequest(
            text='{"error":"description_required"}',
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
            __import__("os").getenv("JOB_SYNC_WAIT_SECONDS") or "300"
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
