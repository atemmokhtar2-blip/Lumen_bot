"""Temporal durable generate — single production path.

LumenSequentialGenerateWorkflow:
  plan → [optional HITL signal] → work → critique ⇄ repair → deliver

Each stage is a real Temporal Activity (retries + heartbeats).
Broken Plugin/legacy paths removed (rules: no dead code, no dual paths).

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
    hitl: bool = False
    max_attempts: int = 4


def _merge(state: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    merged = dict(state or {})
    merged.update(out or {})
    return merged


if activity is not None:

    @activity.defn(name="lumen_stage_plan")
    async def lumen_stage_plan(data: dict[str, Any]) -> dict[str, Any]:
        import asyncio
        from .temporal_stages import stage_plan

        try:
            activity.heartbeat({"phase": "plan_start"})
        except Exception:
            pass
        out = await asyncio.to_thread(stage_plan, data)
        try:
            activity.heartbeat({"phase": "plan_done", "ok": bool((out or {}).get("ok"))})
        except Exception:
            pass
        return _merge(data, out)

    @activity.defn(name="lumen_stage_work")
    async def lumen_stage_work(data: dict[str, Any]) -> dict[str, Any]:
        import asyncio
        from .temporal_stages import stage_work

        try:
            activity.heartbeat({"phase": "work_start"})
        except Exception:
            pass

        async def _pulse() -> None:
            while True:
                await asyncio.sleep(30)
                try:
                    activity.heartbeat({"phase": "work_alive"})
                except Exception:
                    return

        pulse = asyncio.create_task(_pulse())
        try:
            out = await asyncio.to_thread(stage_work, data)
        finally:
            pulse.cancel()
            try:
                await pulse
            except (asyncio.CancelledError, Exception):
                pass
        try:
            activity.heartbeat({"phase": "work_done", "ok": bool((out or {}).get("ok"))})
        except Exception:
            pass
        return _merge(data, out)

    @activity.defn(name="lumen_stage_critique")
    async def lumen_stage_critique(data: dict[str, Any]) -> dict[str, Any]:
        import asyncio
        from .temporal_stages import stage_critique

        try:
            activity.heartbeat({"phase": "critique_start"})
        except Exception:
            pass
        out = await asyncio.to_thread(stage_critique, data)
        try:
            activity.heartbeat({"phase": "critique_done", "ok": bool((out or {}).get("ok"))})
        except Exception:
            pass
        return _merge(data, out)

    @activity.defn(name="lumen_stage_repair")
    async def lumen_stage_repair(data: dict[str, Any]) -> dict[str, Any]:
        import asyncio
        from .temporal_stages import stage_repair

        try:
            activity.heartbeat({"phase": "repair_start"})
        except Exception:
            pass
        out = await asyncio.to_thread(stage_repair, data)
        try:
            activity.heartbeat({"phase": "repair_done"})
        except Exception:
            pass
        return _merge(data, out)

    @activity.defn(name="lumen_stage_deliver")
    async def lumen_stage_deliver(data: dict[str, Any]) -> dict[str, Any]:
        import asyncio
        from .temporal_stages import stage_deliver

        try:
            activity.heartbeat({"phase": "deliver_start"})
        except Exception:
            pass
        out = await asyncio.to_thread(stage_deliver, data)
        try:
            activity.heartbeat({"phase": "deliver_done", "ok": bool((out or {}).get("ok"))})
        except Exception:
            pass
        return _merge(data, out)


if workflow is not None:


    @workflow.defn(name="LumenSequentialGenerateWorkflow")
    class LumenSequentialGenerateWorkflow:
        """Production durable agent path (Temporal AI cookbook pattern).

        plan → optional HITL (signal hitl_decision) → work → critique ⇄ repair → deliver

        Workflow sandbox rules: no os.getenv, no uuid.random, no non-deterministic I/O.
        HITL is opt-in via payload["hitl"]=True (client sets from MULTI_AGENT_LANGGRAPH_HITL).
        """

        def __init__(self) -> None:
            self._cancelled = False
            self._steer: dict[str, Any] = {}
            self._human_input: str | None = None
            self._pending_plan: Any = None
            self._phase: str = "init"

        @workflow.signal
        def cancel(self) -> None:
            self._cancelled = True

        @workflow.signal
        def steer(self, payload: dict[str, Any]) -> None:
            self._steer = dict(payload or {})

        @workflow.signal
        def hitl_decision(self, payload: dict[str, Any] | str) -> None:
            if isinstance(payload, dict):
                self._human_input = str(
                    payload.get("decision")
                    or payload.get("value")
                    or payload.get("feedback")
                    or ""
                )
            else:
                self._human_input = str(payload or "")

        @workflow.signal
        def provide_feedback(self, feedback: str) -> None:
            self._human_input = str(feedback or "")

        @workflow.query
        def status_view(self) -> dict[str, Any]:
            return {
                "phase": self._phase,
                "cancelled": self._cancelled,
                "steer": dict(self._steer),
                "awaiting_hitl": self._human_input is None and self._pending_plan is not None,
                "pending_plan": self._pending_plan,
                "engine": "temporal_sequential_activities",
            }

        @workflow.query
        def get_pending_plan(self) -> Any:
            return self._pending_plan

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
            # HITL only from payload (client reads env) — never os.getenv in workflow
            hitl = bool(payload.get("hitl"))

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
                return {
                    "ok": False,
                    "status": "CANCELLED",
                    "engine": "temporal_sequential_activities",
                }

            self._phase = "plan"
            state = await workflow.execute_activity(
                lumen_stage_plan,
                state,
                start_to_close_timeout=plan_to,
                heartbeat_timeout=hb,
                retry_policy=retry,
            )

            # Optional HITL after plan (signal-driven, durable wait)
            if hitl and not self._cancelled:
                self._phase = "hitl"
                self._pending_plan = {
                    "state_id": state_id,
                    "plan_summary": str(state.get("plan_summary") or "")[:800],
                    "message": "Approve plan to continue building?",
                }
                await workflow.wait_condition(
                    lambda: self._human_input is not None or self._cancelled
                )
                if self._cancelled:
                    return {
                        "ok": False,
                        "status": "CANCELLED",
                        "state_id": state_id,
                        "engine": "temporal_sequential_activities",
                    }
                decision = str(self._human_input or "").strip().lower()
                approved = decision in {
                    "1",
                    "true",
                    "yes",
                    "y",
                    "approve",
                    "approved",
                    "ok",
                    "confirm",
                }
                self._pending_plan = None
                self._human_input = None
                if not approved:
                    return {
                        "ok": False,
                        "status": "FAILED",
                        "state_id": state_id,
                        "error": f"plan_rejected:{decision[:40]}",
                        "engine": "temporal_sequential_activities",
                    }

            for _ in range(max_attempts):
                if self._cancelled:
                    break
                self._phase = "work"
                state = await workflow.execute_activity(
                    lumen_stage_work,
                    state,
                    start_to_close_timeout=work_to,
                    heartbeat_timeout=hb,
                    retry_policy=retry,
                )
                self._phase = "critique"
                state = await workflow.execute_activity(
                    lumen_stage_critique,
                    state,
                    start_to_close_timeout=crit_to,
                    heartbeat_timeout=hb,
                    retry_policy=retry,
                )
                agent = state.get("agent") or {}
                qa = (
                    bool(agent.get("qa_passed"))
                    if isinstance(agent, dict)
                    else bool(state.get("ok"))
                )
                if qa:
                    break
                attempts = int(state.get("attempts") or 0)
                if attempts >= max_attempts:
                    break
                self._phase = "repair"
                state = await workflow.execute_activity(
                    lumen_stage_repair,
                    state,
                    start_to_close_timeout=plan_to,
                    heartbeat_timeout=hb,
                    retry_policy=retry,
                )

            if self._cancelled:
                return {
                    "ok": False,
                    "status": "CANCELLED",
                    "state_id": state_id,
                    "engine": "temporal_sequential_activities",
                }

            self._phase = "deliver"
            state = await workflow.execute_activity(
                lumen_stage_deliver,
                state,
                start_to_close_timeout=timedelta(minutes=30),
                heartbeat_timeout=hb,
                retry_policy=retry,
            )
            self._phase = "done"
            agent = state.get("agent") or {}
            ok = bool(state.get("ok")) or bool(
                agent.get("qa_passed") if isinstance(agent, dict) else False
            )
            return {
                "ok": ok,
                "status": str(
                    state.get("status")
                    or (agent.get("status") if isinstance(agent, dict) else "")
                    or ""
                ),
                "state_id": state_id,
                "generated_path": agent.get("generated_path")
                if isinstance(agent, dict)
                else None,
                "qa_passed": bool(agent.get("qa_passed"))
                if isinstance(agent, dict)
                else ok,
                "attempts": int(state.get("attempts") or 0),
                "task_tree": (
                    (agent.get("extensions") or {}).get("task_tree_summary")
                    if isinstance(agent, dict)
                    else None
                ),
                "state": agent if isinstance(agent, dict) else {},
                "engine": "temporal_sequential_activities",
            }


def activity_fns() -> list[Callable[..., Any]]:
    if activity is None:
        return []
    return [
        lumen_stage_plan,
        lumen_stage_work,
        lumen_stage_critique,
        lumen_stage_repair,
        lumen_stage_deliver,
    ]


def workflow_classes() -> list[type]:
    if workflow is None:
        return []
    return [LumenSequentialGenerateWorkflow]


__all__ = [
    "GenerateJobInput",
    "LumenSequentialGenerateWorkflow",
    "lumen_stage_plan",
    "lumen_stage_work",
    "lumen_stage_critique",
    "lumen_stage_repair",
    "lumen_stage_deliver",
    "activity_fns",
    "workflow_classes",
]
