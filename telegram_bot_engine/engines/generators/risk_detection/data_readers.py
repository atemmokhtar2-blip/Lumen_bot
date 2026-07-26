"""
Data readers for the Risk Detection Engine (Specification 018).

These readers extract data from the artefacts produced by upstream
engines and feed them into the Risk Detection Engine.

The Risk Detection Engine reads **five** data sources:

1. **Project Capability Report** -- the
   ``project_capability_report`` artefact produced by the
   :class:`~telegram_bot_engine.engines.generators.capability_analyzer.ProjectCapabilityAnalyzerEngine`.
2. **Architecture Decision Report** -- the
   ``architecture_decision_report`` artefact produced by the
   :class:`~telegram_bot_engine.engines.generators.architecture_decision.ArchitectureDecisionEngine`.
3. **Technology Selection Report** -- the
   ``technology_selection_report`` artefact produced by the
   :class:`~telegram_bot_engine.engines.generators.technology_selection.TechnologySelectionEngine`.
4. **Normalized Requirement Model** -- the
   ``requirement_normalization_report`` artefact produced by the
   :class:`~telegram_bot_engine.engines.generators.requirement_normalization.RequirementNormalizationEngine`.
5. **Knowledge Base** -- the ``knowledge_base`` artefact, if
   present.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from ....core.context import GenerationContext


# ---------------------------------------------------------------------------#
# Project Capability Report Reader
# ---------------------------------------------------------------------------#

@dataclass
class ProjectCapabilityData:
    """Data extracted from the Project Capability Report.

    The Project Capability Report is the primary upstream input for
    the Risk Detection Engine.  It carries the capability analysis
    (complexity, resources, scalability, stress, dependencies) and
    the overall capability verdict.

    Attributes:
        available: Whether the data was found.
        ready: Whether the capability report is ready.
        verdict: The capability verdict (capable, capable_with_risks,
            not_capable).
        confidence: The capability report confidence (0.0-1.0).
        complexity_level: The project complexity level.
        total_elements: The total number of architectural elements.
        scalability_score: The scalability analysis score (0.0-1.0).
        stress_score: The architecture stress score (0.0-1.0).
        load_level: The maximum sustainable load level.
        max_scalability_tier: The maximum scalability tier.
        dependency_health: The dependency health score (0.0-1.0).
        circular_dependencies: The number of circular dependencies.
        dependency_conflicts: The number of dependency conflicts.
        missing_dependencies: The number of missing dependencies.
        total_dependencies: The total number of dependencies.
        estimated_memory_mb: The estimated memory in MB.
        file_count: The estimated file count.
        bottlenecks: The list of detected bottlenecks.
        analysis_dimensions: The list of analysis dimensions performed.
    """

    available: bool = False
    ready: bool = False
    verdict: str = ""
    confidence: float = 0.0
    complexity_level: str = ""
    total_elements: int = 0
    scalability_score: float = 0.0
    stress_score: float = 0.0
    load_level: str = ""
    max_scalability_tier: str = ""
    dependency_health: float = 0.0
    circular_dependencies: int = 0
    dependency_conflicts: int = 0
    missing_dependencies: int = 0
    total_dependencies: int = 0
    estimated_memory_mb: int = 0
    file_count: int = 0
    bottlenecks: List[Dict[str, Any]] = field(default_factory=list)
    analysis_dimensions: List[str] = field(default_factory=list)


class ProjectCapabilityReader:
    """Reads the Project Capability Report from the context."""

    def read(self, context: GenerationContext) -> ProjectCapabilityData:
        """Extract project capability data from the context.

        Args:
            context: The generation context.

        Returns:
            A :class:`ProjectCapabilityData` instance.
        """
        data = ProjectCapabilityData()

        report = context.get("project_capability_report")
        if report is None:
            return data

        data.available = True

        if hasattr(report, "to_dict"):
            report_dict = report.to_dict()
        elif isinstance(report, dict):
            report_dict = report
        else:
            return data

        data.ready = report_dict.get("ready", False)
        data.verdict = report_dict.get("verdict", "")
        data.confidence = report_dict.get("confidence", 0.0)

        # Complexity.
        complexity = report_dict.get("complexity", {})
        if isinstance(complexity, dict):
            data.complexity_level = complexity.get(
                "complexity_level", ""
            )
            data.total_elements = complexity.get("total_elements", 0)
        elif hasattr(complexity, "to_dict"):
            cd = complexity.to_dict()
            data.complexity_level = cd.get("complexity_level", "")
            data.total_elements = cd.get("total_elements", 0)

        # Scalability.
        scalability = report_dict.get("scalability", {})
        if isinstance(scalability, dict):
            data.scalability_score = scalability.get("score", 0.0)
        elif hasattr(scalability, "to_dict"):
            data.scalability_score = scalability.to_dict().get(
                "score", 0.0
            )

        # Max scalability tier (top-level helper).
        data.max_scalability_tier = report_dict.get(
            "max_scalability_tier", ""
        )

        # Stress.
        stress = report_dict.get("stress", {})
        if isinstance(stress, dict):
            data.stress_score = stress.get("score", 0.0)
            data.load_level = stress.get("load_level", "")
            bottlenecks = stress.get("bottlenecks", [])
            if isinstance(bottlenecks, list):
                data.bottlenecks = [
                    b if isinstance(b, dict) else (
                        b.to_dict() if hasattr(b, "to_dict") else b
                    )
                    for b in bottlenecks
                ]
        elif hasattr(stress, "to_dict"):
            sd = stress.to_dict()
            data.stress_score = sd.get("score", 0.0)
            data.load_level = sd.get("load_level", "")
            bottlenecks = sd.get("bottlenecks", [])
            if isinstance(bottlenecks, list):
                data.bottlenecks = bottlenecks

        # Dependencies.
        dependencies = report_dict.get("dependencies", {})
        if isinstance(dependencies, dict):
            data.dependency_health = dependencies.get("score", 0.0)
            data.circular_dependencies = len(
                dependencies.get("circular_dependencies", [])
            )
            data.dependency_conflicts = len(
                dependencies.get("conflicts", [])
            )
            data.missing_dependencies = len(
                dependencies.get("missing_dependencies", [])
            )
            data.total_dependencies = dependencies.get(
                "total_count", 0
            )
        elif hasattr(dependencies, "to_dict"):
            dd = dependencies.to_dict()
            data.dependency_health = dd.get("score", 0.0)
            data.circular_dependencies = len(
                dd.get("circular_dependencies", [])
            )
            data.dependency_conflicts = len(
                dd.get("conflicts", [])
            )
            data.missing_dependencies = len(
                dd.get("missing_dependencies", [])
            )
            data.total_dependencies = dd.get("total_count", 0)

        # Resources.
        resources = report_dict.get("resources", {})
        if isinstance(resources, dict):
            data.estimated_memory_mb = resources.get("memory_mb", 0)
            data.file_count = resources.get("file_count", 0)
        elif hasattr(resources, "to_dict"):
            rd = resources.to_dict()
            data.estimated_memory_mb = rd.get("memory_mb", 0)
            data.file_count = rd.get("file_count", 0)

        # Analysis dimensions.
        analyses = report_dict.get("analyses", [])
        if isinstance(analyses, list):
            data.analysis_dimensions = [
                a.get("dimension", "")
                if isinstance(a, dict)
                else getattr(a, "dimension", "")
                for a in analyses
            ]

        return data


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
                if isinstance(d, dict) and d.get(
                    "domain"
                ) == "communication":
                    data.communication = d.get("selected", "")
                    break

            data.decisions = decisions_list
            data.decision_count = len(decisions_list)

            modules_list = report_dict.get("modules", [])
            if isinstance(modules_list, list):
                data.modules = [
                    m if isinstance(m, dict) else (
                        m.to_dict() if hasattr(m, "to_dict") else m
                    )
                    for m in modules_list
                ]
                data.module_count = len(data.modules)

            services_list = report_dict.get("services", [])
            if isinstance(services_list, list):
                data.services = [
                    s if isinstance(s, dict) else (
                        s.to_dict() if hasattr(s, "to_dict") else s
                    )
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
                if isinstance(d, dict) and d.get(
                    "domain"
                ) == "communication":
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
            data.selection_count = report_dict.get(
                "selection_count", 0
            )
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

    def read(
        self, context: GenerationContext
    ) -> RequirementNormalizationData:
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
    "ProjectCapabilityData",
    "ProjectCapabilityReader",
    "ArchitectureDecisionData",
    "ArchitectureDecisionReader",
    "TechnologySelectionData",
    "TechnologySelectionReader",
    "RequirementNormalizationData",
    "RequirementNormalizationReader",
    "KnowledgeData",
    "KnowledgeReader",
]
