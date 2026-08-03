"""
DependencyAnalyzer — Specification 021

Builds module relations, detects circular / hidden / strong-coupling
problems and produces the dependency graph.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Dict, List, Set, Tuple

from .report_data import (
    ModuleDescriptor,
    ModuleRelation,
    ArchitectureConflict,
    DEP_HARD,
    COMM_INTERFACE,
    CONFLICT_CIRCULAR_DEPENDENCY,
    CONFLICT_STRONG_COUPLING,
    CONFLICT_HIDDEN_DEPENDENCY,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
)

_log = logging.getLogger("engine.module_architecture_planning.dependency_analyzer")


class DependencyAnalyzer:
    def __init__(self) -> None:
        self.relations: List[ModuleRelation] = []
        self.conflicts: List[ArchitectureConflict] = []

    def analyze(
        self,
        modules: List[ModuleDescriptor],
    ) -> Tuple[List[ModuleRelation], List[ArchitectureConflict], Dict[str, List[str]]]:
        self.relations = []
        self.conflicts = []

        by_id = {m.module_id: m for m in modules}

        # Collect declared dependencies
        for m in modules:
            for dep_id in m.depends_on:
                self.relations.append(ModuleRelation(
                    from_module_id=m.module_id,
                    to_module_id=dep_id,
                    relation_type=DEP_HARD,
                    communication=COMM_INTERFACE,
                    reason=f"Declared dependency of {m.name}",
                ))

        # Detect missing targets
        known = set(by_id.keys())
        for rel in self.relations:
            if rel.to_module_id not in known:
                self.conflicts.append(ArchitectureConflict(
                    conflict_id=f"hidden_{rel.from_module_id}_{rel.to_module_id}",
                    conflict_type=CONFLICT_HIDDEN_DEPENDENCY,
                    severity=SEVERITY_HIGH,
                    message=(
                        f"Module '{rel.from_module_id}' depends on unknown "
                        f"module '{rel.to_module_id}'."
                    ),
                    affected_modules=[rel.from_module_id, rel.to_module_id],
                    resolution_hint="Create the missing module or remove the dependency.",
                ))

        # Circular dependency detection
        graph: Dict[str, List[str]] = defaultdict(list)
        for rel in self.relations:
            if rel.to_module_id in known:
                graph[rel.from_module_id].append(rel.to_module_id)

        cycles = self._find_cycles(graph)
        for cycle in cycles:
            self.conflicts.append(ArchitectureConflict(
                conflict_id=f"cycle_{'_'.join(cycle[:3])}",
                conflict_type=CONFLICT_CIRCULAR_DEPENDENCY,
                severity=SEVERITY_CRITICAL,
                message=f"Circular module dependency: {' → '.join(cycle + [cycle[0]])}",
                affected_modules=list(cycle),
                resolution_hint="Break the cycle by introducing an interface or reordering.",
            ))

        # Strong coupling heuristic: module depends on > 4 others
        for m in modules:
            if len(m.depends_on) > 4:
                self.conflicts.append(ArchitectureConflict(
                    conflict_id=f"coupling_{m.module_id}",
                    conflict_type=CONFLICT_STRONG_COUPLING,
                    severity=SEVERITY_MEDIUM,
                    message=(
                        f"Module '{m.name}' has {len(m.depends_on)} hard dependencies "
                        f"(possible strong coupling)."
                    ),
                    affected_modules=[m.module_id],
                    resolution_hint="Consider splitting the module or using events.",
                ))

        dep_graph = {m.module_id: list(m.depends_on) for m in modules}
        _log.info(
            "DependencyAnalyzer: %d relations, %d conflicts",
            len(self.relations), len(self.conflicts),
        )
        return self.relations, self.conflicts, dep_graph

    def _find_cycles(self, graph: Dict[str, List[str]]) -> List[List[str]]:
        cycles: List[List[str]] = []
        visited: Set[str] = set()
        stack: Set[str] = set()
        path: List[str] = []

        def dfs(node: str) -> None:
            if node in stack:
                try:
                    idx = path.index(node)
                    cycles.append(path[idx:])
                except ValueError:
                    cycles.append([node])
                return
            if node in visited:
                return
            visited.add(node)
            stack.add(node)
            path.append(node)
            for nb in graph.get(node, []):
                dfs(nb)
            path.pop()
            stack.discard(node)

        for n in list(graph.keys()):
            if n not in visited:
                dfs(n)
        return cycles


__all__ = ["DependencyAnalyzer"]
