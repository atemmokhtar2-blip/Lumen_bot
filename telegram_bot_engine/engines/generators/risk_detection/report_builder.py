"""
ReportBuilder -- Specification 018

Builds the Risk Analysis Report containing:

* The per-dimension risk results (7 dimensions).
* The complete risk list with severity classification.
* The recommendations (cause, impact, suggested fix, fix priority).
* The strengths identified during analysis.
* The findings produced during analysis.
* The cache information.
* The provenance (traceability to upstream data sources).
* The confidence score and level.
* The overall project readiness status (verdict).

The report builder assembles the final Risk Analysis Report from the
seven ``RiskDimensionResult`` objects, the collected findings, cache
info, provenance data, and the quality-gate outcome.  It derives the
overall readiness verdict from the analysis results and the
quality-gate outcome.

Verdict logic:

* ``VERDICT_NOT_READY`` -- the quality gate failed, or critical
  risks exist.  Generation is blocked.
* ``VERDICT_READY_WITH_RISKS`` -- the quality gate passed, but
  there are risks or warnings.  Generation may proceed with caution.
* ``VERDICT_READY`` -- the quality gate passed and there are no
  risks or warnings.  Generation may proceed.
"""

from __future__ import annotations

import logging
from typing import List

from .data_readers import (
    ProjectCapabilityData,
    ArchitectureDecisionData,
    TechnologySelectionData,
    RequirementNormalizationData,
    KnowledgeData,
)
from .report_data import (
    RiskDimensionResult,
    RiskFinding,
    RiskRecommendation,
    CacheInfo,
    RiskProvenance,
    RiskAnalysisReport,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    SEVERITY_LOW,
    CONFIDENCE_HIGH_THRESHOLD,
    CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_READY,
    VERDICT_READY_WITH_RISKS,
    VERDICT_NOT_READY,
    DIMENSION_ARCHITECTURE,
    DIMENSION_PERFORMANCE,
    DIMENSION_SCALABILITY,
    DIMENSION_SECURITY,
    DIMENSION_DEPENDENCY,
    DIMENSION_MAINTENANCE,
    DIMENSION_RESOURCE,
    ALL_DIMENSIONS,
)

_log = logging.getLogger("engine.risk_detection.report_builder")


class ReportBuilder:
    """Builds the Risk Analysis Report.

    Assembles the final report from the seven dimension results,
    collected findings, cache info, provenance data, and the
    quality-gate outcome.  Derives the overall readiness verdict,
    confidence, strengths, risks, and recommendations.
    """

    def __init__(self) -> None:
        pass

    def build(
        self,
        dimension_results: List[RiskDimensionResult],
        findings: List[RiskFinding],
        cache_info: CacheInfo,
        provenance: RiskProvenance,
        gate_passed: bool,
    ) -> RiskAnalysisReport:
        """Build the Risk Analysis Report.

        Args:
            dimension_results: The 7 per-dimension risk results.
            findings: The collected findings from all analyzers.
            cache_info: The cache information.
            provenance: The provenance data.
            gate_passed: Whether the quality gate passed.

        Returns:
            The complete :class:`RiskAnalysisReport`.
        """
        report = RiskAnalysisReport(
            dimension_results=dimension_results,
            findings=findings,
            cache_info=cache_info,
            provenance=provenance,
        )

        # Collect all risks from all dimension results into the
        # flat risk list.
        for dr in dimension_results:
            for risk in dr.risks:
                report.add_risk(risk)

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

    # --------------------------------------------------------------- #
    # Strengths derivation
    # --------------------------------------------------------------- #

    def _derive_strengths(
        self, report: RiskAnalysisReport,
    ) -> None:
        """Derive strengths from the dimension results.

        Args:
            report: The report being built (mutated).
        """
        # No critical risks is a strength.
        if not report.has_critical_risks and report.risk_count > 0:
            report.add_strength(
                "No critical-severity risks detected -- the "
                "project design does not have show-stopper risks."
            )

        # All dimensions analysed.
        if report.all_dimensions_analysed:
            report.add_strength(
                "All seven risk dimensions have been analysed -- "
                "the risk profile is comprehensive."
            )

        # Architecture dimension clean.
        arch = report.get_dimension(DIMENSION_ARCHITECTURE)
        if arch and arch.risk_count == 0:
            report.add_strength(
                "Architecture dimension is clean -- no "
                "partitioning, coupling, or extensibility risks."
            )

        # Security dimension clean.
        sec = report.get_dimension(DIMENSION_SECURITY)
        if sec and sec.risk_count == 0:
            report.add_strength(
                "Security dimension is clean -- no security "
                "vulnerabilities detected in the design."
            )

        # Dependency dimension clean.
        dep = report.get_dimension(DIMENSION_DEPENDENCY)
        if dep and dep.risk_count == 0:
            report.add_strength(
                "Dependency dimension is clean -- no dependency "
                "conflicts or failure points detected."
            )

        # Low overall risk score.
        if (
            report.risk_count > 0
            and report.overall_risk_score < 0.35
        ):
            report.add_strength(
                "Overall risk score is low -- the detected risks "
                "are predominantly low or medium severity."
            )

        # Data source availability.
        sources_available = sum([
            report.provenance.project_capability_available,
            report.provenance.architecture_decision_available,
            report.provenance.technology_selection_available,
            report.provenance.normalized_requirements_available,
            report.provenance.knowledge_base_available,
        ])
        if sources_available >= 4:
            report.add_strength(
                f"{sources_available} of 5 data sources were "
                f"available -- the risk analysis is well-grounded."
            )

    # --------------------------------------------------------------- #
    # Risks derivation
    # --------------------------------------------------------------- #

    def _derive_risks(
        self, report: RiskAnalysisReport,
    ) -> None:
        """Derive high-level risks from the dimension results.

        These are the summary-level risks that appear in the
        report's ``risks`` list (distinct from the individual
        ``RiskItem`` objects already collected).  They describe
        the overall risk posture.

        Args:
            report: The report being built (mutated).
        """
        # Critical risks.
        if report.has_critical_risks:
            _add_summary_risk(
                report,
                f"{report.critical_count} critical-severity "
                f"risk(s) detected -- generation is blocked until "
                f"addressed.",
            )

        # Architecture risks.
        arch = report.get_dimension(DIMENSION_ARCHITECTURE)
        if arch and arch.risk_count > 0:
            _add_summary_risk(
                report,
                f"Architecture dimension has {arch.risk_count} "
                f"risk(s) (score={arch.score:.2f}).",
            )

        # Performance risks.
        perf = report.get_dimension(DIMENSION_PERFORMANCE)
        if perf and perf.risk_count > 0:
            _add_summary_risk(
                report,
                f"Performance dimension has {perf.risk_count} "
                f"risk(s) (score={perf.score:.2f}).",
            )

        # Scalability risks.
        scal = report.get_dimension(DIMENSION_SCALABILITY)
        if scal and scal.risk_count > 0:
            _add_summary_risk(
                report,
                f"Scalability dimension has {scal.risk_count} "
                f"risk(s) (score={scal.score:.2f}).",
            )

        # Security risks.
        sec = report.get_dimension(DIMENSION_SECURITY)
        if sec and sec.risk_count > 0:
            _add_summary_risk(
                report,
                f"Security dimension has {sec.risk_count} "
                f"risk(s) (score={sec.score:.2f}).",
            )

        # Dependency risks.
        dep = report.get_dimension(DIMENSION_DEPENDENCY)
        if dep and dep.risk_count > 0:
            _add_summary_risk(
                report,
                f"Dependency dimension has {dep.risk_count} "
                f"risk(s) (score={dep.score:.2f}).",
            )

        # Maintenance risks.
        mnt = report.get_dimension(DIMENSION_MAINTENANCE)
        if mnt and mnt.risk_count > 0:
            _add_summary_risk(
                report,
                f"Maintenance dimension has {mnt.risk_count} "
                f"risk(s) (score={mnt.score:.2f}).",
            )

        # Resource risks.
        res = report.get_dimension(DIMENSION_RESOURCE)
        if res and res.risk_count > 0:
            _add_summary_risk(
                report,
                f"Resource dimension has {res.risk_count} "
                f"risk(s) (score={res.score:.2f}).",
            )

        # Data-source gaps.
        sources_available = sum([
            report.provenance.project_capability_available,
            report.provenance.architecture_decision_available,
            report.provenance.technology_selection_available,
            report.provenance.normalized_requirements_available,
            report.provenance.knowledge_base_available,
        ])
        if sources_available < 3:
            _add_summary_risk(
                report,
                f"Only {sources_available} of 5 data sources "
                f"were available -- risk analysis may be "
                f"incomplete.",
            )

    # --------------------------------------------------------------- #
    # Recommendations derivation
    # --------------------------------------------------------------- #

    def _derive_recommendations(
        self, report: RiskAnalysisReport,
    ) -> None:
        """Derive high-level recommendations from the dimension
        results.

        Each individual :class:`RiskItem` already carries its own
        cause/impact/suggested_fix.  These high-level
        recommendations group risks by dimension and provide
        actionable, prioritised guidance.

        Args:
            report: The report being built (mutated).
        """
        # Architecture recommendations.
        arch = report.get_dimension(DIMENSION_ARCHITECTURE)
        if arch and arch.risk_count > 0:
            related = [
                r.risk_id for r in arch.risks
            ]
            report.add_recommendation(RiskRecommendation(
                recommendation_id="rec_arch_overall",
                dimension=DIMENSION_ARCHITECTURE,
                priority=_priority_for_dimension(arch),
                title="Address architecture risks",
                description=(
                    "Resolve the detected architecture risks "
                    "(partitioning, coupling, extensibility, "
                    "circular dependencies) before generation."
                ),
                related_risks=related,
                expected_outcome=(
                    "Clean, extensible architecture with no "
                    "circular dependencies."
                ),
            ))

        # Performance recommendations.
        perf = report.get_dimension(DIMENSION_PERFORMANCE)
        if perf and perf.risk_count > 0:
            related = [
                r.risk_id for r in perf.risks
            ]
            report.add_recommendation(RiskRecommendation(
                recommendation_id="rec_perf_overall",
                dimension=DIMENSION_PERFORMANCE,
                priority=_priority_for_dimension(perf),
                title="Address performance risks",
                description=(
                    "Resolve the detected performance risks "
                    "(bottlenecks, memory, slow operations, "
                    "repetition) to ensure acceptable "
                    "performance."
                ),
                related_risks=related,
                expected_outcome=(
                    "Acceptable performance under expected load."
                ),
            ))

        # Scalability recommendations.
        scal = report.get_dimension(DIMENSION_SCALABILITY)
        if scal and scal.risk_count > 0:
            related = [
                r.risk_id for r in scal.risks
            ]
            report.add_recommendation(RiskRecommendation(
                recommendation_id="rec_scal_overall",
                dimension=DIMENSION_SCALABILITY,
                priority=_priority_for_dimension(scal),
                title="Address scalability risks",
                description=(
                    "Resolve the detected scalability risks to "
                    "ensure the system can grow without "
                    "degradation."
                ),
                related_risks=related,
                expected_outcome=(
                    "System scales horizontally with no "
                    "bottlenecks."
                ),
            ))

        # Security recommendations.
        sec = report.get_dimension(DIMENSION_SECURITY)
        if sec and sec.risk_count > 0:
            related = [
                r.risk_id for r in sec.risks
            ]
            report.add_recommendation(RiskRecommendation(
                recommendation_id="rec_sec_overall",
                dimension=DIMENSION_SECURITY,
                priority=_priority_for_dimension(sec),
                title="Address security risks",
                description=(
                    "Resolve the detected security "
                    "vulnerabilities before implementation to "
                    "prevent exploitable weaknesses."
                ),
                related_risks=related,
                expected_outcome=(
                    "Secure design with input validation, "
                    "authorization, encryption, and proper "
                    "secrets management."
                ),
            ))

        # Dependency recommendations.
        dep = report.get_dimension(DIMENSION_DEPENDENCY)
        if dep and dep.risk_count > 0:
            related = [
                r.risk_id for r in dep.risks
            ]
            report.add_recommendation(RiskRecommendation(
                recommendation_id="rec_dep_overall",
                dimension=DIMENSION_DEPENDENCY,
                priority=_priority_for_dimension(dep),
                title="Address dependency risks",
                description=(
                    "Resolve the detected dependency risks "
                    "(conflicts, deprecated libraries, "
                    "vulnerabilities, excessive dependencies, "
                    "single points of failure)."
                ),
                related_risks=related,
                expected_outcome=(
                    "Healthy, compatible dependency graph with "
                    "no single points of failure."
                ),
            ))

        # Maintenance recommendations.
        mnt = report.get_dimension(DIMENSION_MAINTENANCE)
        if mnt and mnt.risk_count > 0:
            related = [
                r.risk_id for r in mnt.risks
            ]
            report.add_recommendation(RiskRecommendation(
                recommendation_id="rec_mnt_overall",
                dimension=DIMENSION_MAINTENANCE,
                priority=_priority_for_dimension(mnt),
                title="Address maintenance risks",
                description=(
                    "Resolve the detected maintainability risks "
                    "to ensure the project remains "
                    "maintainable over time."
                ),
                related_risks=related,
                expected_outcome=(
                    "Maintainable project with tests, "
                    "documentation, and monitoring."
                ),
            ))

        # Resource recommendations.
        res = report.get_dimension(DIMENSION_RESOURCE)
        if res and res.risk_count > 0:
            related = [
                r.risk_id for r in res.risks
            ]
            report.add_recommendation(RiskRecommendation(
                recommendation_id="rec_res_overall",
                dimension=DIMENSION_RESOURCE,
                priority=_priority_for_dimension(res),
                title="Address resource risks",
                description=(
                    "Resolve the detected resource risks to "
                    "ensure the project does not exceed "
                    "available resources or budget."
                ),
                related_risks=related,
                expected_outcome=(
                    "Resource-efficient project within budget "
                    "constraints."
                ),
            ))

        # Critical-risk recommendation.
        if report.has_critical_risks:
            critical_ids = [
                r.risk_id for r in report.critical_risks()
            ]
            report.add_recommendation(RiskRecommendation(
                recommendation_id="rec_critical_immediate",
                dimension="all",
                priority="immediate",
                title="Address all critical risks immediately",
                description=(
                    f"{report.critical_count} critical risk(s) "
                    f"must be addressed before proceeding to "
                    f"the generation phase."
                ),
                related_risks=critical_ids,
                expected_outcome=(
                    "No critical risks remain; generation can "
                    "proceed."
                ),
            ))

    # --------------------------------------------------------------- #
    # Confidence calculation
    # --------------------------------------------------------------- #

    def _calculate_confidence(
        self,
        report: RiskAnalysisReport,
        provenance: RiskProvenance,
    ) -> float:
        """Calculate the overall confidence in the risk analysis.

        The confidence is a weighted combination of:

        * Data source availability (35%).
        * Analysis coverage -- number of dimensions analysed
          (30%).
        * Dependency health from the capability report (20%).
        * Scalability confidence from the capability report
          (15%).

        Args:
            report: The report being built.
            provenance: The provenance data.

        Returns:
            The confidence score (0.0-1.0).
        """
        # Data source availability (max 5 sources).
        sources_available = sum([
            provenance.project_capability_available,
            provenance.architecture_decision_available,
            provenance.technology_selection_available,
            provenance.normalized_requirements_available,
            provenance.knowledge_base_available,
        ])
        source_factor = sources_available / 5.0

        # Analysis coverage (max 7 dimensions).
        performed = len([
            d for d in report.dimension_results
            if d.dimension in ALL_DIMENSIONS
        ])
        analysis_factor = performed / 7.0

        # Dependency health from the capability report.
        # If the capability report was available, we use its
        # dependency health; otherwise, we default to a neutral
        # 0.5.
        # The dependency health is not stored directly in the
        # provenance, but we can infer it from the dependency
        # dimension result -- if it has no risks, health is
        # good.
        dep = report.get_dimension(DIMENSION_DEPENDENCY)
        if dep:
            # health = 1 - risk_score (lower score = healthier)
            health_factor = max(0.0, 1.0 - dep.score)
        else:
            health_factor = 0.5

        # Scalability confidence from the capability report.
        # If the scalability dimension has no risks, confidence
        # is high.
        scal = report.get_dimension(DIMENSION_SCALABILITY)
        if scal:
            scalability_factor = max(0.0, 1.0 - scal.score)
        else:
            scalability_factor = 0.5

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

    # --------------------------------------------------------------- #
    # Verdict determination
    # --------------------------------------------------------------- #

    def _determine_verdict(
        self,
        report: RiskAnalysisReport,
        gate_passed: bool,
    ) -> str:
        """Determine the overall project readiness verdict.

        The verdict is:

        * ``VERDICT_NOT_READY`` -- the quality gate failed, or
          critical risks exist.  Generation is blocked.
        * ``VERDICT_READY_WITH_RISKS`` -- the quality gate
          passed, but there are risks or warnings.  Generation
          may proceed with caution.
        * ``VERDICT_READY`` -- the quality gate passed and
          there are no risks or warnings.  Generation may
          proceed.

        Args:
            report: The report being built.
            gate_passed: Whether the quality gate passed.

        Returns:
            The verdict string.
        """
        # If the gate failed, the project is not ready.
        if not gate_passed:
            return VERDICT_NOT_READY

        # If there are critical risks, the project is not ready.
        if report.has_critical_risks:
            return VERDICT_NOT_READY

        # If there are any risks or warnings, ready with risks.
        if report.risks or report.warnings:
            return VERDICT_READY_WITH_RISKS

        # Otherwise, ready.
        return VERDICT_READY

    # --------------------------------------------------------------- #
    # Summary builder
    # --------------------------------------------------------------- #

    def _build_summary(
        self, report: RiskAnalysisReport,
    ) -> str:
        """Build a human-readable summary of the report.

        Args:
            report: The Risk Analysis Report.

        Returns:
            A summary string.
        """
        parts: List[str] = []

        # Verdict.
        parts.append(
            f"Risk Analysis Report: verdict={report.verdict}."
        )

        # Dimension count.
        parts.append(
            f"Dimensions analysed: {report.dimension_count} "
            f"of 7."
        )

        # Risk counts.
        parts.append(
            f"Risks: {report.risk_count} total "
            f"({report.critical_count} critical, "
            f"{report.high_count} high, "
            f"{report.medium_count} medium, "
            f"{report.low_count} low)."
        )

        # Overall risk score.
        parts.append(
            f"Overall risk score: {report.overall_risk_score:.2f}."
        )

        # Recommendations.
        parts.append(
            f"Recommendations: {report.recommendation_count}."
        )

        # Confidence.
        parts.append(
            f"Confidence: {report.confidence:.2f} "
            f"({report.confidence_level})."
        )

        # Readiness.
        if report.is_ready:
            parts.append("Project is ready for generation.")
        elif report.is_blocked:
            parts.append(
                "Project is BLOCKED -- critical risks must be "
                "addressed before generation."
            )
        else:
            parts.append(
                "Project is ready with risks -- proceed with "
                "caution."
            )

        return " ".join(parts)

    # --------------------------------------------------------------- #
    # Notes builder
    # --------------------------------------------------------------- #

    def _build_notes(
        self, report: RiskAnalysisReport,
    ) -> List[str]:
        """Build notes for the report.

        Args:
            report: The Risk Analysis Report.

        Returns:
            A list of note strings.
        """
        notes: List[str] = []

        provenance = report.provenance

        # Source availability.
        sources: List[str] = []
        if provenance.project_capability_available:
            sources.append("Project Capability Report")
        if provenance.architecture_decision_available:
            sources.append("Architecture Decision Report")
        if provenance.technology_selection_available:
            sources.append("Technology Selection Report")
        if provenance.normalized_requirements_available:
            sources.append("Normalized Requirement Model")
        if provenance.knowledge_base_available:
            sources.append("Knowledge Base")

        if sources:
            notes.append(
                f"Data sources used: {', '.join(sources)}."
            )
        else:
            notes.append(
                "No data sources were available.  Risk analysis "
                "is based on defaults."
            )

        # Cache status.
        if report.cache_hit:
            notes.append(
                "Report was served from cache."
            )

        # Dimension coverage.
        analysed = report.dimension_names()
        missing = [
            d for d in ALL_DIMENSIONS if d not in analysed
        ]
        if missing:
            notes.append(
                f"Missing dimensions: {', '.join(missing)}."
            )
        else:
            notes.append(
                "All 7 risk dimensions were analysed."
            )

        # Critical risks.
        if report.has_critical_risks:
            notes.append(
                f"{report.critical_count} critical risk(s) "
                f"detected -- generation is blocked."
            )

        # Capability verdict.
        if provenance.capability_verdict:
            notes.append(
                f"Upstream capability verdict: "
                f"{provenance.capability_verdict}."
            )

        return notes

    # --------------------------------------------------------------- #
    # Warnings collector
    # --------------------------------------------------------------- #

    def _collect_warnings(
        self, report: RiskAnalysisReport,
    ) -> List[str]:
        """Collect warning messages from the report.

        Warnings are derived from:

        * High and critical findings.
        * Critical risks.
        * Data source gaps.

        Args:
            report: The Risk Analysis Report.

        Returns:
            A list of warning strings.
        """
        warnings: List[str] = []

        # Warnings from findings (high and critical).
        for finding in report.findings:
            if finding.severity in (
                SEVERITY_HIGH, SEVERITY_CRITICAL,
            ):
                warnings.append(
                    f"[{finding.code}] {finding.message}"
                )

        # Warnings from critical risks.
        for risk in report.critical_risks():
            warnings.append(
                f"[{risk.risk_id}] {risk.title}"
            )

        # Data source gaps.
        sources_available = sum([
            report.provenance.project_capability_available,
            report.provenance.architecture_decision_available,
            report.provenance.technology_selection_available,
            report.provenance.normalized_requirements_available,
            report.provenance.knowledge_base_available,
        ])
        if sources_available < 3:
            warnings.append(
                f"Only {sources_available} of 5 data sources "
                f"were available -- analysis may be incomplete."
            )

        return warnings

    # --------------------------------------------------------------- #
    # Provenance builder
    # --------------------------------------------------------------- #

    def build_provenance(
        self,
        capability_data: ProjectCapabilityData,
        architecture_data: ArchitectureDecisionData,
        technology_data: TechnologySelectionData,
        requirement_data: RequirementNormalizationData,
        knowledge_data: KnowledgeData,
    ) -> RiskProvenance:
        """Build the provenance data from reader outputs.

        Args:
            capability_data: Project capability reader output.
            architecture_data: Architecture decision reader
                output.
            technology_data: Technology selection reader output.
            requirement_data: Requirement normalization reader
                output.
            knowledge_data: Knowledge base reader output.

        Returns:
            A :class:`RiskProvenance` instance.
        """
        provenance = RiskProvenance(
            project_capability_available=(
                capability_data.available
            ),
            architecture_decision_available=(
                architecture_data.available
            ),
            technology_selection_available=(
                technology_data.available
            ),
            normalized_requirements_available=(
                requirement_data.available
            ),
            knowledge_base_available=knowledge_data.available,
        )

        # Collect all sources used.
        sources: List[str] = []
        if capability_data.available:
            sources.append("project_capability_report")
        if architecture_data.available:
            sources.append("architecture_decision_report")
        if technology_data.available:
            sources.append("technology_selection_report")
        if requirement_data.available:
            sources.append("requirement_normalization_report")
        if knowledge_data.available:
            sources.append("knowledge_base")
        provenance.all_sources_used = sources

        # Extract the capability verdict.
        provenance.capability_verdict = capability_data.verdict

        # Extract counts.
        provenance.decision_count = (
            architecture_data.decision_count
        )
        provenance.selection_count = (
            technology_data.selection_count
        )
        provenance.requirement_count = (
            requirement_data.requirement_count
        )

        return provenance


# --------------------------------------------------------------- #
# Module-level helpers
# --------------------------------------------------------------- #

def _add_summary_risk(
    report: RiskAnalysisReport, message: str,
) -> None:
    """Add a summary-level finding to the report's warnings.

    The summary-level risks are recorded as findings (not as
    individual :class:`RiskItem` objects, which come from the
    analyzers).  This keeps the report's ``risks`` list clean
    (containing only the detailed :class:`RiskItem` objects) while
    still surfacing the high-level risk posture in the findings and
    warnings.
    """
    report.findings.append(RiskFinding(
        severity=SEVERITY_MEDIUM,
        code="summary_risk",
        message=message,
        affected="overall",
        category="summary",
    ))


def _priority_for_dimension(
    dim_result: RiskDimensionResult,
) -> str:
    """Determine the recommendation priority for a dimension.

    Args:
        dim_result: The dimension result.

    Returns:
        The priority string (immediate/high/medium/low).
    """
    if dim_result.critical_count > 0:
        return "immediate"
    if dim_result.high_count > 0:
        return "high"
    if dim_result.medium_count > 0:
        return "medium"
    return "low"


__all__ = ["ReportBuilder"]
