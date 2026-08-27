"""Parallel agent swarm — concurrent Cline run_agent partitions (official loop)."""
from __future__ import annotations

import logging
import os
import shutil
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


def _task_goal(tasks: list[dict[str, Any]], base_goal: str) -> str:
    lines = [base_goal.strip(), "", "Focus only on these tasks:"]
    for t in tasks:
        tid = t.get("id") or t.get("title") or "?"
        title = t.get("title") or t.get("description") or tid
        lines.append(f"- [{tid}] {title}")
    return "\n".join(lines)[:4000]


def _run_partition_agent(
    part: list[dict[str, Any]],
    root: Path,
    idx: int,
    *,
    base_goal: str,
    ir_dict: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sub = root / f".swarm_w{idx}"
    sub.mkdir(parents=True, exist_ok=True)
    goal = _task_goal(part, base_goal)
    try:
        from lumen.engine.services.cline_runtime.agent_loop import run_agent

        state = run_agent(
            work_dir=str(sub),
            goal=goal,
            ir_dict=ir_dict,
            max_steps=int(os.getenv("SWARM_MAX_STEPS") or "12"),
        )
        ok = bool(getattr(state, "ok", False))
        merged = 0
        for f in sub.rglob("*"):
            if not f.is_file():
                continue
            if f.name.startswith("."):
                continue
            rel = f.relative_to(sub)
            dest = root / rel
            if dest.exists():
                # prefer swarm file only if dest empty/missing
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
            merged += 1
        return {
            "ok": ok,
            "worker": idx,
            "task_ids": [x.get("id") or x.get("title") for x in part],
            "merged_files": merged,
            "stop_reason": getattr(state, "stop_reason", ""),
            "errors": list(getattr(state, "errors", None) or [])[:5],
        }
    except Exception as exc:
        logger.exception("swarm worker %s failed", idx)
        return {"ok": False, "worker": idx, "error": f"{type(exc).__name__}:{exc}"}


def run_swarm(
    *,
    work_dir: str | Path,
    tasks: list[dict[str, Any]],
    worker_fn: Callable[[list[dict[str, Any]], Path, int], dict[str, Any]] | None = None,
    max_workers: int | None = None,
    base_goal: str = "",
    ir_dict: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from .production_policy import allow_swarm
    if not allow_swarm():
        return {
            "ok": False,
            "error": "swarm_disabled: set MULTI_AGENT_SWARM=1 to enable experimental parallel workers",
            "engine": "swarm_disabled",
            "workers": [],
        }
    root = Path(work_dir)
    root.mkdir(parents=True, exist_ok=True)
    n = max_workers or _max_workers()
    parts = partition_tasks(list(tasks or []), n)
    results: list[dict[str, Any]] = []
    errors: list[str] = []

    def _default(part, r, idx):
        return _run_partition_agent(
            part, r, idx, base_goal=base_goal or "Implement assigned tasks", ir_dict=ir_dict
        )

    fn = worker_fn or _default
    with ThreadPoolExecutor(max_workers=n, thread_name_prefix="lumen-swarm") as pool:
        futs = {pool.submit(fn, part, root, idx): idx for idx, part in enumerate(parts) if part}
        for fut in as_completed(futs):
            idx = futs[fut]
            try:
                res = fut.result()
                results.append({"worker": idx, **(res if isinstance(res, dict) else {"ok": bool(res)})})
            except Exception as exc:
                errors.append(f"worker{idx}:{type(exc).__name__}:{exc}")
                results.append({"worker": idx, "ok": False, "error": str(exc)})

    ok = bool(results) and all(r.get("ok") for r in results) and not errors
    return {
        "ok": ok,
        "workers": n,
        "results": results,
        "errors": errors,
        "task_count": len(tasks or []),
        "engine": "run_agent" if worker_fn is None else "custom",
    }


__all__ = ["partition_tasks", "run_swarm"]
