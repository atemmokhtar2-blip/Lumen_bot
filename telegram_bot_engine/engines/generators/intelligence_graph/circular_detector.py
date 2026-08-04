"""
Circular detector (Specification 011).

The :class:`CircularDetector` analyses the
:class:`ProjectIntelligenceGraph` for structural problems that would
cause issues for downstream engines.  It detects:

* **Circular dependencies** — a chain of ``depends_on`` (or
  ``imports``, ``uses``, ``required_by``) edges that loops back to the
  starting node.  Circular dependencies must be broken before
  construction can proceed reliably.
* **Broken references** — an edge whose source or target node does not
  exist in the graph.  These indicate a linking error during graph
  building.
* **Unused components** — a component node that has no incoming edges
  at all (no feature references it, no other component uses it, no
  stage contains it).  Unused components may indicate over-engineering
  or a missing relationship.
* **Orphan files** — a file node that is not contained by any folder
  and not referenced by any component.  Orphan files may indicate a
  structure-map inconsistency.
* **Dead components** — a component node that has no outgoing edges
  (it does not use any dependency, does not create any file, and does
  not belong to any stage).  Dead components contribute nothing to the
  project and may indicate a planning gap.

The detector uses depth-first search (DFS) with a recursion stack to
find cycles in the directed graph of dependency-like edges.  The
algorithm runs in O(V + E) time where V is the number of nodes and E
is the number of edges in the dependency subgraph.

The detector does **not** write code, create files, or make build
decisions.  It is a pure analysis helper that produces
:class:`GraphFinding` objects.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set

from .graph_data import (
    ProjectIntelligenceGraph,
    GraphFinding,
    GraphNode,
    GraphIndices,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    SEVERITY_INFO,
    CATEGORY_CIRCULAR_DEPENDENCY,
    CATEGORY_BROKEN_REFERENCE,
    CATEGORY_UNUSED_COMPONENT,
    CATEGORY_ORPHAN_FILE,
    CATEGORY_DEAD_COMPONENT,
    NODE_TYPE_COMPONENT,
    NODE_TYPE_FILE,
    NODE_TYPE_DEPENDENCY,
    EDGE_DEPENDS_ON,
    EDGE_IMPORTS,
    EDGE_USES,
    EDGE_REQUIRED_BY,
    EDGE_CONTAINS,
)


# Edge kinds that, when followed, indicate a forward dependency
# relationship.  Cycles among these edges are the "circular
# dependencies" the specification requires us to detect.
#
# EDGE_REQUIRED_BY is intentionally excluded: it is the *reverse* of
# EDGE_DEPENDS_ON (and EDGE_USES).  When the builder records both
# ``comp --depends_on--> dep`` and ``dep --required_by--> comp``,
# including EDGE_REQUIRED_BY in this set would produce a false 2-cycle
# for every component-dependency pair.  The forward edges alone are
# sufficient to detect genuine circular dependencies.
_DEPENDENCY_EDGE_KINDS = frozenset({
    EDGE_DEPENDS_ON,
    EDGE_IMPORTS,
    EDGE_USES,
})


class CircularDetector:
    """Detect structural problems in the intelligence graph.

    The detector is stateless — it takes the graph and returns a list
    of :class:`GraphFinding` objects.
    """

    def detect(self, graph: ProjectIntelligenceGraph) -> List[GraphFinding]:
        """Analyse the graph and return a list of findings.

        Findings with ``severity == SEVERITY_ERROR`` indicate
        structural problems that make the graph unreliable for
        downstream engines (circular dependencies, broken references).
        Findings with ``severity == SEVERITY_WARNING`` indicate
        potential issues that downstream engines should be aware of
        (unused components, orphan files).  Findings with
        ``severity == SEVERITY_INFO`` are informational (dead
        components).
        """
        findings: List[GraphFinding] = []

        findings.extend(self._detect_circular_dependencies(graph))
        findings.extend(self._detect_broken_references(graph))
        findings.extend(self._detect_unused_components(graph))
        findings.extend(self._detect_orphan_files(graph))
        findings.extend(self._detect_dead_components(graph))

        return findings

    # ------------------------------------------------------------------ #
    # Circular dependency detection (DFS with recursion stack)
    # ------------------------------------------------------------------ #

    def _detect_circular_dependencies(
        self, graph: ProjectIntelligenceGraph,
    ) -> List[GraphFinding]:
        """Detect circular dependencies using DFS.

        We build a directed adjacency list from the dependency-like
        edges (depends_on, imports, uses, required_by) and run a DFS
        that tracks the current path (recursion stack).  When we
        encounter a node that is already on the current path, we have
        found a cycle.  The cycle is recorded as a finding with the
        full path of node IDs.
        """
        findings: List[GraphFinding] = []

        # Build the adjacency list from dependency-like edges.
        # Skip self-edges — a node depending on itself is noise, not a cycle.
        adj: Dict[str, List[str]] = {}
        for edge in graph.edges:
            if edge.kind in _DEPENDENCY_EDGE_KINDS:
                if edge.source_id == edge.target_id:
                    continue
                adj.setdefault(edge.source_id, []).append(edge.target_id)

        if not adj:
            return findings

        # Standard DFS-based cycle detection with three colours:
        #   WHITE (not in visited): unvisited
        #   GREY  (in stack): on the current DFS path
        #   BLACK (in done): fully explored, no cycle through it
        visited: Set[str] = set()
        done: Set[str] = set()
        stack: List[str] = []
        seen_cycles: Set[tuple] = set()

        def _dfs(node_id: str) -> None:
            if node_id in done:
                return
            if node_id in visited:
                # We found a node on the current path — extract the
                # cycle from the stack.
                if node_id in stack:
                    cycle_start = stack.index(node_id)
                    cycle = stack[cycle_start:] + [node_id]
                    # Normalise the cycle so that the same cycle
                    # detected from different starting points is not
                    # reported twice.
                    norm = self._normalise_cycle(cycle)
                    if norm not in seen_cycles:
                        seen_cycles.add(norm)
                        node_names = self._cycle_node_names(
                            graph, cycle,
                        )
                        findings.append(GraphFinding(
                            severity=SEVERITY_ERROR,
                            code="circular_dependency",
                            message=(
                                "Circular dependency detected: "
                                + " -> ".join(node_names)
                            ),
                            affected=cycle[0],
                            category=CATEGORY_CIRCULAR_DEPENDENCY,
                            resolution_hint=(
                                "Break the cycle by removing one "
                                "of the dependency edges or by "
                                "introducing an interface to "
                                "decouple the components."
                            ),
                            cycle=cycle,
                        ))
                return

            visited.add(node_id)
            stack.append(node_id)

            for neighbour in adj.get(node_id, []):
                _dfs(neighbour)

            stack.pop()
            done.add(node_id)

        # Run DFS from every node to catch all cycles in disconnected
        # subgraphs.
        for node_id in adj:
            if node_id not in visited and node_id not in done:
                _dfs(node_id)

        return findings

    @staticmethod
    def _normalise_cycle(cycle: List[str]) -> tuple:
        """Normalise a cycle so that the same cycle detected from
        different starting points produces the same key.

        We rotate the cycle so that the lexicographically smallest
        node ID is first, then drop the duplicate last element (which
        equals the first).
        """
        if len(cycle) <= 1:
            return tuple(cycle)
        # Drop the trailing duplicate (the cycle is A -> B -> A).
        core = cycle[:-1]
        if not core:
            return tuple(cycle)
        min_idx = core.index(min(core))
        rotated = core[min_idx:] + core[:min_idx]
        return tuple(rotated)

    @staticmethod
    def _cycle_node_names(
        graph: ProjectIntelligenceGraph,
        cycle: List[str],
    ) -> List[str]:
        """Convert a cycle of node IDs to a list of human-readable
        node names."""
        names: List[str] = []
        for node_id in cycle:
            node = graph.indices.node_by_id.get(node_id)
            if node is not None:
                names.append(node.name)
            else:
                names.append(node_id)
        return names

    # ------------------------------------------------------------------ #
    # Broken reference detection
    # ------------------------------------------------------------------ #

    def _detect_broken_references(
        self, graph: ProjectIntelligenceGraph,
    ) -> List[GraphFinding]:
        """Detect edges that reference non-existent nodes.

        Every edge has a source_id and a target_id.  If either of
        these does not correspond to a node in the graph, the edge is
        a broken reference — it points to nothing.
        """
        findings: List[GraphFinding] = []

        node_ids: Set[str] = set(graph.indices.node_by_id.keys())

        for edge in graph.edges:
            if edge.source_id not in node_ids:
                findings.append(GraphFinding(
                    severity=SEVERITY_ERROR,
                    code="broken_reference_source",
                    message=(
                        f"Edge '{edge.edge_id}' has a source node "
                        f"'{edge.source_id}' that does not exist "
                        f"in the graph."
                    ),
                    affected=edge.edge_id,
                    category=CATEGORY_BROKEN_REFERENCE,
                    resolution_hint=(
                        "Ensure the source node is created before "
                        "the edge is added, or remove the edge."
                    ),
                ))
            if edge.target_id not in node_ids:
                findings.append(GraphFinding(
                    severity=SEVERITY_ERROR,
                    code="broken_reference_target",
                    message=(
                        f"Edge '{edge.edge_id}' has a target node "
                        f"'{edge.target_id}' that does not exist "
                        f"in the graph."
                    ),
                    affected=edge.edge_id,
                    category=CATEGORY_BROKEN_REFERENCE,
                    resolution_hint=(
                        "Ensure the target node is created before "
                        "the edge is added, or remove the edge."
                    ),
                ))

        return findings

    # ------------------------------------------------------------------ #
    # Unused component detection
    # ------------------------------------------------------------------ #

    def _detect_unused_components(
        self, graph: ProjectIntelligenceGraph,
    ) -> List[GraphFinding]:
        """Detect component nodes that have no incoming edges.

        A component is "unused" when no other element in the graph
        points to it — no feature implements it, no other component
        uses it, no stage contains it.  An unused component may
        indicate over-engineering or a missing relationship.
        """
        findings: List[GraphFinding] = []

        component_ids: List[str] = graph.indices.nodes_by_type.get(
            NODE_TYPE_COMPONENT, [],
        )
        if not component_ids:
            return findings

        for comp_id in component_ids:
            in_edges = graph.indices.in_edges.get(comp_id, [])
            if not in_edges:
                node = graph.indices.node_by_id.get(comp_id)
                name = node.name if node else comp_id
                findings.append(GraphFinding(
                    severity=SEVERITY_WARNING,
                    code="unused_component",
                    message=(
                        f"Component '{name}' has no incoming "
                        f"edges — no feature, component, or "
                        f"stage references it."
                    ),
                    affected=comp_id,
                    category=CATEGORY_UNUSED_COMPONENT,
                    resolution_hint=(
                        "Ensure the component is referenced by a "
                        "feature or assigned to a stage, or "
                        "remove it if it is not needed."
                    ),
                ))

        return findings

    # ------------------------------------------------------------------ #
    # Orphan file detection
    # ------------------------------------------------------------------ #

    def _detect_orphan_files(
        self, graph: ProjectIntelligenceGraph,
    ) -> List[GraphFinding]:
        """Detect file nodes that are not contained by any folder and
        not referenced by any component.

        A file is "orphan" when no folder contains it and no
        component references it.  This may indicate a
        structure-map inconsistency — the file was planned but never
        placed in the project structure.
        """
        findings: List[GraphFinding] = []

        file_ids: List[str] = graph.indices.nodes_by_type.get(
            NODE_TYPE_FILE, [],
        )
        if not file_ids:
            return findings

        for file_id in file_ids:
            in_edges = graph.indices.in_edges.get(file_id, [])
            if not in_edges:
                node = graph.indices.node_by_id.get(file_id)
                name = node.name if node else file_id
                findings.append(GraphFinding(
                    severity=SEVERITY_WARNING,
                    code="orphan_file",
                    message=(
                        f"File '{name}' has no incoming edges — "
                        f"it is not contained by any folder and "
                        f"not referenced by any component."
                    ),
                    affected=file_id,
                    category=CATEGORY_ORPHAN_FILE,
                    resolution_hint=(
                        "Ensure the file is placed in a folder "
                        "in the structure map or referenced by "
                        "a component."
                    ),
                ))

        return findings

    # ------------------------------------------------------------------ #
    # Dead component detection
    # ------------------------------------------------------------------ #

    def _detect_dead_components(
        self, graph: ProjectIntelligenceGraph,
    ) -> List[GraphFinding]:
        """Detect component nodes that have no outgoing edges.

        A component is "dead" when it has no outgoing edges — it
        does not use any dependency, does not create any file, and
        does not belong to any stage.  A dead component contributes
        nothing to the project and may indicate a planning gap.
        """
        findings: List[GraphFinding] = []

        component_ids: List[str] = graph.indices.nodes_by_type.get(
            NODE_TYPE_COMPONENT, [],
        )
        if not component_ids:
            return findings

        for comp_id in component_ids:
            out_edges = graph.indices.out_edges.get(comp_id, [])
            if not out_edges:
                node = graph.indices.node_by_id.get(comp_id)
                name = node.name if node else comp_id
                findings.append(GraphFinding(
                    severity=SEVERITY_INFO,
                    code="dead_component",
                    message=(
                        f"Component '{name}' has no outgoing "
                        f"edges — it does not use any dependency, "
                        f"create any file, or belong to any stage."
                    ),
                    affected=comp_id,
                    category=CATEGORY_DEAD_COMPONENT,
                    resolution_hint=(
                        "Ensure the component has files and "
                        "dependencies assigned to it, or remove "
                        "it if it is not needed."
                    ),
                ))

        return findings


__all__ = ["CircularDetector"]
