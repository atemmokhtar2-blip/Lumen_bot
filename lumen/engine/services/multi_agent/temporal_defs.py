"""Official Temporal.io workflow + activity definitions for Phase B.

Requires: pip install temporalio
Worker: python -m lumen.engine.services.multi_agent.temporal_worker
Env: TEMPORAL_HOST, TEMPORAL_NAMESPACE, TEMPORAL_TASK_QUEUE
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

try:
    from temporalio import activity, workflow
    from temporalio.common import RetryPolicy
except ImportError:  # pragma: no cover - optional dep
    activity = None  # type: ignore
    workflow = None  # type: ignore
    RetryPolicy = None  # type: ignore


@dataclass
class GenerateJobInput:
    state_id: str
    user_id: int = 0
    description: str = ""
    work_dir: str = ""
    payload: dict | None = None


if activity is not None:

    @activity.defn(name="lumen_register_generate_job")
    async def register_generate_job(data: dict[str, Any]) -> dict[str, Any]:
        """Record job in durable journal (file + optional Redis)."""
        from .durable_workflow import JournalEntry, get_journal
        import uuid

        state_id = str(data.get("state_id") or "")
        wid = str(data.get("workflow_id") or f"twf-{uuid.uuid4().hex[:16]}")
        entry = JournalEntry(
            workflow_id=wid,
            state_id=state_id,
            step=str(data.get("step") or "start"),
            status=str(data.get("status") or "running"),
            user_id=int(data.get("user_id") or 0),
            description=str(data.get("description") or "")[:2000],
            attempts=int(data.get("attempts") or 0),
            payload=dict(data.get("payload") or {}),
        )
        get_journal().write(entry)
        return entry.to_dict()

    @activity.defn(name="lumen_resume_generate")
    async def resume_generate_activity(data: dict[str, Any]) -> dict[str, Any]:
        """Resume multi-agent generation from durable checkpoint after crash/429."""
        from .durable_workflow import resume_generate

        state_id = str(data.get("state_id") or "")
        if not state_id:
            return {"ok": False, "error": "missing_state_id"}
        try:
            state = resume_generate(state_id)
            if state is None:
                return {"ok": False, "error": "no_checkpoint"}
            return {
                "ok": True,
                "state_id": state.state_id,
                "status": state.status,
                "attempts": state.attempts,
                "qa_passed": bool(state.qa_passed),
                "generated_path": str(state.generated_path or "")[:500],
            }
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}


if workflow is not None:

    @workflow.defn(name="LumenMultiAgentGenerate")
    class LumenMultiAgentGenerateWorkflow:
        """Long-running generation tracked by Temporal; steps advanced via signals."""

        def __init__(self) -> None:
            self._step = "start"
            self._status = "running"
            self._done = False
            self._last_payload: dict[str, Any] = {}

        @workflow.run
        async def run(self, data: dict[str, Any]) -> dict[str, Any]:
            retry = RetryPolicy(maximum_attempts=3)
            reg = await workflow.execute_activity(
                register_generate_job,
                {**data, "step": "start", "status": "running"},
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=retry,
            )
            workflow.logger.info("registered journal %s", reg.get("workflow_id"))

            # Optionally run resume if requested (crash recovery path)
            if data.get("auto_resume") and data.get("work_dir"):
                result = await workflow.execute_activity(
                    resume_generate_activity,
                    data,
                    start_to_close_timeout=timedelta(hours=2),
                    heartbeat_timeout=timedelta(minutes=5),
                    retry_policy=RetryPolicy(maximum_attempts=5),
                )
                self._status = "done" if result.get("ok") else "failed"
                self._done = True
                return {"ok": bool(result.get("ok")), "step": self._step, "result": result, "register": reg}

            # Wait for external orchestrator checkpoints (signals) or timeout
            try:
                await workflow.wait_condition(lambda: self._done, timeout=timedelta(hours=6))
            except Exception:
                self._status = "timed_out"
            return {
                "ok": self._status in {"done", "passed", "completed"},
                "step": self._step,
                "status": self._status,
                "payload": self._last_payload,
                "register": reg,
            }

        @workflow.signal(name="checkpoint")
        def checkpoint(self, data: dict[str, Any]) -> None:
            self._step = str(data.get("step") or self._step)
            self._status = str(data.get("status") or self._status)
            self._last_payload = dict(data.get("payload") or {})
            if self._status.lower() in {
                "done",
                "passed",
                "failed",
                "completed",
                "error",
                "cancelled",
            }:
                self._done = True

        @workflow.query(name="status")
        def status(self) -> dict[str, Any]:
            return {
                "step": self._step,
                "status": self._status,
                "done": self._done,
                "payload": self._last_payload,
            }


def workflow_classes() -> list:
    if workflow is None:
        return []
    return [LumenMultiAgentGenerateWorkflow]


def activity_fns() -> list:
    if activity is None:
        return []
    return [register_generate_job, resume_generate_activity]


__all__ = [
    "GenerateJobInput",
    "LumenMultiAgentGenerateWorkflow",
    "register_generate_job",
    "resume_generate_activity",
    "workflow_classes",
    "activity_fns",
]
