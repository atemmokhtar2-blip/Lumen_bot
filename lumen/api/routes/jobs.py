"""Job status polling endpoints — tenant ownership enforced."""
from __future__ import annotations

from aiohttp import web

from lumen.api.auth import require_tenant
from lumen.api.ownership import assert_job_owned
from lumen.platform.jobs import get_job_runner


async def get_job(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    job_id = (request.match_info.get("job_id") or "").strip()
    if not job_id or len(job_id) > 128 or ".." in job_id or "/" in job_id:
        raise web.HTTPNotFound(
            text='{"error":"job_not_found"}',
            content_type="application/json",
        )
    job = get_job_runner().store.get(job_id)
    assert_job_owned(job, tenant.tenant_id)
    # public_dict includes tenant_id of owner only (already verified)
    data = job.public_dict()
    # Never echo raw input payload on poll (may contain user secrets)
    data["input"] = {}
    return web.json_response({"ok": True, **data})


async def list_jobs(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    try:
        limit = min(100, max(1, int(request.rel_url.query.get("limit") or "20")))
    except ValueError:
        limit = 20
    jobs = get_job_runner().store.list_for_tenant(tenant.tenant_id, limit=limit)
    out = []
    for j in jobs:
        d = j.public_dict()
        d["input"] = {}
        out.append(d)
    return web.json_response({"ok": True, "jobs": out})
