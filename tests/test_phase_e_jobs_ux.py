"""Phase E — job cancel + web console presence."""
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


def test_jobs_module_defines_cancel_and_stream():
    # avoid importing lumen.api package (aiohttp) — read source
    src = (Path(__file__).resolve().parents[1] / "lumen" / "api" / "routes" / "jobs.py").read_text(encoding="utf-8")
    assert "async def cancel_job" in src
    assert "async def stream_job" in src
    assert "text/event-stream" in src


def test_web_package_manifest():
    pkg = Path(__file__).resolve().parents[1] / "web" / "package.json"
    assert pkg.is_file()
    text = pkg.read_text(encoding="utf-8")
    assert "next" in text
    assert (pkg.parent / "app" / "runs" / "page.tsx").is_file()
