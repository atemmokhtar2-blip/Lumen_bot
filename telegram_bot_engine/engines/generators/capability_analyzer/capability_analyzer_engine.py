"""
ProjectCapabilityAnalyzerEngine — Specification 017

Main engine class that orchestrates the Project Capability Analysis.

This engine:
1. Reads all required data sources (Architecture Decision Report,
   Technology Selection Report, Normalized Requirement Model,
   Project Intelligence Graph, Knowledge Base).
2. Performs Complexity Analysis.
3. Performs Resource Estimation.
4. Performs Scalability Analysis.
5. Performs Architecture Stress Analysis.
6. Performs Dependency Analysis.
7. Validates the architecture through the Quality Gate
   (blocks generation if the architecture can't meet
   performance/scalability/quality requirements).
8. Builds the final Project Capability Report.

The engine does NOT write code, create files, or build the project.
Its sole function is analyzing the project's full capability and
producing the *Project Capability Report* — the official
reference for all downstream engines that need capability
information.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    ArchitectureDecisionData,
    TechnologySelectionData,
    RequirementNormalizationData,
    IntelligenceGraphData,
    KnowledgeData,
    ArchitectureDecisionReader,
    TechnologySelectionReader,
    RequirementNormalizationReader,
    IntelligenceGraphReader,
    KnowledgeReader,
)
from .report_data import (
    AnalysisResult,
    CapabilityFinding,
    CacheInfo,
    CapabilityProvenance,
    ProjectCapabilityReport,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    DIMENSION_COMPLEXITY,
    DIMENSION_RESOURCES,
    DIMENSION_SCALABILITY,
    DIMENSION_STRESS,
    DIMENSION_DEPENDENCIES,
)
from .complexity_analyzer import ComplexityAnalyzer
from .resource_estimator import ResourceEstimator
from .scalability_analyzer import ScalabilityAnalyzer
from .stress_analyzer import StressAnalyzer
from .dependency_analyzer import DependencyAnalyzer
from .quality_gate import QualityGate
from .report_builder import ReportBuilder
from .cache_manager import CacheManager

_log = logging.getLogger("engine.capability_analyzer")


class ProjectCapabilityAnalyzerEngine(BaseEngine):
    """The Project Capability Analyzer Engine.

    Analyzes the project's full capability before building starts.
    Reads five data sources, performs five analyses, validates
    through the quality gate, and produces the Project Capability
    Report.

    The engine:
    1. Reads data from the context.
    2. Performs complexity, resource, scalability, stress, and
       dependency analyses.
    3. Validates the architecture through the quality gate.
    4. Builds the final report.
    5. Stores the report in the context for downstream engines.
    """

    engine_name = "capability_analyzer"
    engine_version = "1.0.0"
    engine_description = (
        "Analyzes the project's full capability (complexity, "
        "resources, scalability, stress, dependencies) before "
        "building starts.  Produces the Project Capability Report "
        "and blocks generation if the architecture cannot meet "
        "performance, scalability, or quality requirements."
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(
            name=self.engine_name,
            version=self.engine_version,
            description=self.engine_description,
        )
        self._complexity_analyzer = ComplexityAnalyzer()
        self._resource_estimator = ResourceEstimator()
        self._scalability_analyzer = ScalabilityAnalyzer()
        self._stress_analyzer = StressAnalyzer()
        self._dependency_analyzer = DependencyAnalyzer()
        self._quality_gate = QualityGate()
        self._report_builder = ReportBuilder()
        self._cache_manager = CacheManager()

    def execute(self, context: GenerationContext) -> StageResult:
        """Execute the Project Capability Analyzer Engine.

        Args:
            context: The generation context containing all project
                data.

        Returns:
            A :class:`StageResult` describing the outcome.
        """
        _log.info("Project Capability Analyzer Engine starting...")

        # Step 1: Read all data sources.
        try:
            (
                arch_data,
                tech_data,
                req_data,
                graph_data,
                kb_data,
            ) = self._read_data_sources(context)
        except Exception as exc:
            return self.failed(
                errors=[f"Failed to read data sources: {exc}"],
            )

        _log.info(
            "Data sources loaded",
            {
                "architecture": arch_data.available,
                "technology": tech_data.available,
                "requirements": req_data.available,
                "graph": graph_data.available,
                "knowledge": kb_data.available,
            },
        )

        # Step 2: Check cache.
        cache_info = self._cache_manager.get_cache_info(
            arch_data, tech_data, req_data, graph_data, kb_data
        )
        cached_report = self._cache_manager.get_cached(cache_info)

        if cached_report is not None:
            _log.info(
                "Using cached Project Capability Report"
            )
            context.set(
                "project_capability_report", cached_report
            )
            context.metadata[
                "project_capability_report"
            ] = cached_report

            return self.ok(
                outputs={
                    "report": cached_report,
                    "analysis_count": (
                        cached_report.analysis_count
                    ),
                    "ready": cached_report.ready,
                    "verdict": cached_report.verdict,
                    "confidence": cached_report.confidence,
                    "cache_hit": True,
                },
                metadata={
                    "cache_hit": True,
                    "analysis_count": (
                        cached_report.analysis_count
                    ),
                    "ready": cached_report.ready,
                    "verdict": cached_report.verdict,
                },
            )

        # Step 3: Run all analyses.
        (
            complexity,
            resources,
            scalability,
            stress,
            dependencies,
            analyses,
        ) = self._run_analyses(
            arch_data, tech_data, req_data, graph_data, kb_data
        )

        _log.info(
            "Analyses complete",
            {
                "dimension_count": len(analyses),
                "complexity_level": complexity.complexity_level,
                "scalability_score": scalability.score,
                "stress_score": stress.score,
                "dependency_score": dependencies.score,
            },
        )

        # Step 4: Build provenance.
        provenance = self._report_builder.build_provenance(
            arch_data, tech_data, req_data, graph_data, kb_data
        )

        # Step 5: Validate through quality gate.
        preliminary_report = ProjectCapabilityReport(
            complexity=complexity,
            resources=resources,
            scalability=scalability,
            stress=stress,
            dependencies=dependencies,
            analyses=analyses,
            findings=[],
            cache_info=cache_info,
            provenance=provenance,
        )

        gate_findings, gate_passed = self._quality_gate.validate(
            preliminary_report
        )
        if not gate_passed:
            _log.warning(
                "Quality gate: architecture cannot meet "
                "performance/scalability/quality requirements. "
                "Generation will be blocked."
            )
        else:
            _log.info(
                "Quality gate passed — architecture is capable."
            )

        # Step 6: Collect all findings.
        all_findings: List[CapabilityFinding] = list(gate_findings)
        all_findings.extend(self._complexity_analyzer.findings)
        all_findings.extend(self._resource_estimator.findings)
        all_findings.extend(self._scalability_analyzer.findings)
        all_findings.extend(self._stress_analyzer.findings)
        all_findings.extend(self._dependency_analyzer.findings)

        # Step 7: Build the final report.
        try:
            report = self._report_builder.build(
                complexity=complexity,
                resources=resources,
                scalability=scalability,
                stress=stress,
                dependencies=dependencies,
                analyses=analyses,
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
            "Project Capability Report built",
            {
                "analysis_count": report.analysis_count,
                "finding_count": report.finding_count,
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
        context.set("project_capability_report", report)
        context.metadata["project_capability_report"] = report

        # Build outputs.
        outputs: Dict[str, Any] = {
            "report": report,
            "analysis_count": report.analysis_count,
            "ready": report.ready,
            "verdict": report.verdict,
            "confidence": report.confidence,
            "confidence_level": report.confidence_level,
            "cache_hit": False,
        }

        # Collect warning and error messages.
        warnings = [
            f.message for f in all_findings
            if f.severity == SEVERITY_WARNING
        ]
        errors = [
            f.message for f in all_findings
            if f.severity == SEVERITY_ERROR
        ]

        # If the report is blocked, errors become warnings in the
        # StageResult so the pipeline can continue and downstream
        # engines can inspect the report.
        all_warnings = warnings + (
            errors if report.is_blocked else []
        )

        return StageResult(
            stage_name=self.name,
            success=True,
            outputs=outputs,
            metadata={
                "cache_hit": False,
                "analysis_count": report.analysis_count,
                "finding_count": report.finding_count,
                "error_count": report.error_count,
                "warning_count": report.warning_count,
                "ready": report.ready,
                "verdict": report.verdict,
                "confidence": report.confidence,
                "confidence_level": report.confidence_level,
                "is_blocked": report.is_blocked,
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
        TechnologySelectionData,
        RequirementNormalizationData,
        IntelligenceGraphData,
        KnowledgeData,
    ]:
        """Read all required data sources from the context.

        Args:
            context: The generation context.

        Returns:
            A tuple of the five data reader outputs.
        """
        arch_reader = ArchitectureDecisionReader()
        tech_reader = TechnologySelectionReader()
        req_reader = RequirementNormalizationReader()
        graph_reader = IntelligenceGraphReader()
        kb_reader = KnowledgeReader()

        arch_data = arch_reader.read(context)
        tech_data = tech_reader.read(context)
        req_data = req_reader.read(context)
        graph_data = graph_reader.read(context)
        kb_data = kb_reader.read(context)

        return arch_data, tech_data, req_data, graph_data, kb_data

    # ----------------------------------------------------------------- #
    # Analysis orchestration
    # ----------------------------------------------------------------- #

    def _run_analyses(
        self,
        arch_data: ArchitectureDecisionData,
        tech_data: TechnologySelectionData,
        req_data: RequirementNormalizationData,
        graph_data: IntelligenceGraphData,
        kb_data: KnowledgeData,
    ) -> tuple[
        Any,  # ComplexityAnalysis
        Any,  # ResourceEstimation
        Any,  # ScalabilityAnalysis
        Any,  # ArchitectureStressAnalysis
        Any,  # DependencyAnalysis
        List[AnalysisResult],
    ]:
        """Run all five analyses and collect per-dimension results.

        Args:
            arch_data: Architecture decision data.
            tech_data: Technology selection data.
            req_data: Requirement normalization data.
            graph_data: Intelligence graph data.
            kb_data: Knowledge base data.

        Returns:
            A tuple of (complexity, resources, scalability, stress,
            dependencies, analyses).
        """
        analyses: List[AnalysisResult] = []

        # Complexity analysis.
        try:
            complexity = self._complexity_analyzer.analyze(
                arch_data, tech_data, req_data, graph_data, kb_data
            )
            analyses.append(AnalysisResult(
                dimension=DIMENSION_COMPLEXITY,
                score=complexity.score,
                summary=complexity.summary,
                details=complexity.details,
            ))
        except Exception as e:
            _log.error(
                "Complexity analysis failed",
                exc_info=e,
            )
            complexity = self._complexity_analyzer.analyze(
                arch_data, tech_data, req_data, graph_data, kb_data
            )
            analyses.append(AnalysisResult(
                dimension=DIMENSION_COMPLEXITY,
                score=complexity.score,
                summary=complexity.summary,
                details=complexity.details,
            ))

        # Resource estimation.
        try:
            resources = self._resource_estimator.estimate(
                arch_data, tech_data, req_data, graph_data, kb_data
            )
            analyses.append(AnalysisResult(
                dimension=DIMENSION_RESOURCES,
                score=resources.score,
                summary=resources.summary,
                details=resources.details,
            ))
        except Exception as e:
            _log.error(
                "Resource estimation failed",
                exc_info=e,
            )
            resources = self._resource_estimator.estimate(
                arch_data, tech_data, req_data, graph_data, kb_data
            )
            analyses.append(AnalysisResult(
                dimension=DIMENSION_RESOURCES,
                score=resources.score,
                summary=resources.summary,
                details=resources.details,
            ))

        # Scalability analysis.
        try:
            scalability = self._scalability_analyzer.analyze(
                arch_data, tech_data, req_data, graph_data, kb_data
            )
            analyses.append(AnalysisResult(
                dimension=DIMENSION_SCALABILITY,
                score=scalability.score,
                summary=scalability.summary,
                details=scalability.details,
            ))
        except Exception as e:
            _log.error(
                "Scalability analysis failed",
                exc_info=e,
            )
            scalability = self._scalability_analyzer.analyze(
                arch_data, tech_data, req_data, graph_data, kb_data
            )
            analyses.append(AnalysisResult(
                dimension=DIMENSION_SCALABILITY,
                score=scalability.score,
                summary=scalability.summary,
                details=scalability.details,
            ))

        # Stress analysis.
        try:
            stress = self._stress_analyzer.analyze(
                arch_data, tech_data, req_data, graph_data, kb_data
            )
            analyses.append(AnalysisResult(
                dimension=DIMENSION_STRESS,
                score=stress.score,
                summary=stress.summary,
                details=stress.details,
            ))
        except Exception as e:
            _log.error(
                "Stress analysis failed",
                exc_info=e,
            )
            stress = self._stress_analyzer.analyze(
                arch_data, tech_data, req_data, graph_data, kb_data
            )
            analyses.append(AnalysisResult(
                dimension=DIMENSION_STRESS,
                score=stress.score,
                summary=stress.summary,
                details=stress.details,
            ))

        # Dependency analysis.
        try:
            dependencies = self._dependency_analyzer.analyze(
                arch_data, tech_data, req_data, graph_data, kb_data
            )
            analyses.append(AnalysisResult(
                dimension=DIMENSION_DEPENDENCIES,
                score=dependencies.score,
                summary=dependencies.summary,
                details=dependencies.details,
            ))
        except Exception as e:
            _log.error(
                "Dependency analysis failed",
                exc_info=e,
            )
            dependencies = self._dependency_analyzer.analyze(
                arch_data, tech_data, req_data, graph_data, kb_data
            )
            analyses.append(AnalysisResult(
                dimension=DIMENSION_DEPENDENCIES,
                score=dependencies.score,
                summary=dependencies.summary,
                details=dependencies.details,
            ))

        return (
            complexity,
            resources,
            scalability,
            stress,
            dependencies,
            analyses,
        )


__all__ = ["ProjectCapabilityAnalyzerEngine"]
