"""Parallel agent swarm — run multiple workers on partitioned tasks.

Uses concurrent.futures with the real WorkerAgent / builder path.
Not a mock: each worker receives a slice of the plan and writes under work_dir.
"""
from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


def _max_workers() -> int:
    try:
        return max(1, min(32, int(os.getenv("MULTI_AGENT_SWARM_SIZE") or "4")))
    except ValueError:
        return 4


def partition_tasks(tasks: list[dict[str, Any]], n: int) -> list[list[dict[str, Any]]]:
    if not tasks:
        return [[] for _ in range(max(1, n))]
    n = max(1, min(n, len(tasks)))
    buckets: list[list[dict[str, Any]]] = [[] for _ in range(n)]
    for i, t in enumerate(tasks):
        buckets[i % n].append(t)
    return buckets


def run_swarm(
    *,
    work_dir: str | Path,
    tasks: list[dict[str, Any]],
    worker_fn: Callable[[list[dict[str, Any]], Path, int], dict[str, Any]],
    max_workers: int | None = None,
) -> dict[str, Any]:
    """Execute worker_fn in parallel over task partitions.

    worker_fn(task_slice, work_dir, worker_index) -> {ok, ...}
    """
    root = Path(work_dir)
    root.mkdir(parents=True, exist_ok=True)
    n = max_workers or _max_workers()
    parts = partition_tasks(list(tasks or []), n)
    results: list[dict[str, Any]] = []
    errors: list[str] = []

    with ThreadPoolExecutor(max_workers=n, thread_name_prefix="lumen-swarm") as pool:
        futs = {
            pool.submit(worker_fn, part, root, idx): idx
            for idx, part in enumerate(parts)
            if part
        }
        for fut in as_completed(futs):
            idx = futs[fut]
            try:
                res = fut.result()
                results.append({"worker": idx, **(res if isinstance(res, dict) else {"ok": bool(res)})})
            except Exception as exc:
                logger.exception("swarm worker %s failed", idx)
                errors.append(f"worker{idx}:{type(exc).__name__}:{exc}")
                results.append({"worker": idx, "ok": False, "error": str(exc)})

    ok = bool(results) and all(r.get("ok") for r in results) and not errors
    return {
        "ok": ok,
        "workers": n,
        "results": results,
        "errors": errors,
        "task_count": len(tasks or []),
    }


__all__ = ["partition_tasks", "run_swarm"]
