"""
Data readers for the Project Capability Analyzer Engine
(Specification 017).

These readers extract data from the artefacts produced by upstream
engines and feed them into the Project Capability Analyzer Engine.

Data sources:
    1. Architecture Decision Report
    2. Technology Selection Report
    3. Normalized Requirement Model
    4. Project Intelligence Graph
    5. Knowledge Base
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from ....core.context import GenerationContext


# ---------------------------------------------------------------------------#
# Architecture Decision Reader
# ---------------------------------------------------------------------------#

@dataclass
class ArchitectureDecisionData:
    """Data extracted from the Architecture Decision Report.

    Attributes:
        available: Whether the data was found.
        pattern: The selected architecture pattern.
        layers: The selected layers.
        modules: The module specifications.
        services: The service specifications.
        communication: The communication pattern.
        decisions: The architecture decisions list.
        decision_count: Number of decisions.
        module_count: Number of modules.
        service_count: Number of services.
    """

    available: bool = False
    pattern: str = ""
    layers: List[str] = field(default_factory=list)
    modules: List[Dict[str, Any]] = field(default_factory=list)
    services: List[Dict[str, Any]] = field(default_factory=list)
    communication: str = ""
    decisions: List[Dict[str, Any]] = field(default_factory=list)
    decision_count: int = 0
    module_count: int = 0
    service_count: int = 0


class ArchitectureDecisionReader:
    """Reads the Architecture Decision Report from the context."""

    def read(self, context: GenerationContext) -> ArchitectureDecisionData:
        """Extract architecture decision data from the context.

        Args:
            context: The generation context.

        Returns:
            An :class:`ArchitectureDecisionData` instance.
        """
        data = ArchitectureDecisionData()

        report = context.get("architecture_decision_report")
        if report is None:
            return data

        data.available = True

        if hasattr(report, "to_dict"):
            report_dict = report.to_dict()
            decisions_list = report_dict.get("decisions", [])

            for d in decisions_list:
                if d.get("domain") == "layers":
                    data.pattern = d.get("selected", "")
                    selected = d.get("selected", "")
                    if selected:
                        data.layers = [
                            l.strip()
                            for l in selected.split(",")
                            if l.strip()
                        ]
                    break

            for d in decisions_list:
                if d.get("domain") == "communication":
                    data.communication = d.get("selected", "")
                    break

            data.decisions = decisions_list
            data.decision_count = len(decisions_list)

            modules_list = report_dict.get("modules", [])
            if isinstance(modules_list, list):
                data.modules = [
                    m if isinstance(m, dict) else m.to_dict()
                    if hasattr(m, "to_dict") else m
                    for m in modules_list
                ]
                data.module_count = len(data.modules)

            services_list = report_dict.get("services", [])
            if isinstance(services_list, list):
                data.services = [
                    s if isinstance(s, dict) else s.to_dict()
                    if hasattr(s, "to_dict") else s
                    for s in services_list
                ]
                data.service_count = len(data.services)
        elif isinstance(report, dict):
            decisions_list = report.get("decisions", [])
            data.decisions = decisions_list
            data.decision_count = len(decisions_list)

            for d in decisions_list:
                if isinstance(d, dict) and d.get("domain") == "layers":
                    data.pattern = d.get("selected", "")
                    selected = d.get("selected", "")
                    if selected:
                        data.layers = [
                            l.strip()
                            for l in selected.split(",")
                            if l.strip()
                        ]
                    break

            for d in decisions_list:
                if isinstance(d, dict) and d.get("domain") == "communication":
                    data.communication = d.get("selected", "")
                    break

            modules_list = report.get("modules", [])
            if isinstance(modules_list, list):
                data.modules = modules_list
                data.module_count = len(modules_list)

            services_list = report.get("services", [])
            if isinstance(services_list, list):
                data.services = services_list
                data.service_count = len(services_list)

        return data


# ---------------------------------------------------------------------------#
# Technology Selection Reader
# ---------------------------------------------------------------------------#

@dataclass
class TechnologySelectionData:
    """Data extracted from the Technology Selection Report.

    Attributes:
        available: Whether the data was found.
        selections: The technology selections.
        selection_count: Number of selections.
        ready: Whether the technology selection report is ready.
        confidence: The confidence of the technology selections.
        selected_technologies: A flat list of selected technology
            names.
    """

    available: bool = False
    selections: List[Dict[str, Any]] = field(default_factory=list)
    selection_count: int = 0
    ready: bool = False
    confidence: float = 0.0
    selected_technologies: List[str] = field(default_factory=list)


class TechnologySelectionReader:
    """Reads the Technology Selection Report from the context."""

    def read(self, context: GenerationContext) -> TechnologySelectionData:
        """Extract technology selection data from the context.

        Args:
            context: The generation context.

        Returns:
            A :class:`TechnologySelectionData` instance.
        """
        data = TechnologySelectionData()

        report = context.get("technology_selection_report")
        if report is None:
            return data

        data.available = True

        if hasattr(report, "to_dict"):
            report_dict = report.to_dict()
            data.selections = report_dict.get("selections", [])
            data.selection_count = report_dict.get("selection_count", 0)
            data.ready = report_dict.get("ready", False)
            data.confidence = report_dict.get("confidence", 0.0)
        elif isinstance(report, dict):
            data.selections = report.get("selections", [])
            data.selection_count = report.get("selection_count", 0)
            data.ready = report.get("ready", False)
            data.confidence = report.get("confidence", 0.0)

        # Build a flat list of selected technology names.
        for sel in data.selections:
            if isinstance(sel, dict):
                name = sel.get("selected", "")
                if name:
                    data.selected_technologies.append(name)

        return data


# ---------------------------------------------------------------------------#
# Requirement Normalization Reader
# ---------------------------------------------------------------------------#

@dataclass
class RequirementNormalizationData:
    """Data extracted from the Normalized Requirement Model.

    Attributes:
        available: Whether the data was found.
        requirements: The list of normalized requirements.
        requirement_count: Number of requirements.
        non_functional: Non-functional requirements.
        functional: Functional requirements.
    """

    available: bool = False
    requirements: List[Dict[str, Any]] = field(default_factory=list)
    requirement_count: int = 0
    non_functional: List[Dict[str, Any]] = field(default_factory=list)
    functional: List[Dict[str, Any]] = field(default_factory=list)


class RequirementNormalizationReader:
    """Reads the Normalized Requirement Model from the context."""

    def read(self, context: GenerationContext) -> RequirementNormalizationData:
        """Extract requirement normalization data from the context.

        Args:
            context: The generation context.

        Returns:
            An :class:`RequirementNormalizationData` instance.
        """
        data = RequirementNormalizationData()

        report = context.get("requirement_normalization_report")
        if report is None:
            return data

        data.available = True

        if hasattr(report, "to_dict"):
            report_dict = report.to_dict()
            data.requirements = report_dict.get("requirements", [])
            data.non_functional = report_dict.get(
                "non_functional", []
            )
            data.functional = report_dict.get("functional", [])
        elif isinstance(report, dict):
            data.requirements = report.get("requirements", [])
            data.non_functional = report.get("non_functional", [])
            data.functional = report.get("functional", [])

        data.requirement_count = len(data.requirements)
        return data


# ---------------------------------------------------------------------------#
# Intelligence Graph Reader
# ---------------------------------------------------------------------------#

@dataclass
class IntelligenceGraphData:
    """Data extracted from the Project Intelligence Graph.

    Attributes:
        available: Whether the data was found.
        nodes: The graph nodes.
        edges: The graph edges.
        node_count: Number of nodes.
        edge_count: Number of edges.
        component_count: Number of components.
        feature_count: Number of features.
        service_count: Number of services.
        file_count: Number of files.
        circular_count: Number of circular dependencies detected.
        node_type_counts: Counts by node type.
        edge_kind_counts: Counts by edge kind.
    """

    available: bool = False
    nodes: List[Dict[str, Any]] = field(default_factory=list)
    edges: List[Dict[str, Any]] = field(default_factory=list)
    node_count: int = 0
    edge_count: int = 0
    component_count: int = 0
    feature_count: int = 0
    service_count: int = 0
    file_count: int = 0
    circular_count: int = 0
    node_type_counts: Dict[str, int] = field(default_factory=dict)
    edge_kind_counts: Dict[str, int] = field(default_factory=dict)


class IntelligenceGraphReader:
    """Reads the Project Intelligence Graph from the context."""

    def read(self, context: GenerationContext) -> IntelligenceGraphData:
        """Extract intelligence graph data from the context.

        Args:
            context: The generation context.

        Returns:
            An :class:`IntelligenceGraphData` instance.
        """
        data = IntelligenceGraphData()

        graph = context.get("intelligence_graph")
        if graph is None:
            return data

        data.available = True

        if hasattr(graph, "to_dict"):
            graph_dict = graph.to_dict()
            data.nodes = graph_dict.get("nodes", [])
            data.edges = graph_dict.get("edges", [])
            data.node_type_counts = graph_dict.get(
                "node_type_counts", {}
            )
            data.edge_kind_counts = graph_dict.get(
                "edge_kind_counts", {}
            )
            data.component_count = graph_dict.get("component_count", 0)
            data.feature_count = graph_dict.get("feature_count", 0)
            data.service_count = graph_dict.get("service_count", 0)
            data.file_count = graph_dict.get("file_count", 0)
            data.circular_count = graph_dict.get("circular_count", 0)
        elif isinstance(graph, dict):
            data.nodes = graph.get("nodes", [])
            data.edges = graph.get("edges", [])
            data.node_type_counts = graph.get("node_type_counts", {})
            data.edge_kind_counts = graph.get("edge_kind_counts", {})
            data.component_count = graph.get("component_count", 0)
            data.feature_count = graph.get("feature_count", 0)
            data.service_count = graph.get("service_count", 0)
            data.file_count = graph.get("file_count", 0)
            data.circular_count = graph.get("circular_count", 0)

        data.node_count = len(data.nodes)
        data.edge_count = len(data.edges)
        return data


# ---------------------------------------------------------------------------#
# Knowledge Base Reader
# ---------------------------------------------------------------------------#

@dataclass
class KnowledgeData:
    """Data extracted from the Knowledge Base.

    Attributes:
        available: Whether the data was found.
        assumptions: Known assumptions.
        defaults: Default values.
        domain_rules: Domain-specific rules.
        constraints: Known constraints.
    """

    available: bool = False
    assumptions: List[str] = field(default_factory=list)
    defaults: Dict[str, Any] = field(default_factory=dict)
    domain_rules: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)


class KnowledgeReader:
    """Reads the Knowledge Base from the context."""

    def read(self, context: GenerationContext) -> KnowledgeData:
        """Extract knowledge base data from the context.

        Args:
            context: The generation context.

        Returns:
            A :class:`KnowledgeData` instance.
        """
        data = KnowledgeData()

        kb = context.get("knowledge_base")
        if kb is None:
            return data

        data.available = True

        if hasattr(kb, "to_dict"):
            kb_dict = kb.to_dict()
            data.assumptions = kb_dict.get("assumptions", [])
            data.defaults = kb_dict.get("defaults", {})
            data.domain_rules = kb_dict.get("domain_rules", [])
            data.constraints = kb_dict.get("constraints", [])
        elif isinstance(kb, dict):
            data.assumptions = kb.get("assumptions", [])
            data.defaults = kb.get("defaults", {})
            data.domain_rules = kb.get("domain_rules", [])
            data.constraints = kb.get("constraints", [])

        return data


__all__ = [
    "ArchitectureDecisionData",
    "ArchitectureDecisionReader",
    "TechnologySelectionData",
    "TechnologySelectionReader",
    "RequirementNormalizationData",
    "RequirementNormalizationReader",
    "IntelligenceGraphData",
    "IntelligenceGraphReader",
    "KnowledgeData",
    "KnowledgeReader",
]
