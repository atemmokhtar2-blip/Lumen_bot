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
                start_to_close_timeout=timedelta(hours=24),
                heartbeat_timeout=timedelta(minutes=10),
                retry_policy=retry,
            )
            return dict(result or {})

    @workflow.defn(name="LumenPluginGenerateWorkflow")
    class LumenPluginGenerateWorkflow:
        """Official Temporal + LangGraph Plugin path (samples-python aligned).

        plan → (HITL interrupt + wait_condition) → work → critique ⇄ repair → deliver
        Each heavy node is a Temporal Activity via LangGraphPlugin metadata.
        """

        def __init__(self) -> None:
            self._steer: dict[str, Any] = {}
            self._cancelled = False
            self._human_input: str | None = None
            self._pending_interrupt: Any = None

        @workflow.signal
        def steer(self, payload: dict[str, Any]) -> None:
            self._steer = dict(payload or {})

        @workflow.signal
        def cancel(self) -> None:
            self._cancelled = True

        @workflow.signal
        def hitl_decision(self, payload: dict[str, Any] | str) -> None:
            """Signal: approve/reject plan (string or {decision: ...})."""
            if isinstance(payload, dict):
                self._human_input = str(
                    payload.get("decision") or payload.get("value") or payload.get("feedback") or ""
                )
            else:
                self._human_input = str(payload or "")

        # Alias used by some Temporal HITL clients
        @workflow.signal
        def provide_feedback(self, feedback: str) -> None:
            self._human_input = str(feedback or "")

        @workflow.query
        def status_view(self) -> dict[str, Any]:
            return {
                "steer": dict(self._steer),
                "cancelled": self._cancelled,
                "awaiting_hitl": self._human_input is None and self._pending_interrupt is not None,
                "pending_interrupt": self._pending_interrupt,
                "engine": "temporal_langgraph_plugin",
            }

        @workflow.query
        def get_pending_plan(self) -> Any:
            return self._pending_interrupt

        @workflow.run
        async def run(self, data: dict[str, Any]) -> dict[str, Any]:
            from datetime import timedelta

            payload = dict(data or {})
            if self._cancelled:
                return {"ok": False, "status": "CANCELLED", "engine": "temporal_langgraph_plugin"}

            try:
                # Official pattern: only temporal_graph + InMemorySaver inside workflow.
                # Graph implementation is registered on the Worker via LangGraphPlugin —
                # do NOT import temporal_plugin_graph here (sandbox + non-determinism).
                from temporalio.contrib.langgraph import graph as temporal_graph
                from langgraph.checkpoint.memory import InMemorySaver
                from langgraph.types import Command

                state_id = str(payload.get("state_id") or payload.get("workflow_id") or "lumen-state")
                max_attempts = int(payload.get("max_attempts") or 4)
                if max_attempts < 1:
                    max_attempts = 1
                if max_attempts > 8:
                    max_attempts = 8
                initial: dict[str, Any] = {
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
                    "max_attempts": max_attempts,
                    "plan_summary": "",
                }
                app = temporal_graph("lumen-generate").compile(checkpointer=InMemorySaver())
                config = {"configurable": {"thread_id": state_id}}

                # First invoke — may pause at plan_gate interrupt()
                result = await app.ainvoke(initial, config, version="v2")

                # Official HITL: if graph paused on interrupt, wait for Temporal signal
                interrupts = getattr(result, "interrupts", None) or []
                if interrupts:
                    self._pending_interrupt = getattr(interrupts[0], "value", interrupts[0])
                    await workflow.wait_condition(
                        lambda: self._human_input is not None or self._cancelled
                    )
                    if self._cancelled:
                        return {
                            "ok": False,
                            "status": "CANCELLED",
                            "state_id": state_id,
                            "engine": "temporal_langgraph_plugin",
                        }
                    result = await app.ainvoke(
                        Command(resume=self._human_input),
                        config,
                        version="v2",
                    )
                    self._pending_interrupt = None

                # result may be state dict or object with values
                if hasattr(result, "values") and isinstance(result.values, dict):
                    out_state = result.values
                elif isinstance(result, dict):
                    out_state = result
                else:
                    out_state = {}

                agent = out_state.get("agent") or {}
                ok = bool(out_state.get("ok")) or bool(
                    agent.get("qa_passed") if isinstance(agent, dict) else False
                )
                return {
                    "ok": ok,
                    "status": str(out_state.get("status") or (agent.get("status") if isinstance(agent, dict) else "") or ""),
                    "state_id": state_id,
                    "generated_path": agent.get("generated_path") if isinstance(agent, dict) else None,
                    "qa_passed": bool(agent.get("qa_passed")) if isinstance(agent, dict) else ok,
                    "attempts": int(out_state.get("attempts") or (agent.get("attempts") if isinstance(agent, dict) else 0) or 0),
                    "task_tree": (
                        (agent.get("extensions") or {}).get("task_tree_summary")
                        if isinstance(agent, dict)
                        else None
                    ),
                    "state": agent if isinstance(agent, dict) else {},
                    "engine": "temporal_langgraph_plugin",
                }
            except Exception as exc:
                workflow.logger.warning(
                    "plugin graph failed (%s): %s — legacy single activity", type(exc).__name__, repr(exc)[:500]
                )
                retry = RetryPolicy(
                    initial_interval=timedelta(seconds=2),
                    backoff_coefficient=2.0,
                    maximum_interval=timedelta(seconds=60),
                    maximum_attempts=2,
                )
                # Sandbox: no os.getenv — fixed production timeouts (override via activity defaults on worker)
                result = await workflow.execute_activity(
                    run_langgraph_generate_activity,
                    payload,
                    start_to_close_timeout=timedelta(hours=24),
                    heartbeat_timeout=timedelta(minutes=10),
                    retry_policy=retry,
                )
                out = dict(result or {})
                out["engine"] = out.get("engine") or "temporal_legacy_after_plugin_error"
                out["plugin_error"] = f"{type(exc).__name__}:{exc}"
                return out



if activity is not None:

    @activity.defn(name="lumen_stage_plan")
    async def lumen_stage_plan(data: dict[str, Any]) -> dict[str, Any]:
        import asyncio
        from .temporal_plugin_graph import _plan_sync, _hb
        _hb({"phase": "plan_activity"})
        out = await asyncio.to_thread(_plan_sync, data)
        _hb({"phase": "plan_done", "ok": bool((out or {}).get("ok"))})
        # merge into state
        merged = dict(data or {})
        merged.update(out or {})
        return merged

    @activity.defn(name="lumen_stage_work")
    async def lumen_stage_work(data: dict[str, Any]) -> dict[str, Any]:
        import asyncio
        from .temporal_plugin_graph import _work_sync, _hb
        _hb({"phase": "work_activity"})
        out = await asyncio.to_thread(_work_sync, data)
        _hb({"phase": "work_done", "ok": bool((out or {}).get("ok"))})
        merged = dict(data or {})
        merged.update(out or {})
        return merged

    @activity.defn(name="lumen_stage_critique")
    async def lumen_stage_critique(data: dict[str, Any]) -> dict[str, Any]:
        import asyncio
        from .temporal_plugin_graph import _critique_sync, _hb
        _hb({"phase": "critique_activity"})
        out = await asyncio.to_thread(_critique_sync, data)
        _hb({"phase": "critique_done", "ok": bool((out or {}).get("ok"))})
        merged = dict(data or {})
        merged.update(out or {})
        return merged

    @activity.defn(name="lumen_stage_repair")
    async def lumen_stage_repair(data: dict[str, Any]) -> dict[str, Any]:
        import asyncio
        from .temporal_plugin_graph import _repair_sync, _hb
        _hb({"phase": "repair_activity"})
        out = await asyncio.to_thread(_repair_sync, data)
        merged = dict(data or {})
        merged.update(out or {})
        return merged

    @activity.defn(name="lumen_stage_deliver")
    async def lumen_stage_deliver(data: dict[str, Any]) -> dict[str, Any]:
        import asyncio
        from .temporal_plugin_graph import _deliver_sync, _hb
        _hb({"phase": "deliver_activity"})
        out = await asyncio.to_thread(_deliver_sync, data)
        merged = dict(data or {})
        merged.update(out or {})
        return merged


if workflow is not None:

    @workflow.defn(name="LumenSequentialGenerateWorkflow")
    class LumenSequentialGenerateWorkflow:
        """Production durable path: explicit Temporal Activities per stage (Temporal AI cookbook).

        plan → work → critique ⇄ repair → deliver
        No LangGraphPlugin ainvoke in the workflow sandbox — pure Temporal orchestration.
        Plugin graph remains registered for advanced/HITL path.
        """

        def __init__(self) -> None:
            self._cancelled = False
            self._steer: dict[str, Any] = {}

        @workflow.signal
        def cancel(self) -> None:
            self._cancelled = True

        @workflow.signal
        def steer(self, payload: dict[str, Any]) -> None:
            self._steer = dict(payload or {})

        @workflow.query
        def status_view(self) -> dict[str, Any]:
            return {"cancelled": self._cancelled, "steer": dict(self._steer), "engine": "temporal_sequential_activities"}

        @workflow.run
        async def run(self, data: dict[str, Any]) -> dict[str, Any]:
            from datetime import timedelta

            payload = dict(data or {})
            state_id = str(payload.get("state_id") or payload.get("workflow_id") or "lumen-state")
            max_attempts = int(payload.get("max_attempts") or 4)
            if max_attempts < 1:
                max_attempts = 1
            if max_attempts > 8:
                max_attempts = 8

            state: dict[str, Any] = {
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
                "max_attempts": max_attempts,
                "plan_summary": "",
            }

            retry = RetryPolicy(
                initial_interval=timedelta(seconds=2),
                backoff_coefficient=2.0,
                maximum_interval=timedelta(seconds=60),
                maximum_attempts=3,
            )
            plan_to = timedelta(hours=1)
            work_to = timedelta(hours=6)
            crit_to = timedelta(hours=1)
            hb = timedelta(minutes=10)

            if self._cancelled:
                return {"ok": False, "status": "CANCELLED", "engine": "temporal_sequential_activities"}

            state = await workflow.execute_activity(
                lumen_stage_plan, state,
                start_to_close_timeout=plan_to, heartbeat_timeout=hb, retry_policy=retry,
            )
            if self._cancelled:
                return {"ok": False, "status": "CANCELLED", "state_id": state_id, "engine": "temporal_sequential_activities"}

            for _ in range(max_attempts):
                if self._cancelled:
                    break
                state = await workflow.execute_activity(
                    lumen_stage_work, state,
                    start_to_close_timeout=work_to, heartbeat_timeout=hb, retry_policy=retry,
                )
                state = await workflow.execute_activity(
                    lumen_stage_critique, state,
                    start_to_close_timeout=crit_to, heartbeat_timeout=hb, retry_policy=retry,
                )
                agent = state.get("agent") or {}
                qa = bool(agent.get("qa_passed")) if isinstance(agent, dict) else bool(state.get("ok"))
                if qa:
                    break
                attempts = int(state.get("attempts") or 0)
                if attempts >= max_attempts:
                    break
                state = await workflow.execute_activity(
                    lumen_stage_repair, state,
                    start_to_close_timeout=plan_to, heartbeat_timeout=hb, retry_policy=retry,
                )

            state = await workflow.execute_activity(
                lumen_stage_deliver, state,
                start_to_close_timeout=timedelta(minutes=30), heartbeat_timeout=hb, retry_policy=retry,
            )
            agent = state.get("agent") or {}
            ok = bool(state.get("ok")) or bool(agent.get("qa_passed") if isinstance(agent, dict) else False)
            return {
                "ok": ok,
                "status": str(state.get("status") or (agent.get("status") if isinstance(agent, dict) else "") or ""),
                "state_id": state_id,
                "generated_path": agent.get("generated_path") if isinstance(agent, dict) else None,
                "qa_passed": bool(agent.get("qa_passed")) if isinstance(agent, dict) else ok,
                "attempts": int(state.get("attempts") or 0),
                "task_tree": (
                    (agent.get("extensions") or {}).get("task_tree_summary")
                    if isinstance(agent, dict) else None
                ),
                "state": agent if isinstance(agent, dict) else {},
                "engine": "temporal_sequential_activities",
            }



def activity_fns() -> list[Callable[..., Any]]:
    if activity is None:
        return []
    return [
        register_generate_job,
        run_langgraph_generate_activity,
        run_generate_activity,
        lumen_stage_plan,
        lumen_stage_work,
        lumen_stage_critique,
        lumen_stage_repair,
        lumen_stage_deliver,
    ]


def workflow_classes() -> list[type]:
    if workflow is None:
        return []
    return [
        LumenSequentialGenerateWorkflow,
        LumenPluginGenerateWorkflow,
        LumenMultiAgentGenerateWorkflow,
    ]


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
