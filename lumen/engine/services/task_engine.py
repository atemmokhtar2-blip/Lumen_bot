"""Tenant-scoped task facade with evidence-gated success.

This layer reuses the durable Redis/RQ JobRunner; it does not create a second
queue or persistence system. A task handler can only finish successfully when
it returns at least one concrete evidence item.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from lumen.platform.jobs import Job, JobRunner, get_job_runner

_KIND_RE = re.compile(r"^[a-z][a-z0-9_.-]{1,63}$")
_TASK_PREFIX = "lumen_task:"


class TaskNotFound(LookupError):
    """Raised when a task is absent or belongs to another tenant."""


class TaskEngine:
    """Tenant-isolated task API backed by Lumen's existing durable job runner."""

    def __init__(self, runner: JobRunner | None = None) -> None:
        self._runner = runner or get_job_runner()

    @staticmethod
    def _tenant(tenant_id: str) -> str:
        value = str(tenant_id or "").strip()
        if not value or len(value) > 128:
            raise ValueError("valid_tenant_id_required")
        return value

    @staticmethod
    def _kind(kind: str) -> str:
        value = str(kind or "").strip().lower()
        if not _KIND_RE.fullmatch(value):
            raise ValueError("invalid_task_kind")
        return value

    @staticmethod
    def _evidence(result: Any) -> list[dict[str, str]]:
        if not isinstance(result, dict):
            return []
        raw = result.get("evidence")
        if not isinstance(raw, list):
            return []
        evidence: list[dict[str, str]] = []
        for item in raw[:50]:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind") or "").strip()[:40]
            locator = str(item.get("locator") or "").strip()[:2048]
            if kind and locator:
                evidence.append({"kind": kind, "locator": locator})
        return evidence

    def register(self, kind: str, handler: Callable[[Job], dict[str, Any]]) -> None:
        """Register a task handler; successful output must include evidence."""
        task_kind = self._kind(kind)
        if not callable(handler):
            raise TypeError("task_handler_must_be_callable")

        def verified_handler(job: Job) -> dict[str, Any]:
            output = handler(job)
            if not isinstance(output, dict):
                return {"ok": False, "errors": ["invalid_handler_result"]}
            if output.get("ok") is False:
                return output
            evidence = self._evidence(output)
            if not evidence:
                return {
                    "ok": False,
                    "message": "verification_evidence_missing",
                    "errors": ["verification_evidence_missing"],
                }
            safe_output = dict(output)
            safe_output["ok"] = True
            safe_output["evidence"] = evidence
            safe_output["verified"] = True
            return safe_output

        self._runner.register(f"{_TASK_PREFIX}{task_kind}", verified_handler)

    def submit(
        self,
        *,
        tenant_id: str,
        kind: str,
        input_data: dict[str, Any],
        message: str = "queued",
    ) -> Job:
        tenant = self._tenant(tenant_id)
        task_kind = self._kind(kind)
        if not isinstance(input_data, dict):
            raise ValueError("task_input_must_be_object")
        return self._runner.enqueue(
            tenant_id=tenant,
            kind=f"{_TASK_PREFIX}{task_kind}",
            input_data=dict(input_data),
            message=str(message or "queued")[:200],
        )

    def get(self, *, tenant_id: str, task_id: str) -> Job:
        tenant = self._tenant(tenant_id)
        task = self._runner.store.get(str(task_id or "").strip())
        if not task or task.tenant_id != tenant or not task.kind.startswith(_TASK_PREFIX):
            raise TaskNotFound("task_not_found")
        return task

    def list(self, *, tenant_id: str, limit: int = 20) -> list[Job]:
        tenant = self._tenant(tenant_id)
        bounded_limit = max(1, min(100, int(limit)))
        return [
            task
            for task in self._runner.store.list_for_tenant(tenant, limit=bounded_limit)
            if task.kind.startswith(_TASK_PREFIX)
        ]

    def cancel(self, *, tenant_id: str, task_id: str) -> Job:
        task = self.get(tenant_id=tenant_id, task_id=task_id)
        updated = self._runner.cancel(task.job_id, tenant_id=task.tenant_id)
        if updated is None:
            raise TaskNotFound("task_not_found")
        return updated

    def pause(self, *, tenant_id: str, task_id: str) -> Job:
        task = self.get(tenant_id=tenant_id, task_id=task_id)
        updated = self._runner.pause(task.job_id, tenant_id=task.tenant_id)
        if updated is None:
            raise TaskNotFound("task_not_found")
        return updated

    def resume(self, *, tenant_id: str, task_id: str) -> Job:
        task = self.get(tenant_id=tenant_id, task_id=task_id)
        updated = self._runner.resume(task.job_id, tenant_id=task.tenant_id)
        if updated is None:
            raise TaskNotFound("task_not_found")
        return updated
