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


async def cancel_job(request: web.Request) -> web.Response:
    """POST /v1/jobs/{job_id}/cancel — soft cancel non-terminal jobs."""
    tenant = require_tenant(request)
    job_id = (request.match_info.get("job_id") or "").strip()
    if not job_id or len(job_id) > 128 or ".." in job_id or "/" in job_id:
        raise web.HTTPNotFound(text='{"error":"job_not_found"}', content_type="application/json")
    runner = get_job_runner()
    job = runner.store.get(job_id)
    assert_job_owned(job, tenant.tenant_id)
    updated = runner.cancel(job_id, tenant_id=tenant.tenant_id)
    if not updated:
        raise web.HTTPNotFound(text='{"error":"job_not_found"}', content_type="application/json")
    data = updated.public_dict()
    data["input"] = {}
    return web.json_response({"ok": True, **data})


async def pause_job(request: web.Request) -> web.Response:
    """POST /v1/jobs/{job_id}/pause — cooperative pause (non-terminal)."""
    tenant = require_tenant(request)
    job_id = (request.match_info.get("job_id") or "").strip()
    if not job_id or len(job_id) > 128 or ".." in job_id or "/" in job_id:
        raise web.HTTPNotFound(text='{"error":"job_not_found"}', content_type="application/json")
    runner = get_job_runner()
    job = runner.store.get(job_id)
    assert_job_owned(job, tenant.tenant_id)
    updated = runner.pause(job_id, tenant_id=tenant.tenant_id)
    if not updated:
        raise web.HTTPNotFound(text='{"error":"job_not_found"}', content_type="application/json")
    data = updated.public_dict()
    data["input"] = {}
    return web.json_response({"ok": True, **data})


async def resume_job(request: web.Request) -> web.Response:
    """POST /v1/jobs/{job_id}/resume — resume a paused job."""
    tenant = require_tenant(request)
    job_id = (request.match_info.get("job_id") or "").strip()
    if not job_id or len(job_id) > 128 or ".." in job_id or "/" in job_id:
        raise web.HTTPNotFound(text='{"error":"job_not_found"}', content_type="application/json")
    runner = get_job_runner()
    job = runner.store.get(job_id)
    assert_job_owned(job, tenant.tenant_id)
    updated = runner.resume(job_id, tenant_id=tenant.tenant_id)
    if not updated:
        raise web.HTTPNotFound(text='{"error":"job_not_found"}', content_type="application/json")
    data = updated.public_dict()
    data["input"] = {}
    return web.json_response({"ok": True, **data})


async def stream_job(request: web.Request) -> web.StreamResponse:
    """GET /v1/jobs/{job_id}/events — Server-Sent Events progress stream (Phase E)."""
    import asyncio
    import json as _json
    import time as _time

    tenant = require_tenant(request)
    job_id = (request.match_info.get("job_id") or "").strip()
    if not job_id or len(job_id) > 128 or ".." in job_id or "/" in job_id:
        raise web.HTTPNotFound(text='{"error":"job_not_found"}', content_type="application/json")
    runner = get_job_runner()
    job = runner.store.get(job_id)
    assert_job_owned(job, tenant.tenant_id)

    resp = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
    await resp.prepare(request)

    # Longer default for long-running agent jobs; client can pass ?timeout=
    deadline = _time.time() + float(request.rel_url.query.get("timeout") or "600")
    last_sig = ""
    while _time.time() < deadline:
        job = runner.store.get(job_id)
        if not job:
            await resp.write(b"event: error\ndata: {\"error\":\"gone\"}\n\n")
            break
        assert_job_owned(job, tenant.tenant_id)
        payload = {
            "job_id": job.job_id,
            "kind": job.kind,
            "status": job.status,
            "progress": job.progress,
            "message": job.message,
            "error": job.error if job.status == "failed" else "",
            "ts": _time.time(),
        }
        sig = f"{job.status}:{job.progress}:{job.message}:{job.error}"
        if sig != last_sig:
            last_sig = sig
            line = f"event: job\ndata: {_json.dumps(payload, ensure_ascii=False)}\n\n"
            await resp.write(line.encode("utf-8"))
        if job.status in {"succeeded", "failed", "cancelled"}:
            done = _json.dumps({"ok": True, "status": job.status, "ts": _time.time()})
            await resp.write(f"event: done\ndata: {done}\n\n".encode("utf-8"))
            break
        await asyncio.sleep(0.5)
    return resp
