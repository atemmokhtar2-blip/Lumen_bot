"""
ReportBuilder — Specification 016

Builds the Technology Selection Report containing:
    - Selected technologies
    - Selection reasons
    - Alternatives
    - Pros and cons of each decision

The report builder assembles the final Technology Selection Report
from the analysis results, technology selections, findings, and
provenance data.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .data_readers import (
    ArchitectureDecisionData,
    RequirementNormalizationData,
    IntelligenceGraphData,
    KnowledgeData,
    QualityRulesData,
)
from .report_data import (
    AnalysisResult,
    TechnologySelection,
    TechnologyFinding,
    CacheInfo,
    TechnologyProvenance,
    TechnologySelectionReport,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    SEVERITY_INFO,
    CONFIDENCE_HIGH_THRESHOLD,
    CONFIDENCE_MEDIUM_THRESHOLD,
)

_log = logging.getLogger("engine.technology_selection.report_builder")


class ReportBuilder:
    """Builds the Technology Selection Report.

    Assembles the final report from analysis results, technology
    selections, findings, and provenance data.
    """

    def __init__(self) -> None:
        pass

    def build(
        self,
        analyses: List[AnalysisResult],
        selections: List[TechnologySelection],
        findings: List[TechnologyFinding],
        cache_info: CacheInfo,
        provenance: TechnologyProvenance,
    ) -> TechnologySelectionReport:
        """Build the Technology Selection Report.

        Args:
            analyses: The list of analysis results.
            selections: The list of technology selections.
            findings: The list of findings.
            cache_info: The cache information.
            provenance: The provenance data.

        Returns:
            The complete :class:`TechnologySelectionReport`.
        """
        report = TechnologySelectionReport(
            analyses=analyses,
            selections=selections,
            findings=findings,
            cache_info=cache_info,
            provenance=provenance,
        )

        # Build the summary.
        report.summary = self._build_summary(report)

        # Build the notes.
        report.notes = self._build_notes(report)

        # Collect warnings.
        report.warnings = self._collect_warnings(report)

        # Calculate confidence.
        report.confidence = self._calculate_confidence(
            provenance, selections
        )

        # Classify confidence level.
        report.confidence_level = self._classify_confidence(
            report.confidence
        )

        return report

    # ----------------------------------------------------------------- #
    # Summary builder
    # ----------------------------------------------------------------- #

    def _build_summary(
        self, report: TechnologySelectionReport
    ) -> str:
        """Build a human-readable summary of the report.

        Args:
            report: The Technology Selection Report.

        Returns:
            A summary string.
        """
        parts = []

        # Selection count.
        parts.append(
            f"Technology Selection Report: "
            f"{report.selection_count} technologies selected."
        )

        # Analysis dimensions.
        dims = report.analysis_dimensions()
        if dims:
            parts.append(
                f"Analyses performed: {', '.join(dims)}."
            )

        # Findings summary.
        if report.has_errors:
            parts.append(
                f"WARNING: {report.error_count} error(s) found "
                f"in technology selections."
            )
        if report.warning_count > 0:
            parts.append(
                f"{report.warning_count} warning(s) noted."
            )

        # Confidence.
        parts.append(
            f"Confidence: {report.confidence:.2f} "
            f"({report.confidence_level})."
        )

        # Readiness.
        if report.ready:
            parts.append("Report is ready for downstream use.")
        else:
            parts.append("Report is NOT ready for downstream use.")

        return " ".join(parts)

    # ----------------------------------------------------------------- #
    # Notes builder
    # ----------------------------------------------------------------- #

    def _build_notes(
        self, report: TechnologySelectionReport
    ) -> List[str]:
        """Build notes for the report.

        Args:
            report: The Technology Selection Report.

        Returns:
            A list of note strings.
        """
        notes = []

        provenance = report.provenance

        # Source availability.
        sources = []
        if provenance.architecture_decision_available:
            sources.append("Architecture Decision Report")
        if provenance.normalized_requirements_available:
            sources.append("Normalized Requirement Model")
        if provenance.intelligence_graph_available:
            sources.append("Project Intelligence Graph")
        if provenance.knowledge_base_available:
            sources.append("Knowledge Base")
        if provenance.quality_rules_available:
            sources.append("Quality Rules")

        if sources:
            notes.append(
                f"Data sources used: {', '.join(sources)}."
            )
        else:
            notes.append(
                "No data sources were available. "
                "Technology selections are based on defaults."
            )

        # Cache status.
        if report.cache_hit:
            notes.append(
                "Report was served from cache."
            )

        # Selection highlights.
        if report.selections:
            highlights = []
            for sel in report.selections:
                highlights.append(
                    f"{sel.category}: {sel.selected}"
                )
            notes.append(
                f"Selected technologies: {', '.join(highlights)}."
            )

        # Quality notes.
        if not report.all_selections_validated:
            notes.append(
                "Some technology selections are missing "
                "required fields (reason, analysis, impact, "
                "or alternatives)."
            )

        return notes

    # ----------------------------------------------------------------- #
    # Warnings collector
    # ----------------------------------------------------------------- #

    def _collect_warnings(
        self, report: TechnologySelectionReport
    ) -> List[str]:
        """Collect warning messages from the report.

        Args:
            report: The Technology Selection Report.

        Returns:
            A list of warning strings.
        """
        warnings = []
        for finding in report.findings:
            if finding.severity == SEVERITY_WARNING:
                warnings.append(f"[{finding.code}] {finding.message}")
        return warnings

    # ----------------------------------------------------------------- #
    # Confidence calculation
    # ----------------------------------------------------------------- #

    def _calculate_confidence(
        self,
        provenance: TechnologyProvenance,
        selections: List[TechnologySelection],
    ) -> float:
        """Calculate the overall confidence in the technology
        selections.

        The confidence is a weighted combination of:
        * Data source availability (40%).
        * Number of selections (20%).
        * Number of validated selections (25%).
        * Analysis coverage (15%).

        Args:
            provenance: The provenance data.
            selections: The list of technology selections.

        Returns:
            The confidence score (0.0-1.0).
        """
        # Data source availability (max 5 sources).
        sources_available = sum([
            provenance.architecture_decision_available,
            provenance.normalized_requirements_available,
            provenance.intelligence_graph_available,
            provenance.knowledge_base_available,
            provenance.quality_rules_available,
        ])
        source_factor = sources_available / 5.0

        # Number of selections (expect 10).
        if selections:
            selection_factor = min(len(selections) / 10.0, 1.0)
        else:
            selection_factor = 0.0

        # Number of validated selections.
        if selections:
            validated = sum(
                1 for s in selections
                if (
                    s.reason
                    and s.analysis
                    and s.impact
                    and s.rejected_alternatives
                )
            )
            validated_factor = validated / len(selections)
        else:
            validated_factor = 0.0

        # Analysis coverage (expect 4 dimensions).
        analysis_factor = 1.0  # All 4 analyses are always performed.

        confidence = (
            (source_factor * 0.4)
            + (selection_factor * 0.2)
            + (validated_factor * 0.25)
            + (analysis_factor * 0.15)
        )

        return max(0.0, min(1.0, confidence))

    @staticmethod
    def _classify_confidence(confidence: float) -> str:
        """Classify the confidence into high/medium/low.

        Args:
            confidence: The confidence score.

        Returns:
            The confidence level string.
        """
        if confidence >= CONFIDENCE_HIGH_THRESHOLD:
            return "high"
        if confidence >= CONFIDENCE_MEDIUM_THRESHOLD:
            return "medium"
        return "low"

    # ----------------------------------------------------------------- #
    # Provenance builder
    # ----------------------------------------------------------------- #

    def build_provenance(
        self,
        architecture_data: ArchitectureDecisionData,
        requirement_data: RequirementNormalizationData,
        graph_data: IntelligenceGraphData,
        knowledge_data: KnowledgeData,
        quality_data: QualityRulesData,
    ) -> TechnologyProvenance:
        """Build the provenance data from reader outputs.

        Args:
            architecture_data: Architecture decision reader output.
            requirement_data: Requirement normalization reader output.
            graph_data: Intelligence graph reader output.
            knowledge_data: Knowledge base reader output.
            quality_data: Quality rules reader output.

        Returns:
            A :class:`TechnologyProvenance` instance.
        """
        provenance = TechnologyProvenance(
            architecture_decision_available=architecture_data.available,
            normalized_requirements_available=requirement_data.available,
            intelligence_graph_available=graph_data.available,
            knowledge_base_available=knowledge_data.available,
            quality_rules_available=quality_data.available,
        )

        # Collect all sources used.
        sources = []
        if architecture_data.available:
            sources.append("architecture_decision_report")
        if requirement_data.available:
            sources.append("normalized_requirements")
        if graph_data.available:
            sources.append("intelligence_graph")
        if knowledge_data.available:
            sources.append("knowledge_base")
        if quality_data.available:
            sources.append("quality_rules")
        provenance.all_sources_used = sources

        # Extract counts.
        provenance.decision_count = architecture_data.decision_count
        provenance.requirement_count = requirement_data.requirement_count
        provenance.graph_node_count = graph_data.node_count
        provenance.graph_edge_count = graph_data.edge_count

        return provenance


__all__ = ["ReportBuilder"]
