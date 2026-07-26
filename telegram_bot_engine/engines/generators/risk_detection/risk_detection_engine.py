"""
RiskDetectionEngine -- Specification 018

Main engine class that orchestrates the Risk Detection analysis.

This engine:

1. Reads all required data sources (Project Capability Report,
   Architecture Decision Report, Technology Selection Report,
   Normalized Requirement Model, Knowledge Base).
2. Performs Architecture Risk Analysis.
3. Performs Performance Risk Analysis.
4. Performs Scalability Risk Analysis.
5. Performs Security Risk Analysis.
6. Performs Dependency Risk Analysis.
7. Performs Maintenance Risk Analysis.
8. Performs Resource Risk Analysis.
9. Validates the report through the Quality Gate (blocks
   generation if a Critical risk exists).
10. Builds the final Risk Analysis Report.

The engine does NOT write code, create files, or start the build
process.  Its sole function is detecting all potential risks
before project generation begins and producing the *Risk Analysis
Report* -- the official reference for all downstream engines that
need risk information.  The report contains the risk list,
severity scores, recommendations, and the final project readiness
status.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    ProjectCapabilityData,
    ArchitectureDecisionData,
    TechnologySelectionData,
    RequirementNormalizationData,
    KnowledgeData,
    ProjectCapabilityReader,
    ArchitectureDecisionReader,
    TechnologySelectionReader,
    RequirementNormalizationReader,
    KnowledgeReader,
)
from .report_data import (
    RiskAnalysisReport,
    RiskFinding,
    RiskDimensionResult,
    CacheInfo,
    RiskProvenance,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    SEVERITY_LOW,
    DIMENSION_ARCHITECTURE,
    DIMENSION_PERFORMANCE,
    DIMENSION_SCALABILITY,
    DIMENSION_SECURITY,
    DIMENSION_DEPENDENCY,
    DIMENSION_MAINTENANCE,
    DIMENSION_RESOURCE,
)
from .architecture_risk_analyzer import ArchitectureRiskAnalyzer
from .performance_risk_analyzer import PerformanceRiskAnalyzer
from .scalability_risk_analyzer import ScalabilityRiskAnalyzer
from .security_risk_analyzer import SecurityRiskAnalyzer
from .dependency_risk_analyzer import DependencyRiskAnalyzer
from .maintenance_risk_analyzer import MaintenanceRiskAnalyzer
from .resource_risk_analyzer import ResourceRiskAnalyzer
from .quality_gate import QualityGate
from .report_builder import ReportBuilder
from .cache_manager import CacheManager

_log = logging.getLogger("engine.risk_detection")


class RiskDetectionEngine(BaseEngine):
    """The Risk Detection Engine.

    Detects all potential risks before project generation begins.
    Reads five data sources, performs seven risk analyses, validates
    through the quality gate, and produces the Risk Analysis Report.

    The engine:

    1. Reads data from the context (5 sources).
    2. Performs 7 risk-dimension analyses.
    3. Validates the report through the quality gate.
    4. Builds the final Risk Analysis Report.
    5. Stores the report in the context for downstream engines.

    If a Critical risk exists, the quality gate blocks the
    generation pipeline -- the report's verdict becomes
    ``not_ready`` and downstream engines must not proceed with
    generation until the critical risks are addressed.
    """

    engine_name = "risk_detection"
    engine_version = "1.0.0"
    engine_description = (
        "Detects all potential risks before project generation "
        "begins.  Reads five data sources, performs seven risk "
        "analyses (architecture, performance, scalability, "
        "security, dependency, maintenance, resource), classifies "
        "each risk by severity, produces recommendations, and "
        "determines the project's readiness for the generation "
        "phase.  Blocks generation if a Critical risk exists."
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(
            name=self.engine_name,
            version=self.engine_version,
            description=self.engine_description,
        )
        self._architecture_analyzer = ArchitectureRiskAnalyzer()
        self._performance_analyzer = PerformanceRiskAnalyzer()
        self._scalability_analyzer = ScalabilityRiskAnalyzer()
        self._security_analyzer = SecurityRiskAnalyzer()
        self._dependency_analyzer = DependencyRiskAnalyzer()
        self._maintenance_analyzer = MaintenanceRiskAnalyzer()
        self._resource_analyzer = ResourceRiskAnalyzer()
        self._quality_gate = QualityGate()
        self._report_builder = ReportBuilder()
        self._cache_manager = CacheManager()

    def execute(self, context: GenerationContext) -> StageResult:
        """Execute the Risk Detection Engine.

        Args:
            context: The generation context containing all project
                data.

        Returns:
            A :class:`StageResult` describing the outcome.
        """
        _log.info("Risk Detection Engine starting...")

        # Step 1: Read all data sources.
        try:
            (
                cap_data,
                arch_data,
                tech_data,
                req_data,
                kb_data,
            ) = self._read_data_sources(context)
        except Exception as exc:
            return self.failed(
                errors=[f"Failed to read data sources: {exc}"],
            )

        _log.info(
            "Data sources loaded",
            {
                "capability": cap_data.available,
                "architecture": arch_data.available,
                "technology": tech_data.available,
                "requirements": req_data.available,
                "knowledge": kb_data.available,
            },
        )

        # Step 2: Check cache.
        cache_info = self._cache_manager.get_cache_info(
            cap_data, arch_data, tech_data, req_data, kb_data
        )
        cached_report = self._cache_manager.get_cached(cache_info)

        if cached_report is not None:
            _log.info("Using cached Risk Analysis Report")
            context.set("risk_analysis_report", cached_report)
            context.metadata["risk_analysis_report"] = cached_report

            return self.ok(
                outputs={
                    "report": cached_report,
                    "dimension_count": (
                        cached_report.dimension_count
                    ),
                    "risk_count": cached_report.risk_count,
                    "critical_count": cached_report.critical_count,
                    "ready": cached_report.ready,
                    "verdict": cached_report.verdict,
                    "confidence": cached_report.confidence,
                    "cache_hit": True,
                },
                metadata={
                    "cache_hit": True,
                    "dimension_count": (
                        cached_report.dimension_count
                    ),
                    "risk_count": cached_report.risk_count,
                    "ready": cached_report.ready,
                    "verdict": cached_report.verdict,
                },
            )

        # Step 3: Run all 7 risk analyses.
        dimension_results = self._run_analyses(
            cap_data, arch_data, tech_data, req_data, kb_data
        )

        _log.info(
            "Risk analyses complete",
            {
                "dimension_count": len(dimension_results),
                "total_risks": sum(
                    dr.risk_count for dr in dimension_results
                ),
            },
        )

        # Step 4: Build provenance.
        provenance = self._report_builder.build_provenance(
            cap_data, arch_data, tech_data, req_data, kb_data
        )

        # Step 5: Validate through quality gate.
        # Build a preliminary report for the quality gate to
        # inspect.  The quality gate needs the dimension results
        # and the collected findings to check the rules.
        preliminary_findings = self._collect_all_findings(
            dimension_results
        )

        preliminary_report = RiskAnalysisReport(
            dimension_results=dimension_results,
            findings=list(preliminary_findings),
            cache_info=cache_info,
            provenance=provenance,
        )
        # Populate the flat risk list for the gate to inspect.
        for dr in dimension_results:
            for risk in dr.risks:
                preliminary_report.add_risk(risk)

        gate_findings, gate_passed = self._quality_gate.validate(
            preliminary_report
        )

        if not gate_passed:
            _log.warning(
                "Quality gate: critical risks detected or "
                "rules failed.  Generation will be blocked."
            )
        else:
            _log.info(
                "Quality gate passed -- no critical risks."
            )

        # Step 6: Collect all findings.
        all_findings: List[RiskFinding] = list(gate_findings)
        all_findings.extend(preliminary_findings)

        # Step 7: Build the final report.
        try:
            report = self._report_builder.build(
                dimension_results=dimension_results,
                findings=all_findings,
                cache_info=cache_info,
                provenance=provenance,
                gate_passed=gate_passed,
            )
        except Exception as exc:
            return self.failed(
                errors=[f"Report building failed: {exc}"],
            )

        _log.info(
            "Risk Analysis Report built",
            {
                "dimension_count": report.dimension_count,
                "risk_count": report.risk_count,
                "critical_count": report.critical_count,
                "high_count": report.high_count,
                "verdict": report.verdict,
                "confidence": report.confidence,
                "confidence_level": report.confidence_level,
                "ready": report.ready,
                "is_blocked": report.is_blocked,
            },
        )

        # Step 8: Cache the report.
        self._cache_manager.store(cache_info, report)

        # Store in context for downstream stages.
        context.set("risk_analysis_report", report)
        context.metadata["risk_analysis_report"] = report

        # Build outputs.
        outputs: Dict[str, Any] = {
            "report": report,
            "dimension_count": report.dimension_count,
            "risk_count": report.risk_count,
            "critical_count": report.critical_count,
            "high_count": report.high_count,
            "medium_count": report.medium_count,
            "low_count": report.low_count,
            "ready": report.ready,
            "verdict": report.verdict,
            "confidence": report.confidence,
            "confidence_level": report.confidence_level,
            "cache_hit": False,
        }

        # Collect warning and error messages.
        warnings = [
            f.message for f in all_findings
            if f.severity in (SEVERITY_MEDIUM, SEVERITY_HIGH)
        ]
        critical_messages = [
            f.message for f in all_findings
            if f.severity == SEVERITY_CRITICAL
        ]

        # If the report is blocked, critical messages become
        # warnings in the StageResult so the pipeline can continue
        # and downstream engines can inspect the report.
        all_warnings = warnings + (
            critical_messages if report.is_blocked else []
        )

        return StageResult(
            stage_name=self.name,
            success=True,
            outputs=outputs,
            metadata={
                "cache_hit": False,
                "dimension_count": report.dimension_count,
                "risk_count": report.risk_count,
                "critical_count": report.critical_count,
                "high_count": report.high_count,
                "medium_count": report.medium_count,
                "low_count": report.low_count,
                "ready": report.ready,
                "verdict": report.verdict,
                "confidence": report.confidence,
                "confidence_level": report.confidence_level,
                "is_blocked": report.is_blocked,
                "overall_risk_score": report.overall_risk_score,
            },
            warnings=all_warnings,
        )

    # --------------------------------------------------------------- #
    # Data reading
    # --------------------------------------------------------------- #

    def _read_data_sources(
        self, context: GenerationContext
    ) -> tuple[
        ProjectCapabilityData,
        ArchitectureDecisionData,
        TechnologySelectionData,
        RequirementNormalizationData,
        KnowledgeData,
    ]:
        """Read all required data sources from the context.

        Args:
            context: The generation context.

        Returns:
            A tuple of the five data reader outputs.
        """
        cap_reader = ProjectCapabilityReader()
        arch_reader = ArchitectureDecisionReader()
        tech_reader = TechnologySelectionReader()
        req_reader = RequirementNormalizationReader()
        kb_reader = KnowledgeReader()

        cap_data = cap_reader.read(context)
        arch_data = arch_reader.read(context)
        tech_data = tech_reader.read(context)
        req_data = req_reader.read(context)
        kb_data = kb_reader.read(context)

        return cap_data, arch_data, tech_data, req_data, kb_data

    # --------------------------------------------------------------- #
    # Analysis orchestration
    # --------------------------------------------------------------- #

    def _run_analyses(
        self,
        cap_data: ProjectCapabilityData,
        arch_data: ArchitectureDecisionData,
        tech_data: TechnologySelectionData,
        req_data: RequirementNormalizationData,
        kb_data: KnowledgeData,
    ) -> List[RiskDimensionResult]:
        """Run all seven risk analyses and collect results.

        Each analyzer is run with a try/except guard.  If an
        analyzer raises, it is retried once.  If the retry also
        fails, a minimal (empty) dimension result is produced so
        that the engine can still complete and the quality gate
        can report the missing dimension.

        Args:
            cap_data: Project capability data.
            arch_data: Architecture decision data.
            tech_data: Technology selection data.
            req_data: Requirement normalization data.
            kb_data: Knowledge base data.

        Returns:
            A list of 7 :class:`RiskDimensionResult` objects.
        """
        results: List[RiskDimensionResult] = []

        # Map dimension constants to (analyzer, dimension_name)
        # for the fallback empty result.
        analyzer_specs = [
            (self._architecture_analyzer, DIMENSION_ARCHITECTURE),
            (self._performance_analyzer, DIMENSION_PERFORMANCE),
            (self._scalability_analyzer, DIMENSION_SCALABILITY),
            (self._security_analyzer, DIMENSION_SECURITY),
            (self._dependency_analyzer, DIMENSION_DEPENDENCY),
            (self._maintenance_analyzer, DIMENSION_MAINTENANCE),
            (self._resource_analyzer, DIMENSION_RESOURCE),
        ]

        for analyzer, dim_name in analyzer_specs:
            result = self._run_single_analysis(
                analyzer, dim_name,
                cap_data, arch_data, tech_data, req_data, kb_data,
            )
            results.append(result)

        return results

    def _run_single_analysis(
        self,
        analyzer: Any,
        dim_name: str,
        cap_data: ProjectCapabilityData,
        arch_data: ArchitectureDecisionData,
        tech_data: TechnologySelectionData,
        req_data: RequirementNormalizationData,
        kb_data: KnowledgeData,
    ) -> RiskDimensionResult:
        """Run a single analyzer with retry and fallback.

        Args:
            analyzer: The analyzer instance.
            dim_name: The dimension name (for the fallback).
            cap_data: Project capability data.
            arch_data: Architecture decision data.
            tech_data: Technology selection data.
            req_data: Requirement normalization data.
            kb_data: Knowledge base data.

        Returns:
            A :class:`RiskDimensionResult`.
        """
        try:
            return analyzer.analyze(
                cap_data, arch_data, tech_data, req_data, kb_data
            )
        except Exception as exc:
            _log.error(
                "%s analysis failed (attempt 1): %s",
                dim_name, exc,
            )
            # Retry once.
            try:
                return analyzer.analyze(
                    cap_data, arch_data, tech_data, req_data,
                    kb_data,
                )
            except Exception as exc2:
                _log.error(
                    "%s analysis failed (attempt 2): %s",
                    dim_name, exc2,
                )
                # Fallback: empty dimension result.
                return RiskDimensionResult(
                    dimension=dim_name,
                    risk_count=0,
                    critical_count=0,
                    high_count=0,
                    medium_count=0,
                    low_count=0,
                    score=0.0,
                    summary=(
                        f"{dim_name} risk analysis failed -- "
                        f"no results available."
                    ),
                    details=[
                        f"Analysis error: {exc2}",
                    ],
                    risks=[],
                )

    # --------------------------------------------------------------- #
    # Findings collection
    # --------------------------------------------------------------- #

    def _collect_all_findings(
        self,
        dimension_results: List[RiskDimensionResult],
    ) -> List[RiskFinding]:
        """Collect all findings from all analyzers.

        Each analyzer stores its findings on ``self.findings``
        after ``analyze()`` is called.  This method collects them
        from the analyzer instances.

        Args:
            dimension_results: The dimension results (used to
                verify which analyzers ran).

        Returns:
            A list of all :class:`RiskFinding` objects.
        """
        all_findings: List[RiskFinding] = []
        analyzers = [
            self._architecture_analyzer,
            self._performance_analyzer,
            self._scalability_analyzer,
            self._security_analyzer,
            self._dependency_analyzer,
            self._maintenance_analyzer,
            self._resource_analyzer,
        ]
        for analyzer in analyzers:
            findings = getattr(analyzer, "findings", [])
            all_findings.extend(findings)
        return all_findings


__all__ = ["RiskDetectionEngine"]
