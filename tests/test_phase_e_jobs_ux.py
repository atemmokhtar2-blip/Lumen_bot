"""Phase E — cancel, SSE auth path, UX routes, web pages."""
from __future__ import annotations

import os
from pathlib import Path


def test_job_runner_cancel():
    os.environ["ENVIRONMENT"] = "test"
    from lumen.platform.jobs import JobRunner, JobStore, STATUS_QUEUED, STATUS_CANCELLED
    import tempfile

    db = Path(tempfile.mkdtemp()) / "jobs.sqlite3"
    store = JobStore(db_path=db)
    runner = JobRunner(store=store)
    runner.register("noop", lambda job: {"ok": True})
    job = runner.enqueue(tenant_id="t1", kind="noop", input_data={})
    assert job.status == STATUS_QUEUED
    cancelled = runner.cancel(job.job_id, tenant_id="t1")
    assert cancelled is not None
    assert cancelled.status == STATUS_CANCELLED


def test_jobs_and_ux_route_sources():
    root = Path(__file__).resolve().parents[1]
    jobs = (root / "lumen" / "api" / "routes" / "jobs.py").read_text(encoding="utf-8")
    assert "async def cancel_job" in jobs
    assert "text/event-stream" in jobs
    ux = (root / "lumen" / "api" / "routes" / "runs_ux.py").read_text(encoding="utf-8")
    assert "list_agent_reports" in ux
    assert "job_diff_files" in ux
    assert "job_file_content" in ux
    auth = (root / "lumen" / "api" / "auth.py").read_text(encoding="utf-8")
    assert "api_key" in auth and "/events" in auth


def test_web_pages_exist():
    root = Path(__file__).resolve().parents[1] / "web"
    assert (root / "package.json").is_file()
    assert (root / "app" / "runs" / "page.tsx").is_file()
    assert (root / "app" / "agents" / "page.tsx").is_file()
    assert (root / "app" / "diff" / "page.tsx").is_file()
    api = (root / "lib" / "api.ts").read_text(encoding="utf-8")
    assert "subscribeJobEvents" in api
    assert "listAgentReports" in api
