"""
Dependency Graph \u2014 the full dependency map of the project plan
(Specification 004).

The :class:`DependencyGraph` answers four questions that the execution
plan and the generator engines need:

1. **What must be built first?** \u2014 the root nodes (no dependencies).
2. **What depends on what?** \u2014 the edges of the graph.
3. **What can be built in parallel?** \u2014 nodes whose dependencies are
   all satisfied at the same level.
4. **What must be deferred?** \u2014 nodes whose dependencies cannot be
   satisfied early.

The graph is built from the :class:`InternalComponent` and
:class:`FeatureUnit` dependency information by the planning engine.  It
is a plain data container with read-only query helpers \u2014 it does
not schedule execution (that is the :class:`ExecutionPlan`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

@dataclass
class DependencyNode:
    """A single node in the dependency graph.

    Attributes:
        name: The node name (a component or feature name).
        kind: ``"component"`` or ``"feature"``.
        dependencies: The names this node depends on.
        dependents: The names that depend on this node.
        priority: Build priority (lower first).
        parallel_group: The parallel group this node belongs to.  Nodes
            in the same group can be built concurrently.
        level: The topological level of the node (0 = root, 1 = depends
            only on roots, etc.).
    """

    name: str
    kind: str = "component"
    dependencies: List[str] = field(default_factory=list)
    dependents: List[str] = field(default_factory=list)
    priority: int = 100
    parallel_group: int = 0
    level: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "dependencies": list(self.dependencies),
            "dependents": list(self.dependents),
            "priority": self.priority,
            "parallel_group": self.parallel_group,
            "level": self.level,
        }


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

class DependencyGraph:
    """The full dependency map of the project plan.

    The graph is populated by the planning engine and queried by the
    execution plan builder.  It supports both component-level and
    feature-level nodes.
    """

    def __init__(self) -> None:
        self._nodes: Dict[str, DependencyNode] = {}

    # -- population --------------------------------------------------------

    def add_node(self, name: str, kind: str = "component",
                 priority: int = 100,
                 dependencies: Optional[List[str]] = None) -> DependencyNode:
        """Add a node to the graph (idempotent on name)."""
        if name in self._nodes:
            node = self._nodes[name]
            if dependencies is not None:
                for dep in dependencies:
                    if dep not in node.dependencies:
                        node.dependencies.append(dep)
            return node
        node = DependencyNode(
            name=name,
            kind=kind,
            priority=priority,
            dependencies=list(dependencies or []),
        )
        self._nodes[name] = node
        return node

    def add_edge(self, source: str, target: str) -> None:
        """Declare that *source* depends on *target*."""
        src = self._nodes.get(source)
        tgt = self._nodes.get(target)
        if src is None:
            src = self.add_node(source)
        if tgt is None:
            self.add_node(target)
        if target not in src.dependencies:
            src.dependencies.append(target)
        if source not in tgt.dependents:
            tgt.dependents.append(source)

    # -- queries -----------------------------------------------------------

    def get(self, name: str) -> Optional[DependencyNode]:
        return self._nodes.get(name)

    def all_nodes(self) -> List[DependencyNode]:
        return list(self._nodes.values())

    def names(self) -> List[str]:
        return list(self._nodes.keys())

    def count(self) -> int:
        return len(self._nodes)

    def roots(self) -> List[DependencyNode]:
        """Return nodes with no dependencies (build first)."""
        return [n for n in self._nodes.values() if not n.dependencies]

    def leaves(self) -> List[DependencyNode]:
        """Return nodes with no dependents (built last)."""
        return [n for n in self._nodes.values() if not n.dependents]

    def dependencies_of(self, name: str) -> List[str]:
        node = self._nodes.get(name)
        return list(node.dependencies) if node else []

    def dependents_of(self, name: str) -> List[str]:
        node = self._nodes.get(name)
        return list(node.dependents) if node else []

    def has_cycle(self) -> bool:
        """Return ``True`` if the graph contains a dependency cycle."""
        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[str, int] = {n: WHITE for n in self._nodes}

        def visit(node_name: str) -> bool:
            color[node_name] = GRAY
            for dep in self._nodes[node_name].dependencies:
                if dep not in self._nodes:
                    continue  # dangling dependency, not a cycle
                if color[dep] == GRAY:
                    return True
                if color[dep] == WHITE and visit(dep):
                    return True
            color[node_name] = BLACK
            return False

        return any(color[n] == WHITE and visit(n) for n in self._nodes)

    def dangling_dependencies(self) -> List[str]:
        """Return dependency names that are not registered nodes."""
        all_names = set(self._nodes)
        missing: Set[str] = set()
        for node in self._nodes.values():
            for dep in node.dependencies:
                if dep not in all_names:
                    missing.add(dep)
        return sorted(missing)

    def compute_levels(self) -> Dict[str, int]:
        """Compute the topological level of each node.

        Root nodes are level 0.  A node's level is one more than the
        maximum level of its dependencies.

        Returns a mapping of node name \u2192 level.  Nodes involved in
        a cycle are not assigned a level (they are excluded).
        """
        levels: Dict[str, int] = {}
        remaining = dict(self._nodes)

        current_level = 0
        while remaining:
            # Find nodes whose dependencies are all already levelled.
            ready = [
                n for n, node in remaining.items()
                if all(dep in levels for dep in node.dependencies
                       if dep in self._nodes)
            ]
            if not ready:
                # Cycle: remaining nodes cannot be levelled.
                break
            for n in ready:
                deps_levels = [
                    levels[d] for d in self._nodes[n].dependencies
                    if d in levels
                ]
                levels[n] = current_level if not deps_levels else \
                    max(deps_levels) + 1
                del remaining[n]
            current_level += 1
        return levels

    def parallel_groups(self) -> Dict[int, List[str]]:
        """Group nodes by their level for parallel execution.

        Nodes in the same group (level) can be built concurrently
        because all of their dependencies are in lower groups.
        """
        levels = self.compute_levels()
        groups: Dict[int, List[str]] = {}
        for name, level in levels.items():
            groups.setdefault(level, []).append(name)
        # Sort each group by priority then name for determinism.
        for level in groups:
            groups[level].sort(
                key=lambda n: (self._nodes[n].priority, n)
            )
        return groups

    def build_order(self) -> List[str]:
        """Return a flat, dependency-respecting build order."""
        order: List[str] = []
        for level in sorted(self.parallel_groups()):
            order.extend(self.parallel_groups()[level])
        return order

    def can_build_in_parallel(self, name_a: str, name_b: str) -> bool:
        """Return ``True`` if two nodes can be built in parallel.

        Two nodes can be built in parallel when neither depends on the
        other (directly or transitively).
        """
        if self.depends_on(name_a, name_b) or self.depends_on(name_b, name_a):
            return False
        return True

    def depends_on(self, source: str, target: str,
                   seen: Optional[Set[str]] = None) -> bool:
        """Return ``True`` if *source* transitively depends on *target*."""
        seen = seen or set()
        if source in seen:
            return False
        seen.add(source)
        node = self._nodes.get(source)
        if not node:
            return False
        if target in node.dependencies:
            return True
        return any(self.depends_on(dep, target, seen)
                   for dep in node.dependencies)

    def deferred_nodes(self) -> List[str]:
        """Return nodes whose dependencies are not all satisfiable.

        Currently this returns nodes involved in a cycle (if any) plus
        nodes with dangling dependencies.
        """
        levels = self.compute_levels()
        all_names = set(self._nodes)
        unlevelled = all_names - set(levels)
        return sorted(unlevelled)

    # -- serialisation -----------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        levels = self.compute_levels()
        # Apply computed levels and parallel groups to nodes.
        for name, level in levels.items():
            self._nodes[name].level = level
        groups = self.parallel_groups()
        for level, names in groups.items():
            for n in names:
                self._nodes[n].parallel_group = level
        return {
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "parallel_groups": {
                str(k): v for k, v in groups.items()
            },
            "build_order": self.build_order(),
            "has_cycle": self.has_cycle(),
            "dangling_dependencies": self.dangling_dependencies(),
        }


__all__ = [
    "DependencyGraph",
    "DependencyNode",
]
