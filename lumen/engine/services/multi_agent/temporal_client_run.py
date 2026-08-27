"""Start Lumen generate on Temporal and wait for result (sync helper).

Prefers LumenPluginGenerateWorkflow (official LangGraph Plugin, per-node Activities).
Falls back to LumenMultiAgentGenerateWorkflow (legacy single-activity) if forced.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Any

logger = logging.getLogger(__name__)


def temporal_configured() -> bool:
    """True only when temporalio is installed AND TEMPORAL_HOST is set (or explicit enable)."""
    try:
        import temporalio  # noqa: F401
    except Exception:
        return False
    if (os.getenv("LUMEN_TEMPORAL_REQUIRED") or "").strip().lower() in {"1", "true", "yes"}:
        return True
    host = (os.getenv("TEMPORAL_HOST") or "").strip()
    return bool(host)


def _prefer_plugin() -> bool:
    """Use official LangGraph Plugin workflow unless explicitly disabled."""
    if (os.getenv("LUMEN_TEMPORAL_LEGACY") or "").strip().lower() in {"1", "true", "yes", "on"}:
        return False
    try:
        from .temporal_plugin_graph import plugin_available
        return plugin_available()
    except Exception:
        return False


async def _start_and_wait(payload: dict[str, Any], *, wait: bool = True) -> dict[str, Any]:
    from temporalio.client import Client
    from .temporal_defs import LumenMultiAgentGenerateWorkflow, LumenPluginGenerateWorkflow

    host = (os.getenv("TEMPORAL_HOST") or "localhost:7233").strip()
    namespace = (os.getenv("TEMPORAL_NAMESPACE") or "default").strip()
    task_queue = (os.getenv("TEMPORAL_TASK_QUEUE") or "tbe-generate").strip()
    client = await Client.connect(host, namespace=namespace)
    wid = str(payload.get("workflow_id") or f"lumen-gen-{uuid.uuid4().hex[:16]}")

    if _prefer_plugin():
        wf = LumenPluginGenerateWorkflow.run
        engine = "temporal_langgraph_plugin"
    else:
        wf = LumenMultiAgentGenerateWorkflow.run
        engine = "temporal_legacy"

    handle = await client.start_workflow(
        wf,
        payload,
        id=wid,
        task_queue=task_queue,
    )
    if not wait:
        return {"ok": True, "workflow_id": wid, "async": True, "engine": engine}
    result = await handle.result()
    return {
        "ok": bool((result or {}).get("ok")),
        "workflow_id": wid,
        "result": result,
        "engine": (result or {}).get("engine") or engine,
    }


def run_generate_via_temporal(
    *,
    request: str,
    work_dir: str,
    user_id: int = 0,
    preferred_keys: list | None = None,
    wait: bool = True,
    timeout_sec: float = 7200.0,
) -> dict[str, Any]:
    payload = {
        "request": request,
        "description": request[:2000],
        "work_dir": work_dir,
        "user_id": int(user_id or 0),
        "preferred_keys": list(preferred_keys or []),
        "state_id": f"tg-{uuid.uuid4().hex[:12]}",
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
                return pool.submit(lambda: asyncio.run(_main())).result(timeout=timeout_sec + 30)
        return asyncio.run(_main())
    except Exception as exc:
        logger.exception("temporal generate failed")
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}


__all__ = ["run_generate_via_temporal", "temporal_configured"]
