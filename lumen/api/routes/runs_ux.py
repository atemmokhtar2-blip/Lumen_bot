"""Phase E — UX helper endpoints: agent run reports + job file listing for diff."""
from __future__ import annotations

import os
from pathlib import Path

from aiohttp import web

from lumen.api.auth import require_tenant


async def list_agent_reports(request: web.Request) -> web.Response:
    """GET /v1/runs/agent-reports — recent multi-agent orchestration reports."""
    require_tenant(request)
    try:
        limit = min(50, max(1, int(request.rel_url.query.get("limit") or "20")))
    except ValueError:
        limit = 20
    try:
        from lumen.engine.services.multi_agent.run_report import recent_reports

        rows = recent_reports(limit=limit)
    except Exception as exc:
        return web.json_response({"ok": False, "error": type(exc).__name__, "reports": []})
    # redact heavy fields
    out = []
    for r in rows:
        out.append(
            {
                "state_id": r.get("state_id"),
                "status": r.get("status"),
                "attempts": r.get("attempts"),
                "qa_passed": r.get("qa_passed"),
                "build_success": r.get("build_success"),
                "generated_path": r.get("generated_path"),
                "findings_count": r.get("findings_count"),
                "cost": r.get("cost"),
                "trajectory": r.get("trajectory"),
                "written_at": r.get("written_at"),
                "errors": (r.get("errors") or [])[:8],
            }
        )
    return web.json_response({"ok": True, "reports": out})


async def job_diff_files(request: web.Request) -> web.Response:
    """GET /v1/jobs/{job_id}/files — list generated project files for diff UI."""
    tenant = require_tenant(request)
    job_id = (request.match_info.get("job_id") or "").strip()
    if not job_id or ".." in job_id or "/" in job_id:
        raise web.HTTPNotFound(text='{"error":"job_not_found"}', content_type="application/json")
    from lumen.api.ownership import assert_job_owned
    from lumen.platform.jobs import get_job_runner

    job = get_job_runner().store.get(job_id)
    assert_job_owned(job, tenant.tenant_id)
    result = dict(job.result or {})
    gen = str(result.get("generated_path") or result.get("project_path") or "").strip()
    if not gen or not Path(gen).is_dir():
        return web.json_response({"ok": True, "job_id": job_id, "files": [], "generated_path": gen or None})
    root = Path(gen).resolve()
    files = []
    import os
    import stat as _stat

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [
            d for d in dirnames
            if d not in {".git", "__pycache__", "node_modules", ".venv"}
            and not (Path(dirpath) / d).is_symlink()
        ]
        for name in filenames:
            if len(files) >= 80:
                break
            full = Path(dirpath) / name
            try:
                st = full.lstat()
            except OSError:
                continue
            if not _stat.S_ISREG(st.st_mode):
                continue
            try:
                rel = full.resolve().relative_to(root).as_posix()
            except ValueError:
                continue
            files.append({"path": rel, "size": int(st.st_size)})
        if len(files) >= 80:
            break
    return web.json_response({"ok": True, "job_id": job_id, "generated_path": str(root), "files": files})


async def job_file_content(request: web.Request) -> web.Response:
    """GET /v1/jobs/{job_id}/file?path=main.py — read one generated file (capped)."""
    tenant = require_tenant(request)
    job_id = (request.match_info.get("job_id") or "").strip()
    rel = (request.rel_url.query.get("path") or "").strip().lstrip("/")
    if not job_id or not rel or ".." in rel or rel.startswith("/"):
        raise web.HTTPBadRequest(text='{"error":"bad_path"}', content_type="application/json")
    from lumen.api.ownership import assert_job_owned
    from lumen.platform.jobs import get_job_runner

    job = get_job_runner().store.get(job_id)
    assert_job_owned(job, tenant.tenant_id)
    result = dict(job.result or {})
    gen = str(result.get("generated_path") or result.get("project_path") or "").strip()
    if not gen:
        raise web.HTTPNotFound(text='{"error":"no_generated_path"}', content_type="application/json")
    root = Path(gen).resolve()
    try:
        from lumen.engine.services.safe_fs import UnsafePathError, safe_open_under

        with safe_open_under(root, rel, "rb") as fh:
            data = fh.read(120_000)
    except UnsafePathError:
        raise web.HTTPForbidden(text='{"error":"path_escape"}', content_type="application/json")
    except FileNotFoundError:
        raise web.HTTPNotFound(text='{"error":"not_found"}', content_type="application/json")
    except OSError:
        raise web.HTTPNotFound(text='{"error":"not_found"}', content_type="application/json")
    text = data.decode("utf-8", errors="replace")
    return web.json_response({"ok": True, "path": rel, "content": text, "truncated": len(data) >= 120_000})
