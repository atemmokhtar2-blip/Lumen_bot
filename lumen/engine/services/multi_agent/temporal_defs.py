"""Official Temporal workflows + activities for Lumen multi-agent generate.

Phase A (2026 world-class):
  - Preferred path: Temporal LangGraph Plugin (per-node Activities)
  - Legacy path: single Activity wrapping run_langgraph_pipeline (fallback only)

Requires: pip install "temporalio[langgraph]>=1.27"
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

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
        """Marker activity for Temporal Event History (job start audit)."""
        return {
            "ok": True,
            "engine": "temporal_history_marker",
            "workflow_id": str(data.get("workflow_id") or ""),
            "state_id": str(data.get("state_id") or ""),
            "step": str(data.get("step") or ""),
            "status": str(data.get("status") or "running"),
        }

    @activity.defn(name="lumen_run_langgraph_generate")
    async def run_langgraph_generate_activity(data: dict[str, Any]) -> dict[str, Any]:
        """Legacy: entire LangGraph pipeline in one Activity (fallback only)."""
        import asyncio
        import os
        from pathlib import Path

        try:
            activity.heartbeat({"phase": "start", "state_id": str((data or {}).get("state_id") or "")})
        except Exception:
            pass

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
            state.extensions = {
                "work_dir": work_dir,
                "orchestration": "temporal_legacy+langgraph+cline",
                "durable_shell": "temporal",
            }
            try:
                activity.heartbeat({"phase": "langgraph_start", "state_id": state_id})
            except Exception:
                pass
            out = run_langgraph_pipeline(
                state,
                context={"work_dir": work_dir, "user_id": user_id},
                registry=get_registry(),
                board=get_blackboard(),
                thread_id=state_id,
            )
            try:
                activity.heartbeat({
                    "phase": "langgraph_done",
                    "state_id": out.state_id,
                    "status": out.status,
                    "qa_passed": bool(out.qa_passed),
                })
            except Exception:
                pass
            ok = bool(out.qa_passed) or str(out.status).upper() in {"PASSED", "DELIVERED"}
            return {
                "ok": ok,
                "status": out.status,
                "state_id": out.state_id,
                "generated_path": out.generated_path,
                "qa_passed": out.qa_passed,
                "attempts": out.attempts,
                "task_tree": (out.extensions or {}).get("task_tree_summary"),
                "swarm": (out.extensions or {}).get("swarm"),
                "state": out.to_dict(),
                "engine": "temporal_legacy_single_activity",
            }

        return await asyncio.to_thread(_run)

    @activity.defn(name="lumen_run_generate")
    async def run_generate_activity(data: dict[str, Any]) -> dict[str, Any]:
        return await run_langgraph_generate_activity(data)


if workflow is not None:

    @workflow.defn(name="LumenMultiAgentGenerateWorkflow")
    class LumenMultiAgentGenerateWorkflow:
        """Legacy workflow: one Activity runs full graph (kept for compatibility)."""

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
            return {"steer": dict(self._steer), "cancelled": self._cancelled, "engine": "legacy"}

        @workflow.run
        async def run(self, data: dict[str, Any]) -> dict[str, Any]:
            import os
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
                start_to_close_timeout=timedelta(hours=float(os.getenv("TEMPORAL_ACTIVITY_HOURS") or "24")),
                heartbeat_timeout=timedelta(minutes=int(os.getenv("TEMPORAL_HEARTBEAT_MINUTES") or "10")),
                retry_policy=retry,
            )
            return dict(result or {})

    @workflow.defn(name="LumenPluginGenerateWorkflow")
    class LumenPluginGenerateWorkflow:
        """World-class path: Temporal LangGraph Plugin — plan/work/critique/repair as Activities."""

        def __init__(self) -> None:
            self._steer: dict[str, Any] = {}
            self._cancelled = False
            self._hitl: dict[str, Any] = {}

        @workflow.signal
        def steer(self, payload: dict[str, Any]) -> None:
            self._steer = dict(payload or {})

        @workflow.signal
        def cancel(self) -> None:
            self._cancelled = True

        @workflow.signal
        def hitl_decision(self, payload: dict[str, Any]) -> None:
            self._hitl = dict(payload or {})

        @workflow.query
        def status_view(self) -> dict[str, Any]:
            return {
                "steer": dict(self._steer),
                "cancelled": self._cancelled,
                "hitl": dict(self._hitl),
                "engine": "temporal_langgraph_plugin",
            }

        @workflow.run
        async def run(self, data: dict[str, Any]) -> dict[str, Any]:
            import os
            import uuid
            from datetime import timedelta

            payload = dict(data or {})
            if self._cancelled:
                return {"ok": False, "status": "CANCELLED", "engine": "temporal_langgraph_plugin"}

            try:
                from temporalio.contrib.langgraph import graph
                from langgraph.checkpoint.memory import InMemorySaver
                from .temporal_plugin_graph import GRAPH_NAME

                state_id = str(payload.get("state_id") or uuid.uuid4().hex[:16])
                initial = {
                    "request": str(payload.get("request") or payload.get("description") or ""),
                    "work_dir": str(payload.get("work_dir") or ""),
                    "user_id": int(payload.get("user_id") or 0),
                    "preferred_keys": list(payload.get("preferred_keys") or []),
                    "state_id": state_id,
                    "agent": {},
                    "status": "PENDING",
                    "ok": False,
                    "error": "",
                    "attempts": 0,
                    "max_attempts": max(1, min(8, int(os.getenv("MULTI_AGENT_MAX_ATTEMPTS") or "4"))),
                    "hitl_decision": "",
                }
                app = graph(GRAPH_NAME).compile(checkpointer=InMemorySaver())
                config = {"configurable": {"thread_id": state_id}}
                result = await app.ainvoke(initial, config=config)
                agent = (result or {}).get("agent") or {}
                ok = bool((result or {}).get("ok")) or bool(agent.get("qa_passed"))
                return {
                    "ok": ok,
                    "status": str((result or {}).get("status") or agent.get("status") or ""),
                    "state_id": state_id,
                    "generated_path": agent.get("generated_path") if isinstance(agent, dict) else None,
                    "qa_passed": bool(agent.get("qa_passed")) if isinstance(agent, dict) else ok,
                    "attempts": int((result or {}).get("attempts") or agent.get("attempts") or 0),
                    "task_tree": (agent.get("extensions") or {}).get("task_tree_summary") if isinstance(agent, dict) else None,
                    "state": agent if isinstance(agent, dict) else {},
                    "engine": "temporal_langgraph_plugin",
                }
            except Exception as exc:
                workflow.logger.warning("plugin graph invoke failed: %s — legacy activity", type(exc).__name__)
                retry = RetryPolicy(
                    initial_interval=timedelta(seconds=2),
                    backoff_coefficient=2.0,
                    maximum_interval=timedelta(seconds=60),
                    maximum_attempts=2,
                )
                result = await workflow.execute_activity(
                    run_langgraph_generate_activity,
                    payload,
                    start_to_close_timeout=timedelta(hours=float(os.getenv("TEMPORAL_ACTIVITY_HOURS") or "24")),
                    heartbeat_timeout=timedelta(minutes=int(os.getenv("TEMPORAL_HEARTBEAT_MINUTES") or "10")),
                    retry_policy=retry,
                )
                out = dict(result or {})
                out["engine"] = out.get("engine") or "temporal_legacy_after_plugin_error"
                out["plugin_error"] = f"{type(exc).__name__}:{exc}"
                return out


def activity_fns() -> list[Callable[..., Any]]:
    if activity is None:
        return []
    return [register_generate_job, run_langgraph_generate_activity, run_generate_activity]


def workflow_classes() -> list[type]:
    if workflow is None:
        return []
    return [LumenMultiAgentGenerateWorkflow, LumenPluginGenerateWorkflow]


__all__ = [
    "GenerateJobInput",
    "LumenMultiAgentGenerateWorkflow",
    "LumenPluginGenerateWorkflow",
    "register_generate_job",
    "run_generate_activity",
    "run_langgraph_generate_activity",
    "activity_fns",
    "workflow_classes",
]
