"""Official Temporal workflow + activities wrapping LangGraph + Cline."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

try:
    from temporalio import activity, workflow
    from temporalio.common import RetryPolicy
except Exception:
    activity = None  # type: ignore
    workflow = None  # type: ignore
    RetryPolicy = None  # type: ignore


@dataclass
class GenerateJobInput:
    state_id: str = ""
    user_id: int = 0
    description: str = ""
    work_dir: str = ""
    preferred_keys: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)
    workflow_id: str = ""


if activity is not None:

    @activity.defn(name="lumen_register_generate_job")
    async def register_generate_job(data: dict[str, Any]) -> dict[str, Any]:
        JournalEntry = None  # durable_workflow removed; Temporal workflow is source of truth
        get_journal = None
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

    @activity.defn(name="lumen_run_langgraph_generate")
    async def run_langgraph_generate_activity(data: dict[str, Any]) -> dict[str, Any]:
        import asyncio
        import os
        from pathlib import Path

        def _run() -> dict[str, Any]:
            os.environ["LUMEN_INSIDE_TEMPORAL_ACTIVITY"] = "1"
            from .state import AgentState, AgentStatus
            from .langgraph_pipeline import run_langgraph_pipeline, langgraph_available
            from .blackboard import get_blackboard
            from .registry import get_registry
            import uuid

            if not langgraph_available():
                return {"ok": False, "error": "langgraph_not_installed", "status": "FAILED"}

            request = str(data.get("request") or data.get("description") or "")
            work_dir = str(data.get("work_dir") or "")
            user_id = int(data.get("user_id") or 0)
            preferred = [str(x) for x in (data.get("preferred_keys") or []) if str(x).strip()]
            state_id = str(data.get("state_id") or uuid.uuid4().hex[:16])
            if work_dir:
                Path(work_dir).mkdir(parents=True, exist_ok=True)

            state = AgentState(
                state_id=state_id,
                user_id=user_id,
                user_text=request,
                spec_request=request,
                preferred_keys=preferred,
                status=AgentStatus.PENDING.value,
            )
            state.extensions = {"work_dir": work_dir, "orchestration": "temporal+langgraph+cline"}
            out = run_langgraph_pipeline(
                state,
                context={"work_dir": work_dir, "user_id": user_id},
                registry=get_registry(),
                board=get_blackboard(),
                thread_id=state_id,
            )
            ok = bool(out.qa_passed) or str(out.status).upper() in {"PASSED", "DELIVERED"}
            return {
                "ok": ok,
                "status": out.status,
                "state_id": out.state_id,
                "generated_path": out.generated_path,
                "qa_passed": out.qa_passed,
                "attempts": out.attempts,
                "task_tree": (out.extensions or {}).get("task_tree_summary"),
                "state": out.to_dict(),
            }

        return await asyncio.to_thread(_run)

    @activity.defn(name="lumen_run_generate")
    async def run_generate_activity(data: dict[str, Any]) -> dict[str, Any]:
        return await run_langgraph_generate_activity(data)


if workflow is not None:

    @workflow.defn(name="LumenMultiAgentGenerateWorkflow")
    class LumenMultiAgentGenerateWorkflow:
        def __init__(self) -> None:
            self._steer: dict[str, Any] = {}
            self._cancelled = False

        @workflow.signal
        def steer(self, payload: dict[str, Any]) -> None:
            self._steer = dict(payload or {})

        @workflow.signal
        def cancel(self) -> None:
            self._cancelled = True

        @workflow.query
        def status_view(self) -> dict[str, Any]:
            return {"steer": dict(self._steer), "cancelled": self._cancelled}

        @workflow.run
        async def run(self, data: dict[str, Any]) -> dict[str, Any]:
            from datetime import timedelta
            payload = dict(data or {})
            retry = RetryPolicy(
                initial_interval=timedelta(seconds=2),
                backoff_coefficient=2.0,
                maximum_interval=timedelta(seconds=60),
                maximum_attempts=3,
            )
            await workflow.execute_activity(
                register_generate_job,
                {**payload, "step": "start", "status": "running"},
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=retry,
            )
            if self._cancelled:
                return {"ok": False, "status": "CANCELLED"}
            result = await workflow.execute_activity(
                run_langgraph_generate_activity,
                payload,
                start_to_close_timeout=timedelta(hours=2),
                heartbeat_timeout=timedelta(minutes=5),
                retry_policy=retry,
            )
            return dict(result or {})


__all__ = [
    "GenerateJobInput",
    "LumenMultiAgentGenerateWorkflow",
    "register_generate_job",
    "run_generate_activity",
    "run_langgraph_generate_activity",
]
