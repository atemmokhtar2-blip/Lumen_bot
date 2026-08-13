"""Job status polling endpoints."""
from __future__ import annotations

from aiohttp import web

from api.auth import require_tenant
from b2b_platform.jobs import get_job_runner


async def get_job(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    job_id = request.match_info.get("job_id") or ""
    job = get_job_runner().store.get(job_id)
    if not job or job.tenant_id != tenant.tenant_id:
        raise web.HTTPNotFound(
            text='{"error":"job_not_found"}',
            content_type="application/json",
        )
    return web.json_response({"ok": True, **job.public_dict()})


async def list_jobs(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    limit = int(request.rel_url.query.get("limit") or "20")
    jobs = get_job_runner().store.list_for_tenant(tenant.tenant_id, limit=min(limit, 100))
    return web.json_response(
        {"ok": True, "jobs": [j.public_dict() for j in jobs]},
    )
