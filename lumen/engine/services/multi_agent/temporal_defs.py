"""Official Temporal.io workflow + activities — production path for generation.

Worker: python -m lumen.engine.services.multi_agent.temporal_worker
Env: TEMPORAL_HOST, TEMPORAL_NAMESPACE, TEMPORAL_TASK_QUEUE

The workflow ALWAYS runs run_generate_activity (LangGraph orchestrator), not
signal-only bookkeeping. Signals still support pause/cancel/steer.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

try:
    from temporalio import activity, workflow
    from temporalio.common import RetryPolicy
except ImportError:  # pragma: no cover
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

    @activity.defn(name="lumen_run_generate")
    async def run_generate_activity(data: dict[str, Any]) -> dict[str, Any]:
        """Primary activity: full multi-agent generate via LangGraph orchestrator."""
        import asyncio
        from pathlib import Path

        request = str(data.get("request") or data.get("description") or data.get("user_text") or "")
        work_dir = str(data.get("work_dir") or "")
        user_id = int(data.get("user_id") or 0)
        preferred = data.get("preferred_keys")
        if not request.strip():
            return {"ok": False, "error": "empty_request"}
        if not work_dir:
            return {"ok": False, "error": "missing_work_dir"}
        Path(work_dir).mkdir(parents=True, exist_ok=True)

        def _run():
            import os as _os
            _os.environ["LUMEN_INSIDE_TEMPORAL_ACTIVITY"] = "1"
            _os.environ["LUMEN_GENERATE_VIA_TEMPORAL"] = "0"
            from .orchestrator import orchestrate_generate

            return orchestrate_generate(
                request,
                work_dir,
                user_id=user_id,
                preferred_keys=list(preferred) if isinstance(preferred, list) else None,
                spec_request=str(data.get("spec_request") or request),
            )

        # Activity must not block the event loop
        result = await asyncio.to_thread(_run)
        success = bool(getattr(result, "success", False))
        path = str(getattr(result, "project_path", None) or getattr(result, "path", None) or "")
        errors = list(getattr(result, "errors", None) or [])
        meta = dict(getattr(result, "metadata", None) or {})
        return {
            "ok": success,
            "success": success,
            "project_path": path[:1000],
            "errors": [str(e)[:300] for e in errors[:20]],
            "metadata": {
                k: meta[k]
                for k in list(meta.keys())[:30]
                if isinstance(meta.get(k), (str, int, float, bool, type(None)))
            },
            "orchestration": meta.get("multi_agent", {}).get("extensions", {}).get("orchestration")
            if isinstance(meta.get("multi_agent"), dict)
            else meta.get("orchestration"),
        }

    @activity.defn(name="lumen_resume_generate")
    async def resume_generate_activity(data: dict[str, Any]) -> dict[str, Any]:
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
        """Runs generate activity under Temporal; survives worker crash/restart."""

        def __init__(self) -> None:
            self._step = "start"
            self._status = "running"
            self._done = False
            self._cancelled = False
            self._last_payload: dict[str, Any] = {}
            self._steer: str = ""

        @workflow.run
        async def run(self, data: dict[str, Any]) -> dict[str, Any]:
            retry = RetryPolicy(maximum_attempts=3)
            long_retry = RetryPolicy(maximum_attempts=2)

            reg = await workflow.execute_activity(
                register_generate_job,
                {**data, "step": "start", "status": "running"},
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=retry,
            )
            self._step = "registered"
            workflow.logger.info("journal %s", reg.get("workflow_id"))

            if self._cancelled:
                self._status = "cancelled"
                self._done = True
                return {"ok": False, "status": "cancelled", "register": reg}

            # Crash recovery path
            if data.get("auto_resume") and data.get("state_id"):
                self._step = "resume"
                result = await workflow.execute_activity(
                    resume_generate_activity,
                    data,
                    start_to_close_timeout=timedelta(hours=2),
                    heartbeat_timeout=timedelta(minutes=5),
                    retry_policy=long_retry,
                )
                self._status = "done" if result.get("ok") else "failed"
                self._done = True
                self._last_payload = dict(result)
                return {"ok": bool(result.get("ok")), "step": self._step, "result": result, "register": reg}

            # PRIMARY: full generate (LangGraph inside orchestrate_generate)
            self._step = "generate"
            payload = dict(data)
            if self._steer:
                payload["request"] = f"{payload.get('request') or payload.get('description') or ''}\n\nSTEER: {self._steer}"
            result = await workflow.execute_activity(
                run_generate_activity,
                payload,
                start_to_close_timeout=timedelta(hours=4),
                heartbeat_timeout=timedelta(minutes=10),
                retry_policy=long_retry,
            )
            self._last_payload = dict(result)
            self._status = "done" if result.get("ok") else "failed"
            self._step = "finished"
            self._done = True

            await workflow.execute_activity(
                register_generate_job,
                {
                    **data,
                    "workflow_id": reg.get("workflow_id"),
                    "step": self._step,
                    "status": self._status,
                    "payload": {"result_ok": bool(result.get("ok")), "path": result.get("project_path")},
                },
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=retry,
            )
            return {
                "ok": bool(result.get("ok")),
                "step": self._step,
                "status": self._status,
                "result": result,
                "register": reg,
            }

        @workflow.signal(name="checkpoint")
        def checkpoint(self, data: dict[str, Any]) -> None:
            self._step = str(data.get("step") or self._step)
            self._status = str(data.get("status") or self._status)
            self._last_payload = dict(data.get("payload") or {})
            if self._status.lower() in {
                "done", "passed", "failed", "completed", "error", "cancelled",
            }:
                self._done = True

        @workflow.signal(name="cancel")
        def cancel(self) -> None:
            self._cancelled = True
            self._status = "cancelled"
            self._done = True

        @workflow.signal(name="steer")
        def steer(self, data: dict[str, Any]) -> None:
            self._steer = str((data or {}).get("message") or data or "")[:2000]

        @workflow.query(name="status")
        def status(self) -> dict[str, Any]:
            return {
                "step": self._step,
                "status": self._status,
                "done": self._done,
                "payload": self._last_payload,
                "steer": self._steer[:200],
            }


def workflow_classes() -> list:
    if workflow is None:
        return []
    return [LumenMultiAgentGenerateWorkflow]


def activity_fns() -> list:
    if activity is None:
        return []
    return [register_generate_job, run_generate_activity, resume_generate_activity]


__all__ = [
    "GenerateJobInput",
    "LumenMultiAgentGenerateWorkflow",
    "register_generate_job",
    "run_generate_activity",
    "resume_generate_activity",
    "workflow_classes",
    "activity_fns",
]
