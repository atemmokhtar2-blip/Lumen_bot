"""
Intelligence graph reader -- reads the Project Intelligence Graph
from the generation context.

The :class:`IntelligenceGraphReader` is responsible for obtaining
the ``intelligence_graph`` artefact (produced by the
:class:`~telegram_bot_engine.engines.generators.intelligence_graph.IntelligenceGraphEngine`)
and returning a normalised :class:`IntelligenceGraphData` object.

The reader is tolerant: it never raises when the intelligence graph
is not available.  It returns a :class:`IntelligenceGraphData` with
``available=False`` in that case.

This module is a pure reader: it has no side effects and does not
modify the generation context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from ....core.context import GenerationContext
from .report_data import SOURCE_INTELLIGENCE_GRAPH


# ---------------------------------------------------------------------------#
# Intelligence graph data
# ---------------------------------------------------------------------------#

@dataclass
class IntelligenceGraphData:
    """Normalised view of the Project Intelligence Graph.

    This is a lightweight container that holds the information the
    Architecture Decision Engine needs from the Intelligence Graph.

    Attributes:
        node_count: The total number of nodes.
        edge_count: The total number of edges.
        node_type_counts: A mapping of node type -> count.
        edge_kind_counts: A mapping of edge kind -> count.
        component_count: The number of component nodes.
        feature_count: The number of feature nodes.
        service_count: The number of service nodes.
        dependency_count: The number of dependency nodes.
        file_count: The number of file nodes.
        finding_count: The number of findings.
        circular_count: The number of circular dependency findings.
        available: Whether the intelligence graph was available.
    """

    node_count: int = 0
    edge_count: int = 0
    node_type_counts: Dict[str, int] = field(default_factory=dict)
    edge_kind_counts: Dict[str, int] = field(default_factory=dict)
    component_count: int = 0
    feature_count: int = 0
    service_count: int = 0
    dependency_count: int = 0
    file_count: int = 0
    finding_count: int = 0
    circular_count: int = 0
    available: bool = False

    @property
    def source_artefact(self) -> str:
        return SOURCE_INTELLIGENCE_GRAPH

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "node_type_counts": dict(self.node_type_counts),
            "edge_kind_counts": dict(self.edge_kind_counts),
            "component_count": self.component_count,
            "feature_count": self.feature_count,
            "service_count": self.service_count,
            "dependency_count": self.dependency_count,
            "file_count": self.file_count,
            "finding_count": self.finding_count,
            "circular_count": self.circular_count,
            "available": self.available,
        }


class IntelligenceGraphReader:
    """Reads the Project Intelligence Graph from the generation
    context.

    The reader looks for the ``intelligence_graph`` artefact.  When
    present, it extracts the node/edge counts, node type counts, edge
    kind counts, component/feature/service/dependency/file counts, and
    findings.  When absent, it returns a
    :class:`IntelligenceGraphData` with ``available=False``.
    """

    def read(self, context: GenerationContext) -> IntelligenceGraphData:
        """Read the intelligence graph and return a
        :class:`IntelligenceGraphData`.
        """
        graph = context.get("intelligence_graph")
        if graph is None:
            return IntelligenceGraphData(available=False)

        return self._read_from_graph(graph)

    # ----------------------------------------------------------------- #
    # Internal helpers
    # ----------------------------------------------------------------- #

    def _read_from_graph(
        self, graph: Any,
    ) -> IntelligenceGraphData:
        """Extract data from the intelligence graph artefact."""
        def get_attr(name: str, default: Any = None) -> Any:
            if hasattr(graph, name):
                return getattr(graph, name)
            if isinstance(graph, dict):
                return graph.get(name, default)
            return default

        # Node and edge counts.
        node_count = 0
        if hasattr(graph, "node_count"):
            try:
                node_count = int(graph.node_count)
            except (TypeError, ValueError):
                node_count = 0
        elif isinstance(get_attr("nodes"), (list, tuple)):
            node_count = len(get_attr("nodes"))

        edge_count = 0
        if hasattr(graph, "edge_count"):
            try:
                edge_count = int(graph.edge_count)
            except (TypeError, ValueError):
                edge_count = 0
        elif isinstance(get_attr("edges"), (list, tuple)):
            edge_count = len(get_attr("edges"))

        # Node type counts.
        node_type_counts: Dict[str, int] = {}
        if hasattr(graph, "node_type_counts"):
            try:
                ntc = graph.node_type_counts()
                if isinstance(ntc, dict):
                    node_type_counts = {
                        str(k): int(v) for k, v in ntc.items()
                    }
            except (TypeError, ValueError):
                pass
        elif isinstance(get_attr("node_type_counts"), dict):
            node_type_counts = {
                str(k): int(v)
                for k, v in get_attr("node_type_counts").items()
            }

        # Edge kind counts.
        edge_kind_counts: Dict[str, int] = {}
        if hasattr(graph, "edge_kind_counts"):
            try:
                ekc = graph.edge_kind_counts()
                if isinstance(ekc, dict):
                    edge_kind_counts = {
                        str(k): int(v) for k, v in ekc.items()
                    }
            except (TypeError, ValueError):
                pass
        elif isinstance(get_attr("edge_kind_counts"), dict):
            edge_kind_counts = {
                str(k): int(v)
                for k, v in get_attr("edge_kind_counts").items()
            }

        # Component, feature, service, dependency, file counts.
        component_count = self._count_nodes_of_type(
            graph, "component",
        )
        feature_count = self._count_nodes_of_type(
            graph, "feature",
        )
        service_count = self._count_nodes_of_type(
            graph, "service",
        )
        dependency_count = self._count_nodes_of_type(
            graph, "dependency",
        )
        file_count = self._count_nodes_of_type(
            graph, "file",
        )

        # Findings.
        finding_count = 0
        circular_count = 0
        findings_raw = get_attr("findings", []) or []
        if isinstance(findings_raw, (list, tuple)):
            finding_count = len(findings_raw)
            for finding in findings_raw:
                if isinstance(finding, dict):
                    category = str(finding.get("category", "") or "")
                elif hasattr(finding, "category"):
                    category = str(
                        getattr(finding, "category", "") or ""
                    )
                else:
                    category = ""
                if "circular" in category:
                    circular_count += 1

        return IntelligenceGraphData(
            node_count=node_count,
            edge_count=edge_count,
            node_type_counts=node_type_counts,
            edge_kind_counts=edge_kind_counts,
            component_count=component_count,
            feature_count=feature_count,
            service_count=service_count,
            dependency_count=dependency_count,
            file_count=file_count,
            finding_count=finding_count,
            circular_count=circular_count,
            available=True,
        )

    @staticmethod
    def _count_nodes_of_type(graph: Any, node_type: str) -> int:
        """Count the number of nodes of a given type."""
        # Try the nodes_of_type method.
        if hasattr(graph, "nodes_of_type"):
            try:
                nodes = graph.nodes_of_type(node_type)
                if isinstance(nodes, (list, tuple)):
                    return len(nodes)
            except (TypeError, ValueError):
                pass

        # Try the node_type_count method.
        if hasattr(graph, "node_type_count"):
            try:
                # This might be a property or a method.
                count = graph.node_type_count
                if callable(count):
                    count = count()
                if isinstance(count, dict):
                    return int(count.get(node_type, 0))
            except (TypeError, ValueError):
                pass

        # Try the indices.
        if hasattr(graph, "indices"):
            indices = graph.indices
            if hasattr(indices, "nodes_by_type"):
                nbt = indices.nodes_by_type
                if isinstance(nbt, dict):
                    nodes = nbt.get(node_type, [])
                    if isinstance(nodes, (list, tuple)):
                        return len(nodes)

        return 0


__all__ = [
    "IntelligenceGraphReader",
    "IntelligenceGraphData",
]
