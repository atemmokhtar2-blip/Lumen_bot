from __future__ import annotations

from types import SimpleNamespace

import pytest

from lumen.engine.services.task_engine import TaskEngine, TaskNotFound


class FakeStore:
    def __init__(self):
        self.jobs = {}

    def get(self, task_id):
        return self.jobs.get(task_id)

    def list_for_tenant(self, tenant_id, *, limit=20):
        return [job for job in self.jobs.values() if job.tenant_id == tenant_id][:limit]


class FakeRunner:
    def __init__(self):
        self.store = FakeStore()
        self.handlers = {}

    def register(self, kind, handler):
        self.handlers[kind] = handler

    def enqueue(self, *, tenant_id, kind, input_data, message):
        job = SimpleNamespace(
            job_id="task_1", tenant_id=tenant_id, kind=kind,
            input=input_data, message=message, status="queued",
        )
        self.store.jobs[job.job_id] = job
        return job

    def cancel(self, task_id, *, tenant_id):
        job = self.store.get(task_id)
        return job if job and job.tenant_id == tenant_id else None

    pause = cancel
    resume = cancel


def test_task_handler_requires_concrete_evidence():
    runner = FakeRunner()
    engine = TaskEngine(runner)
    engine.register("research", lambda job: {"ok": True, "summary": "done"})
    handler = runner.handlers["lumen_task:research"]

    result = handler(SimpleNamespace())

    assert result["ok"] is False
    assert result["errors"] == ["verification_evidence_missing"]


def test_task_handler_marks_evidence_backed_result_verified():
    runner = FakeRunner()
    engine = TaskEngine(runner)
    engine.register(
        "research",
        lambda job: {
            "ok": True,
            "summary": "done",
            "evidence": [{"kind": "source", "locator": "https://example.com/report"}],
        },
    )

    result = runner.handlers["lumen_task:research"](SimpleNamespace())

    assert result["ok"] is True
    assert result["verified"] is True
    assert result["evidence"] == [
        {"kind": "source", "locator": "https://example.com/report"}
    ]


def test_task_lookup_is_tenant_scoped():
    runner = FakeRunner()
    engine = TaskEngine(runner)
    engine.submit(tenant_id="tenant-a", kind="research", input_data={})

    assert engine.get(tenant_id="tenant-a", task_id="task_1").tenant_id == "tenant-a"
    with pytest.raises(TaskNotFound):
        engine.get(tenant_id="tenant-b", task_id="task_1")


def test_invalid_task_kind_is_rejected():
    engine = TaskEngine(FakeRunner())

    with pytest.raises(ValueError, match="invalid_task_kind"):
        engine.submit(tenant_id="tenant-a", kind="../admin", input_data={})
