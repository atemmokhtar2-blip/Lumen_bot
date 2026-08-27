"""Event-driven agent wake — Temporal signals / workflow starts (official path).

Supported event types (no fake in-process sleep loops):
  - ci_failed / github_workflow_failed
  - pull_request_opened / pull_request_comment
  - schedule_tick
  - telegram_message (optional handoff)
  - custom wake signal on running workflow

Requires TEMPORAL_HOST for durable long-running behavior.
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Any

logger = logging.getLogger(__name__)

# Event → default Temporal action
EVENT_ROUTES: dict[str, str] = {
    "ci_failed": "start_generate",
    "github_workflow_failed": "start_generate",
    "pull_request_opened": "start_generate",
    "pull_request_comment": "signal_wake",
    "schedule_tick": "start_generate",
    "telegram_message": "start_generate",
    "wake": "signal_wake",
    "cancel": "signal_wake",
}


def temporal_enabled() -> bool:
    host = (os.getenv("TEMPORAL_HOST") or os.getenv("TEMPORAL_ADDRESS") or "").strip()
    return bool(host)


async def signal_wake(
    workflow_id: str,
    *,
    signal_name: str = "wake",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send a Temporal signal to a running agent workflow."""
    if not temporal_enabled():
        return {"ok": False, "error": "temporal_not_configured"}
    try:
        from temporalio.client import Client

        host = (os.getenv("TEMPORAL_HOST") or os.getenv("TEMPORAL_ADDRESS") or "localhost:7233").strip()
        namespace = (os.getenv("TEMPORAL_NAMESPACE") or "default").strip()
        client = await Client.connect(host, namespace=namespace)
        handle = client.get_workflow_handle(workflow_id)
        await handle.signal(signal_name, payload or {})
        return {"ok": True, "workflow_id": workflow_id, "signal": signal_name}
    except Exception as exc:
        logger.exception("signal_wake failed")
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}


def schedule_wake_cron(
    *,
    workflow_type: str = "LumenSequentialGenerateWorkflow",
    cron: str = "0 * * * *",
    task_queue: str | None = None,
) -> dict[str, Any]:
    """Return Temporal Schedule config (create via Temporal Schedule API / CLI)."""
    if not temporal_enabled():
        return {"ok": False, "error": "temporal_not_configured"}
    queue = task_queue or (os.getenv("TEMPORAL_TASK_QUEUE") or "lumen-agents")
    return {
        "ok": True,
        "engine": "temporal_schedule",
        "workflow_type": workflow_type,
        "cron": cron,
        "task_queue": queue,
        "note": "temporal schedule create --cron '{cron}' --workflow-type {workflow_type}".format(
            cron=cron, workflow_type=workflow_type
        ),
    }


def handle_agent_event(
    event_type: str,
    payload: dict[str, Any] | None = None,
    *,
    workflow_id: str | None = None,
) -> dict[str, Any]:
    """Route an external event to Temporal start or signal (sync entry).

    Does not simulate work in-process. When Temporal is down, returns explicit error.
    """
    et = (event_type or "").strip().lower()
    action = EVENT_ROUTES.get(et, "start_generate")
    data = dict(payload or {})
    data.setdefault("event_type", et)
    data.setdefault("event_id", uuid.uuid4().hex[:16])

    if not temporal_enabled():
        return {
            "ok": False,
            "error": "temporal_not_configured",
            "event_type": et,
            "action": action,
            "hint": "Set TEMPORAL_HOST and run temporal_worker for durable event-driven agents",
        }

    if action == "signal_wake":
        wid = workflow_id or str(data.get("workflow_id") or "")
        if not wid:
            return {"ok": False, "error": "workflow_id_required_for_signal", "event_type": et}
        import asyncio
        try:
            return asyncio.get_event_loop().run_until_complete(
                signal_wake(wid, signal_name=str(data.get("signal_name") or "wake"), payload=data)
            )
        except RuntimeError:
            return asyncio.run(signal_wake(wid, signal_name=str(data.get("signal_name") or "wake"), payload=data))

    # start_generate via official temporal client helper
    try:
        from .temporal_client_run import run_generate_via_temporal, temporal_configured
        if not temporal_configured():
            return {"ok": False, "error": "temporal_not_configured", "event_type": et}
        # Fire-and-forget style: start workflow; client helper may wait — use short path if available
        result = run_generate_via_temporal(
            request=str(data.get("request") or data.get("description") or f"event:{et}"),
            work_dir=str(data.get("work_dir") or ""),
            user_id=int(data.get("user_id") or 0),
            preferred_keys=list(data.get("preferred_keys") or []),
            state_id=str(data.get("state_id") or ""),
        )
        return {"ok": bool(result.get("ok")), "event_type": et, "action": action, "temporal": result}
    except Exception as exc:
        logger.exception("handle_agent_event start failed")
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}", "event_type": et, "action": action}


__all__ = [
    "EVENT_ROUTES",
    "temporal_enabled",
    "signal_wake",
    "schedule_wake_cron",
    "handle_agent_event",
]
