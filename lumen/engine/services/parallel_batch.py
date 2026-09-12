"""Run indexed callables in parallel with asyncio, thread-pool fallback.

Used by tool_runtime and cline agent_fs so asyncio.run + ThreadPoolExecutor
is not reimplemented per module.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Iterable, TypeVar

T = TypeVar("T")


def run_indexed_parallel(
    indices: Iterable[int],
    worker: Callable[[int], T],
    *,
    max_workers: int = 4,
) -> dict[int, T]:
    """Execute worker(idx) for each index; return {idx: result}.

    Prefers asyncio.to_thread under a fresh event loop; on RuntimeError
    (nested loop) falls back to ThreadPoolExecutor.
    """
    idxs = [int(i) for i in indices]
    if not idxs:
        return {}
    max_workers = max(1, int(max_workers))
    results: dict[int, T] = {}

    async def _one(i: int) -> tuple[int, T]:
        out = await asyncio.to_thread(worker, i)
        return i, out

    async def _runner() -> None:
        for start in range(0, len(idxs), max_workers):
            batch = idxs[start : start + max_workers]
            done = await asyncio.gather(*[_one(i) for i in batch])
            for i, out in done:
                results[i] = out

    try:
        asyncio.run(_runner())
    except RuntimeError:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futs = {pool.submit(worker, i): i for i in idxs}
            for fut in as_completed(futs):
                i = futs[fut]
                results[i] = fut.result()
    return results


__all__ = ["run_indexed_parallel"]
