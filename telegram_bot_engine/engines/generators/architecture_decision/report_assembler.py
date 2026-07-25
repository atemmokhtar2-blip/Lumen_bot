"""
Report assembler — assembles the final Architecture Decision Report.

The :class:`ReportAssembler` is the final step of the architecture
decision pipeline.  It takes all the pieces produced by the other
helpers (analyses, decisions, modules, services, findings, cache
info, provenance, confidence) and assembles them into a single
:class:`ArchitectureDecisionReport`.

The assembler also:
* Builds the human-readable summary.
* Builds the notes list.
* Collects warnings from all sources.
* Builds the provenance record.

The assembler does **not** write code, create files, or build the
project.  It only *assembles* the report.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from .intelligence_graph_reader import IntelligenceGraphData
from .knowledge_reader import KnowledgeData
from .requirement_intelligence_reader import (
    RequirementIntelligenceData,
)
from .requirement_normalization_reader import (
    RequirementNormalizationData,
)
from .report_data import (
    ArchitectureDecision,
    ArchitectureDecisionReport,
    ArchitectureFinding,
    ArchitectureProvenance,
    CacheInfo,
    AnalysisResult,
    ModuleSpec,
    ServiceSpec,
    SEVERITY_WARNING,
    SOURCE_INTELLIGENCE_GRAPH,
    SOURCE_KNOWLEDGE_BASE,
    SOURCE_NORMALIZED_REQUIREMENTS,
    SOURCE_REQUIREMENT_INTELLIGENCE,
    SOURCE_SEMANTIC_UNDERSTANDING,
)
from .semantic_understanding_reader import SemanticUnderstandingData


class ReportAssembler:
    """Assembles the final Architecture Decision Report.

    The assembler takes all the pieces produced by the other helpers
    and assembles them into a single
    :class:`ArchitectureDecisionReport`.

    The assembler is the only component that creates the
    :class:`ArchitectureDecisionReport` — all other helpers produce
    their individual pieces.
    """

    def assemble(
        self,
        analyses: List[AnalysisResult],
        decisions: List[ArchitectureDecision],
        modules: List[ModuleSpec],
        services: List[ServiceSpec],
        cache_info: CacheInfo,
        provenance: ArchitectureProvenance,
        confidence: float,
        confidence_level: str,
    ) -> ArchitectureDecisionReport:
        """Assemble the final report from all the pieces.

        Parameters:
            analyses: The five analysis results (size,
                scalability, performance, security,
                maintainability).
            decisions: The eight architectural decisions.
            modules: The module specifications.
            services: The service specifications.
            cache_info: The cache info.
            provenance: The provenance record.
            confidence: The overall confidence score
                (0.0–1.0).
            confidence_level: The confidence level
                (high/medium/low).

        Returns:
            A :class:`ArchitectureDecisionReport`.
        """
        report = ArchitectureDecisionReport(
            analyses=analyses,
            decisions=decisions,
            modules=modules,
            services=services,
            cache_info=cache_info,
            provenance=provenance,
            confidence=confidence,
            confidence_level=confidence_level,
        )

        # Build the summary.
        report.summary = self._build_summary(report)

        return report

    # ----------------------------------------------------------------- #
    # Summary
    # ----------------------------------------------------------------- #

    @staticmethod
    def _build_summary(
        report: ArchitectureDecisionReport,
    ) -> str:
        """Build a human-readable summary of the report."""
        return (
            f"Architecture Decision Report: "
            f"{report.analysis_count} analysis dimension(s), "
            f"{report.decision_count} decision(s), "
            f"{report.module_count} module(s), "
            f"{report.service_count} service(s), "
            f"{report.finding_count} finding(s) "
            f"({report.error_count} error(s), "
            f"{report.warning_count} warning(s)). "
            f"Confidence: {report.confidence:.1%} "
            f"({report.confidence_level}). "
            f"Cache: "
            f"{'hit' if report.cache_hit else 'miss'}. "
            f"{'Report is ready.' if report.ready else 'Report is not ready.'}"
        )

    # ----------------------------------------------------------------- #
    # Notes
    # ----------------------------------------------------------------- #

    def build_notes(
        self,
        report: ArchitectureDecisionReport,
        requirement_data: RequirementNormalizationData,
        graph_data: IntelligenceGraphData,
        requirement_intelligence_data: RequirementIntelligenceData,
        semantic_data: SemanticUnderstandingData,
        knowledge_data: KnowledgeData,
    ) -> List[str]:
        """Build the notes list for the report."""
        notes: List[str] = [
            f"Architecture Decision Report generated at "
            f"{datetime.now(timezone.utc).isoformat()}.",
            f"Data sources used: "
            f"{', '.join(report.provenance.all_sources_used)}.",
            f"Normalized requirement model available: "
            f"{report.provenance.normalized_requirements_available}.",
            f"Intelligence graph available: "
            f"{report.provenance.intelligence_graph_available}.",
            f"Requirement intelligence report available: "
            f"{report.provenance.requirement_intelligence_available}.",
            f"Semantic understanding report available: "
            f"{report.provenance.semantic_understanding_available}.",
            f"Knowledge base available: "
            f"{report.provenance.knowledge_base_available}.",
        ]

        if requirement_data.available:
            notes.append(
                f"Normalized requirements: "
                f"{requirement_data.requirement_count} requirement(s) "
                f"({requirement_data.active_requirement_count} "
                f"active), confidence: "
                f"{requirement_data.confidence:.1%}."
            )

        if graph_data.available:
            notes.append(
                f"Intelligence graph: "
                f"{graph_data.node_count} node(s), "
                f"{graph_data.edge_count} edge(s), "
                f"{graph_data.component_count} component(s), "
                f"{graph_data.service_count} service(s)."
            )

        if requirement_intelligence_data.available:
            notes.append(
                f"Requirement intelligence: "
                f"{len(requirement_intelligence_data.requirements)} "
                f"requirement(s), intent confidence: "
                f"{requirement_intelligence_data.intent_confidence:.1%}."
            )

        if semantic_data.available:
            notes.append(
                f"Semantic understanding: intent kind "
                f"'{semantic_data.intent_kind}', "
                f"{len(semantic_data.keywords)} keyword(s), "
                f"confidence: {semantic_data.confidence:.1%}."
            )

        if knowledge_data.available:
            notes.append(
                f"Knowledge base: "
                f"{len(knowledge_data.synonyms)} synonym(s), "
                f"{len(knowledge_data.abbreviations)} "
                f"abbreviation(s), "
                f"{len(knowledge_data.terminology)} terminology "
                f"mapping(s)."
            )

        if report.analysis_count > 0:
            dims = ", ".join(
                f"{a.dimension}={a.level}"
                f"({a.score:.2f})"
                for a in report.analyses
            )
            notes.append(
                f"Analysis dimensions: {dims}."
            )

        if report.decision_count > 0:
            notes.append(
                f"Decision domains covered: "
                f"{', '.join(report.decision_domains())}."
            )

        if report.module_count > 0:
            notes.append(
                f"Modules selected: "
                f"{', '.join(m.name for m in report.modules)}."
            )

        if report.service_count > 0:
            notes.append(
                f"Services selected: "
                f"{', '.join(s.name for s in report.services)}."
            )

        if report.cache_hit:
            notes.append(
                "Cache hit: the architecture decision report "
                "was served from cache."
            )

        return notes

    # ----------------------------------------------------------------- #
    # Warnings
    # ----------------------------------------------------------------- #

    @staticmethod
    def collect_warnings(
        report: ArchitectureDecisionReport,
    ) -> List[str]:
        """Collect all warnings from the report."""
        warnings: List[str] = []

        # Warnings from findings.
        for finding in report.findings:
            if finding.severity == SEVERITY_WARNING:
                warnings.append(
                    f"[{finding.code}] {finding.message}"
                )

        return warnings

    # ----------------------------------------------------------------- #
    # Provenance builder
    # ----------------------------------------------------------------- #

    @staticmethod
    def build_provenance(
        requirement_data: RequirementNormalizationData,
        graph_data: IntelligenceGraphData,
        requirement_intelligence_data: RequirementIntelligenceData,
        semantic_data: SemanticUnderstandingData,
        knowledge_data: KnowledgeData,
    ) -> ArchitectureProvenance:
        """Build the provenance record from the data sources."""
        sources_used: List[str] = []
        if requirement_data.available:
            sources_used.append(SOURCE_NORMALIZED_REQUIREMENTS)
        if graph_data.available:
            sources_used.append(SOURCE_INTELLIGENCE_GRAPH)
        if requirement_intelligence_data.available:
            sources_used.append(SOURCE_REQUIREMENT_INTELLIGENCE)
        if semantic_data.available:
            sources_used.append(SOURCE_SEMANTIC_UNDERSTANDING)
        if knowledge_data.available:
            sources_used.append(SOURCE_KNOWLEDGE_BASE)

        return ArchitectureProvenance(
            normalized_requirements_available=(
                requirement_data.available
            ),
            intelligence_graph_available=graph_data.available,
            requirement_intelligence_available=(
                requirement_intelligence_data.available
            ),
            semantic_understanding_available=(
                semantic_data.available
            ),
            knowledge_base_available=knowledge_data.available,
            all_sources_used=sources_used,
            requirement_count=requirement_data.requirement_count,
            graph_node_count=graph_data.node_count,
            graph_edge_count=graph_data.edge_count,
            intent_kind=semantic_data.intent_kind,
            semantic_confidence=semantic_data.confidence,
        )


__all__ = ["ReportAssembler"]
