"""Event-driven agent wake — Temporal signals / schedules (official path).

No fake in-process sleep loops. Requires Temporal worker when host is set.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


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
    workflow_type: str = "LumenAgentWorkflow",
    cron: str = "0 * * * *",
    task_queue: str | None = None,
) -> dict[str, Any]:
    """Describe how to schedule wakes — returns config; actual schedule via Temporal CLI/API."""
    if not temporal_enabled():
        return {"ok": False, "error": "temporal_not_configured"}
    queue = task_queue or (os.getenv("TEMPORAL_TASK_QUEUE") or "lumen-agents")
    return {
        "ok": True,
        "engine": "temporal_schedule",
        "workflow_type": workflow_type,
        "cron": cron,
        "task_queue": queue,
        "note": "Create via Temporal Schedule API or temporal schedule create",
    }


__all__ = ["temporal_enabled", "signal_wake", "schedule_wake_cron"]
