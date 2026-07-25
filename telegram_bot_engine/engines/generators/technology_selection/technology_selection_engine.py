"""
TechnologySelectionEngine — Specification 016

Main engine class that orchestrates the Technology Selection process.

This engine:
1. Reads all required data sources (Architecture Decision Report,
   Normalized Requirement Model, Project Intelligence Graph,
   Knowledge Base, Quality Rules).
2. Analyzes candidates against Quality, Stability, Compatibility,
   and Scalability.
3. Selects all ten technology categories (Programming Language,
   Framework, Database, ORM, Cache, Queue, Storage, Logging,
   Testing, Deployment).
4. Validates selections through the Quality Gate.
5. Builds the final Technology Selection Report.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    ArchitectureDecisionData,
    RequirementNormalizationData,
    IntelligenceGraphData,
    KnowledgeData,
    QualityRulesData,
    ArchitectureDecisionReader,
    RequirementNormalizationReader,
    IntelligenceGraphReader,
    KnowledgeReader,
    QualityRulesReader,
)
from .report_data import (
    AnalysisResult,
    TechnologySelection,
    TechnologyFinding,
    TechnologyProvenance,
    TechnologySelectionReport,
    CacheInfo,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
)
from .compatibility_analyzer import CompatibilityAnalyzer
from .performance_analyzer import PerformanceAnalyzer
from .security_analyzer import SecurityAnalyzer
from .quality_gate import QualityGate
from .report_builder import ReportBuilder
from .technology_selector import TechnologySelector
from .cache_manager import CacheManager

_log = logging.getLogger("engine.technology_selection")


class TechnologySelectionEngine(BaseEngine):
    """The Technology Selection Engine.

    Selects all ten technology categories for the project based on
    the architecture decision, requirements, intelligence graph,
    knowledge base, and quality rules.

    The engine:
    1. Reads data from the context.
    2. Analyzes candidates for compatibility, performance, security,
       and quality.
    3. Selects technologies for all ten categories.
    4. Validates selections through the quality gate.
    5. Builds the final report.
    """

    engine_name = "technology_selection"
    engine_version = "1.0.0"
    engine_description = (
        "Selects the best technologies for the project based on "
        "architecture decisions, requirements, and quality rules."
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(
            name=self.engine_name,
            version=self.engine_version,
            description=self.engine_description,
        )
        self._compatibility_analyzer = CompatibilityAnalyzer()
        self._performance_analyzer = PerformanceAnalyzer()
        self._security_analyzer = SecurityAnalyzer()
        self._quality_gate = QualityGate()
        self._report_builder = ReportBuilder()
        self._technology_selector = TechnologySelector()
        self._cache_manager = CacheManager()

    def execute(self, context: GenerationContext) -> StageResult:
        """Execute the Technology Selection Engine.

        Args:
            context: The generation context containing all project data.

        Returns:
            A :class:`StageResult` describing the outcome.
        """
        _log.info("Technology Selection Engine starting...")

        # Step 1: Read all data sources.
        try:
            (
                arch_data,
                req_data,
                graph_data,
                kb_data,
                qr_data,
            ) = self._read_data_sources(context)
        except Exception as exc:
            return self.failed(
                errors=[f"Failed to read data sources: {exc}"],
            )

        _log.info(
            "Data sources loaded",
            {
                "architecture": arch_data.available,
                "requirements": req_data.available,
                "graph": graph_data.available,
                "knowledge": kb_data.available,
                "quality": qr_data.available,
            },
        )

        # Step 2: Check cache.
        cache_info = self._cache_manager.get_cache_info(
            arch_data, req_data, graph_data, kb_data, qr_data
        )
        cached_report = self._cache_manager.get_cached(cache_info)

        if cached_report is not None:
            _log.info("Using cached Technology Selection Report")
            context.set("technology_selection_report", cached_report)
            context.metadata["technology_selection_report"] = cached_report

            return self.ok(
                outputs={
                    "report": cached_report,
                    "selection_count": cached_report.selection_count,
                    "ready": cached_report.ready,
                    "confidence": cached_report.confidence,
                    "cache_hit": True,
                },
                metadata={
                    "cache_hit": True,
                    "selection_count": cached_report.selection_count,
                    "ready": cached_report.ready,
                },
            )

        # Step 3: Select technologies.
        try:
            selections = self._technology_selector.select(
                arch_data, req_data, graph_data, kb_data, qr_data
            )
        except Exception as exc:
            return self.failed(
                errors=[f"Technology selection failed: {exc}"],
            )

        _log.info(
            "Technology selections made",
            {"count": len(selections)},
        )

        # Step 4: Analyze candidates.
        analyses = self._analyze(
            arch_data, req_data, graph_data, kb_data
        )

        _log.info(
            "Analysis complete",
            {"dimension_count": len(analyses)},
        )

        # Step 5: Validate through quality gate.
        provenance = self._report_builder.build_provenance(
            arch_data, req_data, graph_data, kb_data, qr_data
        )

        preliminary_report = TechnologySelectionReport(
            analyses=analyses,
            selections=selections,
            findings=[],
            cache_info=cache_info,
            provenance=provenance,
        )

        gate_findings, gate_passed = self._quality_gate.validate(
            preliminary_report
        )
        if not gate_passed:
            _log.warning(
                "Quality gate: some selections failed validation"
            )

        # Step 6: Collect all findings.
        all_findings = list(gate_findings)
        all_findings.extend(self._technology_selector.findings)
        all_findings.extend(self._compatibility_analyzer.findings)
        all_findings.extend(self._performance_analyzer.findings)
        all_findings.extend(self._security_analyzer.findings)

        # Step 7: Build the final report.
        try:
            report = self._report_builder.build(
                analyses=analyses,
                selections=selections,
                findings=all_findings,
                cache_info=cache_info,
                provenance=provenance,
            )
        except Exception as exc:
            return self.failed(
                errors=[f"Report building failed: {exc}"],
            )

        _log.info(
            "Technology Selection Report built",
            {
                "selection_count": report.selection_count,
                "finding_count": report.finding_count,
                "confidence": report.confidence,
                "confidence_level": report.confidence_level,
                "ready": report.ready,
            },
        )

        # Step 8: Cache the report.
        self._cache_manager.store(cache_info, report)

        # Store in context for downstream stages.
        context.set("technology_selection_report", report)
        context.metadata["technology_selection_report"] = report

        # Build outputs.
        outputs: Dict[str, Any] = {
            "report": report,
            "selection_count": report.selection_count,
            "ready": report.ready,
            "confidence": report.confidence,
            "confidence_level": report.confidence_level,
            "cache_hit": False,
        }

        # Collect warning messages.
        warnings = [f.message for f in all_findings
                    if f.severity == SEVERITY_WARNING]
        errors = [f.message for f in all_findings
                  if f.severity == SEVERITY_ERROR]

        # Collect warning messages.
        all_warnings = warnings + (errors if not report.ready else [])

        return StageResult(
            stage_name=self.name,
            success=True,
            outputs=outputs,
            metadata={
                "cache_hit": False,
                "selection_count": report.selection_count,
                "finding_count": report.finding_count,
                "error_count": report.error_count,
                "warning_count": report.warning_count,
                "ready": report.ready,
                "confidence": report.confidence,
                "confidence_level": report.confidence_level,
            },
            warnings=all_warnings,
        )

    # ----------------------------------------------------------------- #
    # Data reading
    # ----------------------------------------------------------------- #

    def _read_data_sources(
        self, context: GenerationContext
    ) -> tuple[
        ArchitectureDecisionData,
        RequirementNormalizationData,
        IntelligenceGraphData,
        KnowledgeData,
        QualityRulesData,
    ]:
        """Read all required data sources from the context.

        Args:
            context: The generation context.

        Returns:
            A tuple of the five data reader outputs.
        """
        arch_reader = ArchitectureDecisionReader()
        req_reader = RequirementNormalizationReader()
        graph_reader = IntelligenceGraphReader()
        kb_reader = KnowledgeReader()
        qr_reader = QualityRulesReader()

        arch_data = arch_reader.read(context)
        req_data = req_reader.read(context)
        graph_data = graph_reader.read(context)
        kb_data = kb_reader.read(context)
        qr_data = qr_reader.read(context)

        return arch_data, req_data, graph_data, kb_data, qr_data

    # ----------------------------------------------------------------- #
    # Analysis
    # ----------------------------------------------------------------- #

    def _analyze(
        self,
        arch_data: ArchitectureDecisionData,
        req_data: RequirementNormalizationData,
        graph_data: IntelligenceGraphData,
        kb_data: KnowledgeData,
    ) -> List[AnalysisResult]:
        """Run all analyses.

        Args:
            arch_data: Architecture decision data.
            req_data: Requirement normalization data.
            graph_data: Intelligence graph data.
            kb_data: Knowledge base data.

        Returns:
            A list of AnalysisResult objects, one per dimension.
        """
        analyses: List[AnalysisResult] = []

        # Compatibility analysis.
        try:
            compat_result = self._compatibility_analyzer.analyze(
                arch_data, req_data, graph_data, kb_data
            )
            analyses.append(compat_result)
        except Exception as e:
            _log.error(
                "Compatibility analysis failed",
                exc_info=e,
            )

        # Performance analysis.
        try:
            perf_result = self._performance_analyzer.analyze(
                arch_data, req_data, graph_data, kb_data
            )
            analyses.append(perf_result)
        except Exception as e:
            _log.error(
                "Performance analysis failed",
                exc_info=e,
            )

        # Security analysis.
        try:
            sec_result = self._security_analyzer.analyze(
                arch_data, req_data, graph_data, kb_data
            )
            analyses.append(sec_result)
        except Exception as e:
            _log.error(
                "Security analysis failed",
                exc_info=e,
            )

        return analyses


__all__ = ["TechnologySelectionEngine"]
