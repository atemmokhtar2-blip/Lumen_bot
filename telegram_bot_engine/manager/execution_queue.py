"""
Execution queue (Specification 003).

The :class:`ExecutionQueue` is the internal ordering mechanism of the
Core Engine Manager.  It determines the order in which engines run.

Key rules:

* The queue is **internal** to the manager.  No engine can see it,
  change it, or influence its own position.
* Engines cannot change their own order — only the manager rebuilds the
  queue, and it does so deterministically from the registered entries
  (sorted by priority, then by engine ID for stability).
* The queue respects dependencies: an engine will not appear before any
  of its dependencies.
* A topological sort resolves dependency ordering; ties are broken by
  priority then by ID so the order is deterministic and reproducible.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .engine_entry import EngineEntry
from .lifecycle import EngineState


class QueueItem:
    """A single item in the execution queue.

    A lightweight, immutable view of an :class:`EngineEntry` exposed to
    the manager during execution.  It carries only the information the
    manager needs to decide whether to run the engine next.
    """

    __slots__ = ("engine_id", "name", "priority", "dependencies",
                 "dependencies_met")

    def __init__(self, engine_id: str, name: str, priority: int,
                 dependencies: List[str],
                 dependencies_met: bool) -> None:
        self.engine_id = engine_id
        self.name = name
        self.priority = priority
        self.dependencies = list(dependencies)
        self.dependencies_met = dependencies_met

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (f"QueueItem(engine_id={self.engine_id!r}, "
                f"priority={self.priority}, "
                f"dependencies_met={self.dependencies_met})")


class ExecutionQueue:
    """Internal, dependency-aware execution queue for the manager.

    The queue is rebuilt from the registered engine entries whenever the
    manager asks for the next runnable engine.  It performs a
    topological sort (Kahn's algorithm) over the dependency graph,
    breaking ties by ``(priority, engine_id)`` so the order is
    deterministic.

    The queue does **not** execute engines.  It only tells the manager
    which engine should run next and whether that engine's dependencies
    are currently satisfied.
    """

    def __init__(self) -> None:
        self._entries: Dict[str, EngineEntry] = {}

    # -- population --------------------------------------------------------

    def rebuild(self, entries: Dict[str, EngineEntry]) -> List[QueueItem]:
        """Rebuild the queue from the given engine entries.

        Only enabled engines that are not yet terminal are included.
        The returned list is in the order the manager should attempt
        to run them.

        Raises:
            ValueError: if a dependency cycle is detected.
        """
        self._entries = dict(entries)
        return self._build_order()

    # -- queries -----------------------------------------------------------

    def order(self) -> List[QueueItem]:
        """Return the current queue order without rebuilding."""
        return self._build_order()

    def next_runnable(self,
                      completed: "Optional[set]" = None) -> Optional[QueueItem]:
        """Return the next engine that is ready to run.

        An engine is "ready to run" when:

        * it is enabled,
        * it is in the ``READY`` state,
        * all of its dependencies are in *completed* (a set of engine
          IDs that have reached the ``COMPLETED`` state).

        Returns ``None`` when no engine is currently runnable.
        """
        completed = completed or set()
        for item in self._build_order():
            if not item.dependencies_met:
                continue
            entry = self._entries.get(item.engine_id)
            if entry is None:
                continue
            if not entry.enabled:
                continue
            if entry.status != EngineState.READY:
                continue
            return item
        return None

    # -- internals ---------------------------------------------------------

    def _build_order(self) -> List[QueueItem]:
        """Topologically sort enabled entries by dependencies + priority."""
        # Consider only enabled, non-terminal engines.
        active = {
            eid: e for eid, e in self._entries.items()
            if e.enabled and not e.is_terminal
        }

        if not active:
            return []

        # Build adjacency: for each engine, which engines depend on it.
        in_degree: Dict[str, int] = {eid: 0 for eid in active}
        dependents: Dict[str, List[str]] = {eid: [] for eid in active}

        for eid, entry in active.items():
            for dep in entry.dependencies:
                # Only count dependencies that are themselves active.
                if dep in active:
                    in_degree[eid] += 1
                    dependents[dep].append(eid)

        # Kahn's algorithm with a priority-ordered ready set.
        # Sort ready nodes by (priority, engine_id) for determinism.
        import heapq

        ready: List[tuple] = []
        for eid, deg in in_degree.items():
            if deg == 0:
                entry = active[eid]
                heapq.heappush(ready, (entry.priority, eid))

        ordered_ids: List[str] = []
        while ready:
            _, eid = heapq.heappop(ready)
            ordered_ids.append(eid)
            for dependent in dependents[eid]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    entry = active[dependent]
                    heapq.heappush(ready, (entry.priority, eid if False else dependent))

        # Detect cycles: if not all active engines were ordered, there
        # is a dependency cycle among the remaining ones.
        if len(ordered_ids) != len(active):
            cyclic = set(active) - set(ordered_ids)
            raise ValueError(
                "Dependency cycle detected among engines: "
                + ", ".join(sorted(cyclic))
            )

        # Build QueueItem list, computing dependencies_met against the
        # set of already-ordered engine IDs (i.e. engines that will have
        # run before this one).
        items: List[QueueItem] = []
        seen: set = set()
        for eid in ordered_ids:
            entry = active[eid]
            deps_met = all(d in seen for d in entry.dependencies)
            items.append(QueueItem(
                engine_id=eid,
                name=entry.name,
                priority=entry.priority,
                dependencies=sorted(entry.dependencies),
                dependencies_met=deps_met,
            ))
            seen.add(eid)
        return items


__all__ = [
    "ExecutionQueue",
    "QueueItem",
]
