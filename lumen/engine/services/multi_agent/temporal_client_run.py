"""Start Lumen durable generate on Temporal (single production path).

Always uses LumenSequentialGenerateWorkflow:
  plan → [HITL if enabled] → work → critique ⇄ repair → deliver

HITL opt-in: MULTI_AGENT_LANGGRAPH_HITL=1 (passed as payload hitl=True).
Requires TEMPORAL_HOST and a running worker:
  python -m lumen.engine.services.multi_agent.temporal_worker
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Any

logger = logging.getLogger(__name__)


def temporal_configured() -> bool:
    """True when temporalio is installed and TEMPORAL_HOST is set (or explicit require)."""
    try:
        import temporalio  # noqa: F401
    except Exception:
        return False
    if (os.getenv("LUMEN_TEMPORAL_REQUIRED") or "").strip().lower() in {"1", "true", "yes"}:
        return True
    return bool((os.getenv("TEMPORAL_HOST") or "").strip())


def _hitl_from_env() -> bool:
    return (os.getenv("MULTI_AGENT_LANGGRAPH_HITL") or "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


async def _start_and_wait(payload: dict[str, Any], *, wait: bool = True) -> dict[str, Any]:
    from temporalio.client import Client
    from .temporal_defs import LumenSequentialGenerateWorkflow

    host = (os.getenv("TEMPORAL_HOST") or "localhost:7233").strip()
    namespace = (os.getenv("TEMPORAL_NAMESPACE") or "default").strip()
    task_queue = (os.getenv("TEMPORAL_TASK_QUEUE") or "tbe-generate").strip()
    client = await Client.connect(host, namespace=namespace)
    wid = str(payload.get("workflow_id") or f"lumen-gen-{uuid.uuid4().hex[:16]}")

    handle = await client.start_workflow(
        LumenSequentialGenerateWorkflow.run,
        payload,
        id=wid,
        task_queue=task_queue,
    )
    if not wait:
        return {
            "ok": True,
            "workflow_id": wid,
            "async": True,
            "engine": "temporal_sequential_activities",
        }
    result = await handle.result()
    return {
        "ok": bool((result or {}).get("ok")),
        "workflow_id": wid,
        "result": result,
        "engine": (result or {}).get("engine") or "temporal_sequential_activities",
    }


def run_generate_via_temporal(
    *,
    request: str,
    work_dir: str,
    user_id: int = 0,
    preferred_keys: list | None = None,
    wait: bool = True,
    timeout_sec: float = 7200.0,
    hitl: bool | None = None,
    max_attempts: int = 4,
) -> dict[str, Any]:
    payload = {
        "request": request,
        "description": (request or "")[:2000],
        "work_dir": work_dir,
        "user_id": int(user_id or 0),
        "preferred_keys": list(preferred_keys or []),
        "state_id": f"tg-{uuid.uuid4().hex[:12]}",
        "hitl": bool(_hitl_from_env() if hitl is None else hitl),
        "max_attempts": max(1, min(8, int(max_attempts or 4))),
    }

    async def _main():
        return await asyncio.wait_for(_start_and_wait(payload, wait=wait), timeout=timeout_sec)

    try:
        try:
            asyncio.get_running_loop()
            running = True
        except RuntimeError:
            running = False
        if running:
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(lambda: asyncio.run(_main())).result(
                    timeout=timeout_sec + 30
                )
        return asyncio.run(_main())
    except Exception as exc:
        logger.exception("temporal generate failed")
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}


__all__ = ["run_generate_via_temporal", "temporal_configured"]
