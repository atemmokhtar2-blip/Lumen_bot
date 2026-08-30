"""Job status polling endpoints — presentation adapter.

Read paths go through application handlers (domain ownership rules).
Mutating job control still uses the job runner (infrastructure) until
dedicated commands exist for cancel/pause/resume/steer.
"""
from __future__ import annotations

from aiohttp import web

from lumen.api.auth import require_tenant, require_tenant_for_sse, mint_sse_ticket
from lumen.api.ownership import assert_job_owned
from lumen.application.commands.cancel_job import CancelJobCommand
from lumen.application.commands.pause_job import PauseJobCommand
from lumen.application.commands.resume_job import ResumeJobCommand
from lumen.application.handlers.job_handlers import (
    handle_cancel_job,
    handle_get_job,
    handle_pause_job,
    handle_resume_job,
)
from lumen.application.queries.get_job import GetJobQuery
from lumen.bootstrap import get_job_repository
from lumen.platform.jobs import get_job_runner


async def get_job(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    job_id = (request.match_info.get("job_id") or "").strip()
    if not job_id or len(job_id) > 128 or ".." in job_id or "/" in job_id:
        raise web.HTTPNotFound(
            text='{"error":"job_not_found"}',
            content_type="application/json",
        )
    try:
        job = handle_get_job(
            GetJobQuery(job_id=job_id, tenant_id=tenant.tenant_id),
            jobs=get_job_repository(),
        )
    except LookupError:
        raise web.HTTPNotFound(
            text='{"error":"job_not_found"}',
            content_type="application/json",
        )
    except PermissionError:
        raise web.HTTPForbidden(
            text='{"error":"job_not_owned"}',
            content_type="application/json",
        )
    data = job.public_dict()
    data["input"] = {}
    return web.json_response({"ok": True, **data})



async def list_jobs(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    try:
        limit = min(100, max(1, int(request.rel_url.query.get("limit") or "20")))
    except ValueError:
        limit = 20
    jobs = get_job_repository().list_for_tenant(tenant.tenant_id, limit=limit)
    out = []
    for j in jobs:
        d = j.public_dict()
        d["input"] = {}
        out.append(d)
    return web.json_response({"ok": True, "jobs": out})


async def cancel_job(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    job_id = (request.match_info.get("job_id") or "").strip()
    if not job_id or len(job_id) > 128 or ".." in job_id or "/" in job_id:
        raise web.HTTPNotFound(text='{"error":"job_not_found"}', content_type="application/json")
    try:
        updated = handle_cancel_job(
            CancelJobCommand(job_id=job_id, tenant_id=tenant.tenant_id),
            jobs=get_job_repository(),
        )
    except LookupError:
        raise web.HTTPNotFound(text='{"error":"job_not_found"}', content_type="application/json")
    except PermissionError:
        raise web.HTTPForbidden(text='{"error":"job_not_owned"}', content_type="application/json")
    data = updated.public_dict()
    data["input"] = {}
    return web.json_response({"ok": True, **data})



async def pause_job(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    job_id = (request.match_info.get("job_id") or "").strip()
    if not job_id or len(job_id) > 128 or ".." in job_id or "/" in job_id:
        raise web.HTTPNotFound(text='{"error":"job_not_found"}', content_type="application/json")
    try:
        updated = handle_pause_job(
            PauseJobCommand(job_id=job_id, tenant_id=tenant.tenant_id),
            jobs=get_job_repository(),
        )
    except LookupError:
        raise web.HTTPNotFound(text='{"error":"job_not_found"}', content_type="application/json")
    except PermissionError:
        raise web.HTTPForbidden(text='{"error":"job_not_owned"}', content_type="application/json")
    data = updated.public_dict()
    data["input"] = {}
    return web.json_response({"ok": True, **data})



async def resume_job(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    job_id = (request.match_info.get("job_id") or "").strip()
    if not job_id or len(job_id) > 128 or ".." in job_id or "/" in job_id:
        raise web.HTTPNotFound(text='{"error":"job_not_found"}', content_type="application/json")
    try:
        updated = handle_resume_job(
            ResumeJobCommand(job_id=job_id, tenant_id=tenant.tenant_id),
            jobs=get_job_repository(),
        )
    except LookupError:
        raise web.HTTPNotFound(text='{"error":"job_not_found"}', content_type="application/json")
    except PermissionError:
        raise web.HTTPForbidden(text='{"error":"job_not_owned"}', content_type="application/json")
    data = updated.public_dict()
    data["input"] = {}
    return web.json_response({"ok": True, **data})



async def steer_job(request: web.Request) -> web.Response:
    """POST /v1/jobs/{job_id}/steer — human steer instruction (Phase E).

    Body JSON: ``{"message": "..."}`` (required, max 2000 chars).
    """
    tenant = require_tenant(request)
    job_id = (request.match_info.get("job_id") or "").strip()
    if not job_id or len(job_id) > 128 or ".." in job_id or "/" in job_id:
        raise web.HTTPNotFound(text='{"error":"job_not_found"}', content_type="application/json")
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    message = body.get("message") if isinstance(body.get("message"), str) else ""
    message = message.strip()
    if not message:
        raise web.HTTPBadRequest(
            text='{"error":"message_required"}',
            content_type="application/json",
        )
    runner = get_job_runner()
    job = runner.store.get(job_id)
    assert_job_owned(job, tenant.tenant_id)
    updated = runner.steer(job_id, message, tenant_id=tenant.tenant_id)
    if not updated:
        raise web.HTTPBadRequest(
            text='{"error":"steer_rejected"}',
            content_type="application/json",
        )
    data = updated.public_dict()
    data["input"] = {}
    return web.json_response({"ok": True, **data})


async def create_events_ticket(request: web.Request) -> web.Response:
    """POST /v1/jobs/{job_id}/events-ticket — mint short-lived SSE ticket.

    Authenticated with the normal long-lived API key (headers only).
    The returned ticket is the only credential that may appear in the
    EventSource URL, preventing API-key leakage into access logs.
    """
    tenant = require_tenant(request)
    job_id = (request.match_info.get("job_id") or "").strip()
    if not job_id or len(job_id) > 128 or ".." in job_id or "/" in job_id:
        raise web.HTTPNotFound(text='{"error":"job_not_found"}', content_type="application/json")
    job = get_job_runner().store.get(job_id)
    assert_job_owned(job, tenant.tenant_id)
    try:
        ttl = int(request.rel_url.query.get("ttl") or "300")
    except ValueError:
        ttl = 300
    ticket = mint_sse_ticket(tenant.tenant_id, job_id, ttl_sec=ttl)
    return web.json_response({
        "ok": True,
        "ticket": ticket,
        "expires_in": max(60, min(ttl, 900)),
        "job_id": job_id,
    })


async def stream_job(request: web.Request) -> web.StreamResponse:
    """GET /v1/jobs/{job_id}/events — Server-Sent Events progress stream (Phase E).

    Auth: short-lived ticket only (query param ticket).
    Long-lived API keys are rejected here by design.
    """
    import asyncio
    import json as _json
    import time as _time

    job_id = (request.match_info.get("job_id") or "").strip()
    if not job_id or len(job_id) > 128 or ".." in job_id or "/" in job_id:
        raise web.HTTPNotFound(text='{"error":"job_not_found"}', content_type="application/json")
    tenant = require_tenant_for_sse(request, job_id)
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
        pub = job.public_dict()
        payload = {
            "job_id": job.job_id,
            "kind": job.kind,
            "status": job.status,
            "progress": job.progress,
            "message": job.message,
            "error": job.error if job.status == "failed" else "",
            "last_steer": pub.get("last_steer"),
            "ts": _time.time(),
        }
        sig = f"{job.status}:{job.progress}:{job.message}:{job.error}:{pub.get('last_steer')}"
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
