"""DependencyAnalyzer + ReuseDetector — Specification 022"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Dict, List, Set, Tuple

from .report_data import (
    ComponentDescriptor,
    ComponentRelation,
    ComponentConflict,
    ReuseOpportunity,
    DEP_HARD,
    COMM_INTERFACE,
    CONFLICT_CIRCULAR_DEPENDENCY,
    CONFLICT_HIDDEN_DEPENDENCY,
    CONFLICT_STRONG_COUPLING,
    CONFLICT_UNUSED_COMPONENT,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
)

_log = logging.getLogger("engine.component_architecture_planning.dependency_analyzer")


class DependencyAnalyzer:
    def analyze(
        self,
        components: List[ComponentDescriptor],
    ) -> Tuple[List[ComponentRelation], List[ComponentConflict], Dict[str, List[str]], List[ReuseOpportunity]]:
        relations: List[ComponentRelation] = []
        conflicts: List[ComponentConflict] = []
        known = {c.component_id for c in components}

        for c in components:
            for dep in c.depends_on:
                relations.append(ComponentRelation(
                    from_component_id=c.component_id,
                    to_component_id=dep,
                    relation_type=DEP_HARD,
                    communication=COMM_INTERFACE,
                    reason=f"Declared dependency of {c.name}",
                ))
                if dep not in known:
                    conflicts.append(ComponentConflict(
                        conflict_id=f"hidden_{c.component_id}_{dep}",
                        conflict_type=CONFLICT_HIDDEN_DEPENDENCY,
                        severity=SEVERITY_HIGH,
                        message=f"Component '{c.component_id}' depends on unknown '{dep}'.",
                        affected_components=[c.component_id, dep],
                        resolution_hint="Create the missing component or remove the dependency.",
                    ))

        # Cycles
        graph: Dict[str, List[str]] = defaultdict(list)
        for r in relations:
            if r.to_component_id in known:
                graph[r.from_component_id].append(r.to_component_id)

        for cycle in self._cycles(graph):
            conflicts.append(ComponentConflict(
                conflict_id=f"cycle_{'_'.join(cycle[:3])}",
                conflict_type=CONFLICT_CIRCULAR_DEPENDENCY,
                severity=SEVERITY_CRITICAL,
                message=f"Circular component dependency: {' → '.join(cycle + [cycle[0]])}",
                affected_components=list(cycle),
                resolution_hint="Break the cycle with an interface or event.",
            ))

        # Strong coupling
        for c in components:
            if len(c.depends_on) > 4:
                conflicts.append(ComponentConflict(
                    conflict_id=f"coupling_{c.component_id}",
                    conflict_type=CONFLICT_STRONG_COUPLING,
                    severity=SEVERITY_MEDIUM,
                    message=f"Component '{c.name}' has {len(c.depends_on)} hard dependencies.",
                    affected_components=[c.component_id],
                    resolution_hint="Split or use events to reduce coupling.",
                ))

        # Unused (no one depends on it and it depends on nothing special)
        referenced = {r.to_component_id for r in relations}
        for c in components:
            if c.component_id not in referenced and not c.depends_on and "test" not in c.component_id:
                # only flag pure leaves that look unused
                if c.kind in ("helper", "utility") and not c.reusable:
                    conflicts.append(ComponentConflict(
                        conflict_id=f"unused_{c.component_id}",
                        conflict_type=CONFLICT_UNUSED_COMPONENT,
                        severity=SEVERITY_MEDIUM,
                        message=f"Component '{c.name}' appears unused.",
                        affected_components=[c.component_id],
                        resolution_hint="Remove or mark as reusable entry-point.",
                    ))

        # Reuse opportunities: same kind + similar name across modules
        by_kind_name: Dict[str, List[str]] = defaultdict(list)
        for c in components:
            key = f"{c.kind}:{c.name.split()[-1].lower()}"
            by_kind_name[key].append(c.component_id)

        reuses: List[ReuseOpportunity] = []
        for key, ids in by_kind_name.items():
            if len(ids) >= 2:
                reuses.append(ReuseOpportunity(
                    opportunity_id=f"reuse_{key.replace(':', '_')}",
                    component_ids=ids,
                    reason=f"Multiple components share kind/name pattern '{key}'",
                    suggested_shared_name=key.split(":")[-1].title() + "Shared",
                ))

        dep_graph = {c.component_id: list(c.depends_on) for c in components}
        _log.info("DependencyAnalyzer: %d relations, %d conflicts, %d reuses",
                  len(relations), len(conflicts), len(reuses))
        return relations, conflicts, dep_graph, reuses

    def _cycles(self, graph: Dict[str, List[str]]) -> List[List[str]]:
        cycles: List[List[str]] = []
        visited: Set[str] = set()
        stack: Set[str] = set()
        path: List[str] = []

        def dfs(n: str) -> None:
            if n in stack:
                try:
                    cycles.append(path[path.index(n):])
                except ValueError:
                    cycles.append([n])
                return
            if n in visited:
                return
            visited.add(n)
            stack.add(n)
            path.append(n)
            for nb in graph.get(n, []):
                dfs(nb)
            path.pop()
            stack.discard(n)

        for n in list(graph):
            if n not in visited:
                dfs(n)
        return cycles


__all__ = ["DependencyAnalyzer"]
