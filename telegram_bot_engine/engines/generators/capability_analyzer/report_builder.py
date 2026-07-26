"""
ReportBuilder — Specification 017

Builds the Project Capability Report containing:
    - Complexity analysis
    - Resource estimation
    - Scalability analysis
    - Architecture stress analysis
    - Dependency analysis
    - Per-dimension analysis results
    - Findings, strengths, risks, recommendations
    - Provenance and confidence

The report builder assembles the final Project Capability Report
from the analysis results, findings, cache info, and provenance
data.  It also derives the overall capability verdict from the
analysis results and quality-gate outcome.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .data_readers import (
    ArchitectureDecisionData,
    TechnologySelectionData,
    RequirementNormalizationData,
    IntelligenceGraphData,
    KnowledgeData,
)
from .report_data import (
    AnalysisResult,
    ComplexityAnalysis,
    ResourceEstimation,
    ScalabilityAnalysis,
    ArchitectureStressAnalysis,
    DependencyAnalysis,
    CapabilityFinding,
    CacheInfo,
    CapabilityProvenance,
    ProjectCapabilityReport,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    SEVERITY_INFO,
    CONFIDENCE_HIGH_THRESHOLD,
    CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_CAPABLE,
    VERDICT_CAPABLE_WITH_RISKS,
    VERDICT_NOT_CAPABLE,
    DIMENSION_COMPLEXITY,
    DIMENSION_RESOURCES,
    DIMENSION_SCALABILITY,
    DIMENSION_STRESS,
    DIMENSION_DEPENDENCIES,
)

_log = logging.getLogger("engine.capability_analyzer.report_builder")


class ReportBuilder:
    """Builds the Project Capability Report.

    Assembles the final report from the five sub-analyses,
    per-dimension analysis results, findings, cache info, and
    provenance data.  Derives the overall verdict and confidence.
    """

    def __init__(self) -> None:
        pass

    def build(
        self,
        complexity: ComplexityAnalysis,
        resources: ResourceEstimation,
        scalability: ScalabilityAnalysis,
        stress: ArchitectureStressAnalysis,
        dependencies: DependencyAnalysis,
        analyses: List[AnalysisResult],
        findings: List[CapabilityFinding],
        cache_info: CacheInfo,
        provenance: CapabilityProvenance,
        gate_passed: bool,
    ) -> ProjectCapabilityReport:
        """Build the Project Capability Report.

        Args:
            complexity: The complexity analysis.
            resources: The resource estimation.
            scalability: The scalability analysis.
            stress: The architecture stress analysis.
            dependencies: The dependency analysis.
            analyses: The per-dimension analysis results.
            findings: The collected findings.
            cache_info: The cache information.
            provenance: The provenance data.
            gate_passed: Whether the quality gate passed.

        Returns:
            The complete :class:`ProjectCapabilityReport`.
        """
        report = ProjectCapabilityReport(
            complexity=complexity,
            resources=resources,
            scalability=scalability,
            stress=stress,
            dependencies=dependencies,
            analyses=analyses,
            findings=findings,
            cache_info=cache_info,
            provenance=provenance,
        )

        # Derive strengths, risks, recommendations.
        self._derive_strengths(report)
        self._derive_risks(report)
        self._derive_recommendations(report)

        # Calculate confidence.
        report.confidence = self._calculate_confidence(
            report, provenance,
        )

        # Classify confidence level.
        report.confidence_level = self._classify_confidence(
            report.confidence
        )

        # Determine verdict.
        report.verdict = self._determine_verdict(
            report, gate_passed,
        )

        # Build the summary.
        report.summary = self._build_summary(report)

        # Build the notes.
        report.notes = self._build_notes(report)

        # Collect warnings.
        report.warnings = self._collect_warnings(report)

        return report

    # ----------------------------------------------------------------- #
    # Strengths derivation
    # ----------------------------------------------------------------- #

    def _derive_strengths(
        self, report: ProjectCapabilityReport,
    ) -> None:
        """Derive strengths from the analysis results.

        Args:
            report: The report being built (mutated).
        """
        # Architecture strengths.
        if report.scalability.score >= 0.7:
            report.add_strength(
                "Architecture demonstrates strong scalability "
                "characteristics."
            )

        # Stress strengths.
        if report.stress.score >= 0.7:
            report.add_strength(
                "Architecture handles high load with acceptable "
                "performance."
            )

        # Dependency strengths.
        if report.dependencies.is_healthy and (
            len(report.dependencies.circular_dependencies) == 0
        ):
            report.add_strength(
                "Dependency graph is healthy with no circular "
                "dependencies."
            )

        # Technology strengths.
        if report.provenance.technology_selection_available:
            report.add_strength(
                "Technology selections are available and integrated "
                "into the capability analysis."
            )

        # Complexity strengths.
        if report.complexity.total_elements > 0:
            report.add_strength(
                f"Project complexity is well-defined "
                f"({report.complexity.complexity_level} level, "
                f"{report.complexity.total_elements} elements)."
            )

    # ----------------------------------------------------------------- #
    # Risks derivation
    # ----------------------------------------------------------------- #

    def _derive_risks(
        self, report: ProjectCapabilityReport,
    ) -> None:
        """Derive risks from the analysis results.

        Args:
            report: The report being built (mutated).
        """
        # Scalability risks.
        if report.scalability.score < 0.5:
            report.add_risk(
                "Scalability score is low — the architecture may "
                "struggle under growth."
            )

        # Stress risks.
        if report.stress.score < 0.5:
            report.add_risk(
                "Stress score is low — performance degradation "
                "likely under load."
            )

        # Dependency risks.
        if len(report.dependencies.circular_dependencies) > 0:
            report.add_risk(
                f"{len(report.dependencies.circular_dependencies)} circular "
                f"dependency/dependencies detected — refactor needed."
            )

        if len(report.dependencies.conflicts) > 0:
            report.add_risk(
                f"{len(report.dependencies.conflicts)} technology "
                f"conflict(s) detected — resolution needed."
            )

        if not report.dependencies.is_healthy:
            report.add_risk(
                "Dependency health is below acceptable threshold."
            )

        # Bottleneck risks.
        critical = report.critical_bottlenecks()
        if critical:
            report.add_risk(
                f"{len(critical)} critical/major bottleneck(s) "
                f"identified under stress."
            )

        # Complexity risks.
        if report.complexity.complexity_level in ("high", "very_high"):
            report.add_risk(
                f"Project complexity is {report.complexity.complexity_level} "
                f"— careful planning required."
            )

        # Data-source risks.
        if not report.provenance.technology_selection_available:
            report.add_risk(
                "Technology Selection Report was not available — "
                "analysis may be incomplete."
            )

    # ----------------------------------------------------------------- #
    # Recommendations derivation
    # ----------------------------------------------------------------- #

    def _derive_recommendations(
        self, report: ProjectCapabilityReport,
    ) -> None:
        """Derive recommendations from the analysis results.

        Args:
            report: The report being built (mutated).
        """
        # Scalability recommendations.
        if report.scalability.score < 0.6:
            report.add_recommendation(
                "Consider adopting horizontal scaling patterns and "
                "stateless services to improve scalability."
            )

        # Stress recommendations.
        for bottleneck in report.stress.bottlenecks:
            if bottleneck.improvement:
                report.add_recommendation(
                    f"Address {bottleneck.component} bottleneck: "
                    f"{bottleneck.improvement}"
                )

        # Dependency recommendations.
        if len(report.dependencies.circular_dependencies) > 0:
            report.add_recommendation(
                "Break circular dependencies by introducing "
                "interfaces or dependency inversion."
            )

        if len(report.dependencies.conflicts) > 0:
            report.add_recommendation(
                "Resolve technology conflicts by selecting "
                "compatible alternatives."
            )

        if len(report.dependencies.missing_dependencies) > 0:
            report.add_recommendation(
                "Add missing dependencies (database, cache, "
                "testing framework) as required by the project."
            )

        # Resource recommendations.
        if report.resources.memory_mb > 512:
            report.add_recommendation(
                "Plan for higher memory allocation — estimated "
                f"{report.resources.memory_mb} MB."
            )

    # ----------------------------------------------------------------- #
    # Confidence calculation
    # ----------------------------------------------------------------- #

    def _calculate_confidence(
        self,
        report: ProjectCapabilityReport,
        provenance: CapabilityProvenance,
    ) -> float:
        """Calculate the overall confidence in the capability analysis.

        The confidence is a weighted combination of:
        * Data source availability (35%).
        * Analysis coverage (30%).
        * Dependency health (20%).
        * Scalability confidence (15%).

        Args:
            report: The report being built.
            provenance: The provenance data.

        Returns:
            The confidence score (0.0-1.0).
        """
        # Data source availability (max 5 sources).
        sources_available = sum([
            provenance.architecture_decision_available,
            provenance.technology_selection_available,
            provenance.normalized_requirements_available,
            provenance.intelligence_graph_available,
            provenance.knowledge_base_available,
        ])
        source_factor = sources_available / 5.0

        # Analysis coverage (max 5 dimensions).
        performed = len(report.analysis_dimensions())
        analysis_factor = performed / 5.0

        # Dependency health.
        health_factor = report.dependencies.score

        # Scalability confidence.
        if report.scalability.tiers:
            avg_conf = sum(
                t.confidence for t in report.scalability.tiers
            ) / len(report.scalability.tiers)
        else:
            avg_conf = 0.0
        scalability_factor = avg_conf

        confidence = (
            (source_factor * 0.35)
            + (analysis_factor * 0.30)
            + (health_factor * 0.20)
            + (scalability_factor * 0.15)
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
    # Verdict determination
    # ----------------------------------------------------------------- #

    def _determine_verdict(
        self,
        report: ProjectCapabilityReport,
        gate_passed: bool,
    ) -> str:
        """Determine the overall capability verdict.

        The verdict is:
        * ``VERDICT_CAPABLE`` — the quality gate passed and the
          architecture meets all requirements.
        * ``VERDICT_CAPABLE_WITH_RISKS`` — the quality gate passed
          but there are notable risks or warnings.
        * ``VERDICT_NOT_CAPABLE`` — the quality gate failed; the
          architecture cannot meet performance/scalability/quality
          requirements.  Generation is blocked.

        Args:
            report: The report being built.
            gate_passed: Whether the quality gate passed.

        Returns:
            The verdict string.
        """
        if not gate_passed:
            return VERDICT_NOT_CAPABLE

        # If there are error-level findings, block.
        if report.has_errors:
            return VERDICT_NOT_CAPABLE

        # If there are risks or warnings, capable with risks.
        if report.risks or report.warning_count > 0:
            return VERDICT_CAPABLE_WITH_RISKS

        return VERDICT_CAPABLE

    # ----------------------------------------------------------------- #
    # Summary builder
    # ----------------------------------------------------------------- #

    def _build_summary(
        self, report: ProjectCapabilityReport,
    ) -> str:
        """Build a human-readable summary of the report.

        Args:
            report: The Project Capability Report.

        Returns:
            A summary string.
        """
        parts: List[str] = []

        # Verdict.
        parts.append(
            f"Project Capability Report: verdict={report.verdict}."
        )

        # Analysis count.
        parts.append(
            f"Analyses performed: {report.analysis_count} "
            f"dimension(s)."
        )

        # Complexity.
        parts.append(
            f"Complexity: {report.complexity.complexity_level} "
            f"({report.complexity.total_elements} elements)."
        )

        # Scalability.
        parts.append(
            f"Scalability: score={report.scalability.score:.2f}, "
            f"max tier={report.max_scalability_tier}."
        )

        # Stress.
        parts.append(
            f"Stress: score={report.stress.score:.2f}, "
            f"max load={report.stress.load_level}."
        )

        # Dependencies.
        parts.append(
            f"Dependencies: health={report.dependencies.score:.2f}, "
            f"circular={len(report.dependencies.circular_dependencies)}, "
            f"conflicts={len(report.dependencies.conflicts)}."
        )

        # Findings.
        if report.has_errors:
            parts.append(
                f"WARNING: {report.error_count} error(s) found."
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
        self, report: ProjectCapabilityReport,
    ) -> List[str]:
        """Build notes for the report.

        Args:
            report: The Project Capability Report.

        Returns:
            A list of note strings.
        """
        notes: List[str] = []

        provenance = report.provenance

        # Source availability.
        sources: List[str] = []
        if provenance.architecture_decision_available:
            sources.append("Architecture Decision Report")
        if provenance.technology_selection_available:
            sources.append("Technology Selection Report")
        if provenance.normalized_requirements_available:
            sources.append("Normalized Requirement Model")
        if provenance.intelligence_graph_available:
            sources.append("Project Intelligence Graph")
        if provenance.knowledge_base_available:
            sources.append("Knowledge Base")

        if sources:
            notes.append(
                f"Data sources used: {', '.join(sources)}."
            )
        else:
            notes.append(
                "No data sources were available. "
                "Capability analysis is based on defaults."
            )

        # Cache status.
        if report.cache_hit:
            notes.append(
                "Report was served from cache."
            )

        # Complexity notes.
        notes.append(
            f"Project complexity level: "
            f"{report.complexity.complexity_level}."
        )

        # Resource notes.
        notes.append(
            f"Estimated project size: "
            f"{report.resources.project_size_level}, "
            f"{report.resources.file_count} files."
        )

        # Scalability notes.
        if report.scalability.tiers:
            supported_tiers = [
                t.tier for t in report.scalability.tiers if t.supported
            ]
            if supported_tiers:
                notes.append(
                    f"Supported scalability tiers: "
                    f"{', '.join(supported_tiers)}."
                )
            else:
                notes.append(
                    "No scalability tiers are fully supported."
                )

        # Stress notes.
        if report.stress.bottlenecks:
            notes.append(
                f"Bottlenecks identified: "
                f"{len(report.stress.bottlenecks)}."
            )

        # Dependency notes.
        if not report.dependencies.is_healthy:
            notes.append(
                "Dependency graph health is below acceptable "
                "threshold."
            )

        return notes

    # ----------------------------------------------------------------- #
    # Warnings collector
    # ----------------------------------------------------------------- #

    def _collect_warnings(
        self, report: ProjectCapabilityReport,
    ) -> List[str]:
        """Collect warning messages from the report.

        Args:
            report: The Project Capability Report.

        Returns:
            A list of warning strings.
        """
        warnings: List[str] = []
        for finding in report.findings:
            if finding.severity == SEVERITY_WARNING:
                warnings.append(f"[{finding.code}] {finding.message}")
        return warnings

    # ----------------------------------------------------------------- #
    # Provenance builder
    # ----------------------------------------------------------------- #

    def build_provenance(
        self,
        architecture_data: ArchitectureDecisionData,
        technology_data: TechnologySelectionData,
        requirement_data: RequirementNormalizationData,
        graph_data: IntelligenceGraphData,
        knowledge_data: KnowledgeData,
    ) -> CapabilityProvenance:
        """Build the provenance data from reader outputs.

        Args:
            architecture_data: Architecture decision reader output.
            technology_data: Technology selection reader output.
            requirement_data: Requirement normalization reader output.
            graph_data: Intelligence graph reader output.
            knowledge_data: Knowledge base reader output.

        Returns:
            A :class:`CapabilityProvenance` instance.
        """
        provenance = CapabilityProvenance(
            architecture_decision_available=(
                architecture_data.available
            ),
            technology_selection_available=technology_data.available,
            normalized_requirements_available=(
                requirement_data.available
            ),
            intelligence_graph_available=graph_data.available,
            knowledge_base_available=knowledge_data.available,
        )

        # Collect all sources used.
        sources: List[str] = []
        if architecture_data.available:
            sources.append("architecture_decision_report")
        if technology_data.available:
            sources.append("technology_selection_report")
        if requirement_data.available:
            sources.append("normalized_requirements")
        if graph_data.available:
            sources.append("intelligence_graph")
        if knowledge_data.available:
            sources.append("knowledge_base")
        provenance.all_sources_used = sources

        # Extract counts.
        provenance.decision_count = architecture_data.decision_count
        provenance.selection_count = technology_data.selection_count
        provenance.requirement_count = requirement_data.requirement_count
        provenance.graph_node_count = graph_data.node_count
        provenance.graph_edge_count = graph_data.edge_count

        return provenance


__all__ = ["ReportBuilder"]
