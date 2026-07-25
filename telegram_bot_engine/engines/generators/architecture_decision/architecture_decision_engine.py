"""
Architecture Decision Engine (Specification 015).

The :class:`ArchitectureDecisionEngine` is the engine responsible
for making **all** architectural decisions for the project.  Its
sole function is selecting the best architecture based on prior
analysis — it does **not** write code, create files, or build the
project.

Data sources
------------
The engine reads **five** data sources from the generation context:

1. **Normalized Requirement Model** — the
   ``requirement_normalization_report`` artefact produced by the
   :class:`~telegram_bot_engine.engines.generators.requirement_normalization.RequirementNormalizationEngine`.
2. **Project Intelligence Graph** — the ``intelligence_graph``
   artefact produced by the
   :class:`~telegram_bot_engine.engines.generators.intelligence_graph.IntelligenceGraphEngine`.
3. **Requirement Intelligence Report** — the
   ``requirement_intelligence_report`` artefact produced by the
   :class:`~telegram_bot_engine.engines.generators.requirement_intelligence.RequirementIntelligenceEngine`.
4. **Semantic Understanding Report** — the
   ``semantic_understanding_report`` artefact produced by the
   :class:`~telegram_bot_engine.engines.generators.semantic_understanding.SemanticUnderstandingEngine`.
5. **Knowledge Base** — the ``knowledge_base`` artefact, if
   present.

Responsibility
--------------
* Analyse the project size, scalability, performance, security,
  and maintainability.
* Select the best architecture: layers, modules, services,
  dependency structure, project layout, communication pattern,
  error handling strategy, and configuration strategy.
* Validate every decision (reason, analysis, impact, rejected
  alternatives).
* Cache the decision report for performance.
* Scale from small to very large projects.
* Enforce a quality rule: no architecture that fails quality or
  scalability requirements is allowed.

What this engine does NOT do
----------------------------
* It does **not** write code.
* It does **not** create files on disk.
* It does **not** build the project.

Output
------
The final output is an :class:`ArchitectureDecisionReport`,
stored in the context as the ``architecture_decision_report``
artefact.  This is the official reference for all other engines.
"""

from __future__ import annotations

import time
from typing import List, Tuple

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .architecture_selector import ArchitectureSelector
from .cache_manager import CacheManager
from .decision_validator import DecisionValidator
from .intelligence_graph_reader import (
    IntelligenceGraphData,
    IntelligenceGraphReader,
)
from .knowledge_reader import KnowledgeData, KnowledgeReader
from .maintainability_analyzer import MaintainabilityAnalyzer
from .performance_analyzer import PerformanceAnalyzer
from .quality_gate import QualityGate
from .report_assembler import ReportAssembler
from .report_data import (
    AnalysisResult,
    ArchitectureDecision,
    ArchitectureDecisionReport,
    ArchitectureFinding,
    ArchitectureProvenance,
    CONFIDENCE_HIGH_THRESHOLD,
    CONFIDENCE_MEDIUM_THRESHOLD,
    DIMENSION_SIZE,
    ModuleSpec,
    SEVERITY_ERROR,
    ServiceSpec,
)
from .requirement_intelligence_reader import (
    RequirementIntelligenceData,
    RequirementIntelligenceReader,
)
from .requirement_normalization_reader import (
    RequirementNormalizationData,
    RequirementNormalizationReader,
)
from .scalability_analyzer import ScalabilityAnalyzer
from .security_analyzer import SecurityAnalyzer
from .semantic_understanding_reader import (
    SemanticUnderstandingData,
    SemanticUnderstandingReader,
)
from .size_analyzer import SizeAnalyzer


class ArchitectureDecisionEngine(BaseEngine):
    """The engine that makes all architectural decisions for the
    project.

    This engine is the authority on *architectural decisions*.  It
    reads the five data sources (normalized requirement model,
    intelligence graph, requirement intelligence report, semantic
    understanding report, knowledge base), analyses the project
    across five dimensions (size, scalability, performance,
    security, maintainability), makes all eight architectural
    decisions (layers, modules, services, dependency structure,
    project layout, communication pattern, error handling
    strategy, configuration strategy), validates every decision,
    caches the result, and produces the
    ``architecture_decision_report`` artefact.

    The engine does **not** write code, create files, build the
    project, or perform any action other than producing the
    Architecture Decision Report.  Its sole function is selecting
    the best architecture based on prior analysis.
    """

    def __init__(self) -> None:
        super().__init__(
            name="architecture_decision",
            version="1.0.0",
            description=(
                "Makes all architectural decisions for the "
                "project based on prior analysis.  Reads the "
                "Normalized Requirement Model, Project "
                "Intelligence Graph, Requirement Intelligence "
                "Report, Semantic Understanding Report, and "
                "Knowledge Base.  Analyses the project size, "
                "scalability, performance, security, and "
                "maintainability.  Selects the best "
                "architecture: layers, modules, services, "
                "dependency structure, project layout, "
                "communication pattern, error handling "
                "strategy, and configuration strategy.  "
                "Validates every decision (reason, analysis, "
                "impact, rejected alternatives).  Caches the "
                "decision report for performance.  Scales from "
                "small to very large projects.  Enforces a "
                "quality rule: no architecture that fails "
                "quality or scalability requirements is "
                "allowed.  Does not write code, create files, "
                "or build the project."
            ),
            tags=["generation", "architecture", "decision"],
            metadata={"phase": "architecture"},
        )
        self._requirement_normalization_reader = (
            RequirementNormalizationReader()
        )
        self._intelligence_graph_reader = (
            IntelligenceGraphReader()
        )
        self._requirement_intelligence_reader = (
            RequirementIntelligenceReader()
        )
        self._semantic_understanding_reader = (
            SemanticUnderstandingReader()
        )
        self._knowledge_reader = KnowledgeReader()
        self._size_analyzer = SizeAnalyzer()
        self._scalability_analyzer = ScalabilityAnalyzer()
        self._performance_analyzer = PerformanceAnalyzer()
        self._security_analyzer = SecurityAnalyzer()
        self._maintainability_analyzer = MaintainabilityAnalyzer()
        self._architecture_selector = ArchitectureSelector()
        self._decision_validator = DecisionValidator()
        self._cache_manager = CacheManager()
        self._quality_gate = QualityGate()
        self._assembler = ReportAssembler()

    # ----------------------------------------------------------------- #
    # Main entry point
    # ----------------------------------------------------------------- #

    def execute(self, context: GenerationContext) -> StageResult:
        """Build the Architecture Decision Report and produce the
        report artefact.

        Steps:
            1. Read the five data sources.
            2. Check the cache.
            3. Analyse the project size.
            4. Analyse the project scalability.
            5. Analyse the performance requirements.
            6. Analyse the security requirements.
            7. Analyse the maintainability.
            8. Select the architecture (all decisions, modules,
               services).
            9. Validate the decisions.
            10. Build the provenance.
            11. Calculate the confidence score.
            12. Assemble the final report.
            13. Validate quality (quality gate).
            14. Store the report in the cache and the context.
        """
        gen_start = time.perf_counter()

        # Step 1: read the five data sources.
        requirement_data = (
            self._requirement_normalization_reader.read(context)
        )
        graph_data = self._intelligence_graph_reader.read(context)
        requirement_intelligence_data = (
            self._requirement_intelligence_reader.read(context)
        )
        semantic_data = (
            self._semantic_understanding_reader.read(context)
        )
        knowledge_data = self._knowledge_reader.read(context)

        self._log.info(
            "Starting architecture decision",
            {
                "normalized_requirements_available": (
                    requirement_data.available
                ),
                "intelligence_graph_available": (
                    graph_data.available
                ),
                "requirement_intelligence_available": (
                    requirement_intelligence_data.available
                ),
                "semantic_understanding_available": (
                    semantic_data.available
                ),
                "knowledge_available": knowledge_data.available,
            },
        )

        # If no data at all, we cannot proceed.
        if not (
            requirement_data.available
            or graph_data.available
            or requirement_intelligence_data.available
            or semantic_data.available
        ):
            report = self._build_empty_report(
                requirement_data,
                graph_data,
                requirement_intelligence_data,
                semantic_data,
                knowledge_data,
            )
            context.set("architecture_decision_report", report)
            return self.failed(
                errors=[
                    "No data sources available. The Architecture "
                    "Decision Engine requires at least one data "
                    "source to proceed."
                ],
                outputs={
                    "architecture_decision_report": report,
                },
            )

        # Step 2: check the cache.
        cache_info = self._cache_manager.get_cache_info(
            requirement_data,
            graph_data,
            requirement_intelligence_data,
            semantic_data,
            knowledge_data,
        )
        if cache_info.hit:
            cached_report = self._cache_manager.get_cached(
                cache_info
            )
            if cached_report is not None:
                # Update the cache info on the cached report so
                # that it reflects the current cache hit.
                cached_report.cache_info = cache_info
                # Rebuild the provenance, notes, and summary for
                # the cached report.
                cached_report.provenance = (
                    self._assembler.build_provenance(
                        requirement_data,
                        graph_data,
                        requirement_intelligence_data,
                        semantic_data,
                        knowledge_data,
                    )
                )
                cached_report.notes = self._assembler.build_notes(
                    report=cached_report,
                    requirement_data=requirement_data,
                    graph_data=graph_data,
                    requirement_intelligence_data=(
                        requirement_intelligence_data
                    ),
                    semantic_data=semantic_data,
                    knowledge_data=knowledge_data,
                )
                cached_report.summary = (
                    self._assembler._build_summary(cached_report)
                )
                cached_report.warnings = (
                    self._assembler.collect_warnings(cached_report)
                )

                context.set(
                    "architecture_decision_report",
                    cached_report,
                )
                context.metadata[
                    "architecture_decision"
                ] = cached_report

                total_duration_ms = (
                    (time.perf_counter() - gen_start) * 1000
                )
                self._log.info(
                    "Architecture decision served from cache",
                    {
                        "cache_key": cache_info.cache_key,
                        "decision_count": (
                            cached_report.decision_count
                        ),
                        "duration_ms": round(total_duration_ms, 2),
                    },
                )
                return self.ok(
                    outputs={
                        "architecture_decision_report":
                            cached_report,
                    },
                    metadata={
                        "cache_hit": True,
                        "cache_key": cache_info.cache_key,
                        "decision_count": (
                            cached_report.decision_count
                        ),
                        "module_count": (
                            cached_report.module_count
                        ),
                        "service_count": (
                            cached_report.service_count
                        ),
                        "confidence": cached_report.confidence,
                        "confidence_level": (
                            cached_report.confidence_level
                        ),
                        "ready": cached_report.ready,
                        "duration_ms": round(total_duration_ms, 2),
                    },
                )

        # Step 3: analyse the project size.
        size_analysis = self._size_analyzer.analyze(
            requirement_data, graph_data,
        )
        size_tier = size_analysis.level
        self._log.info(
            "Size analysis complete",
            {
                "size_tier": size_tier,
                "score": round(size_analysis.score, 3),
            },
        )

        # Step 4: analyse the project scalability.
        scalability_analysis = (
            self._scalability_analyzer.analyze(
                graph_data, requirement_data, size_tier,
            )
        )
        self._log.info(
            "Scalability analysis complete",
            {
                "level": scalability_analysis.level,
                "score": round(scalability_analysis.score, 3),
            },
        )

        # Step 5: analyse the performance requirements.
        performance_analysis = (
            self._performance_analyzer.analyze(
                semantic_data,
                requirement_intelligence_data,
                requirement_data,
            )
        )
        self._log.info(
            "Performance analysis complete",
            {
                "level": performance_analysis.level,
                "score": round(performance_analysis.score, 3),
            },
        )

        # Step 6: analyse the security requirements.
        security_analysis = self._security_analyzer.analyze(
            semantic_data,
            requirement_intelligence_data,
            requirement_data,
        )
        self._log.info(
            "Security analysis complete",
            {
                "level": security_analysis.level,
                "score": round(security_analysis.score, 3),
            },
        )

        # Step 7: analyse the maintainability.
        maintainability_analysis = (
            self._maintainability_analyzer.analyze(
                graph_data,
                requirement_intelligence_data,
                requirement_data,
                size_tier,
            )
        )
        self._log.info(
            "Maintainability analysis complete",
            {
                "level": maintainability_analysis.level,
                "score": round(maintainability_analysis.score, 3),
            },
        )

        # Collect all analyses.
        analyses: List[AnalysisResult] = [
            size_analysis,
            scalability_analysis,
            performance_analysis,
            security_analysis,
            maintainability_analysis,
        ]

        # Step 8: select the architecture.
        decisions, modules, services = (
            self._architecture_selector.select(
                analyses=analyses,
                graph_data=graph_data,
                requirement_data=requirement_data,
                requirement_intelligence_data=(
                    requirement_intelligence_data
                ),
                semantic_data=semantic_data,
            )
        )
        self._log.info(
            "Architecture selection complete",
            {
                "decision_count": len(decisions),
                "module_count": len(modules),
                "service_count": len(services),
            },
        )

        # Step 9: build the provenance.
        provenance = self._assembler.build_provenance(
            requirement_data,
            graph_data,
            requirement_intelligence_data,
            semantic_data,
            knowledge_data,
        )

        # Step 10: calculate the confidence score.
        confidence = self._calculate_confidence(
            requirement_data,
            graph_data,
            requirement_intelligence_data,
            semantic_data,
            knowledge_data,
            decisions,
        )
        confidence_level = self._classify_confidence(confidence)
        self._log.info(
            "Confidence calculated",
            {
                "confidence": round(confidence, 3),
                "confidence_level": confidence_level,
            },
        )

        # Step 11: assemble the final report.
        report = self._assembler.assemble(
            analyses=analyses,
            decisions=decisions,
            modules=modules,
            services=services,
            cache_info=cache_info,
            provenance=provenance,
            confidence=confidence,
            confidence_level=confidence_level,
        )

        # Build the notes.
        report.notes = self._assembler.build_notes(
            report=report,
            requirement_data=requirement_data,
            graph_data=graph_data,
            requirement_intelligence_data=(
                requirement_intelligence_data
            ),
            semantic_data=semantic_data,
            knowledge_data=knowledge_data,
        )

        # Step 12: validate the decisions.
        validation_findings, validation_passed = (
            self._decision_validator.validate(report)
        )
        for finding in validation_findings:
            report.findings.append(finding)
        self._log.info(
            "Decision validation complete",
            {
                "validation_findings": len(validation_findings),
                "passed": validation_passed,
            },
        )

        # Step 13: validate quality (quality gate).
        quality_findings, quality_passed = (
            self._quality_gate.validate(report)
        )
        for finding in quality_findings:
            report.findings.append(finding)

        # Rebuild the summary and warnings after validation.
        report.summary = self._assembler._build_summary(report)
        report.warnings = self._assembler.collect_warnings(report)

        self._log.info(
            "Quality validation complete",
            {
                "quality_findings": len(quality_findings),
                "passed": quality_passed,
            },
        )

        # Step 14: store the report in the cache and the context.
        self._cache_manager.store(cache_info, report)
        context.set("architecture_decision_report", report)
        context.metadata["architecture_decision"] = report

        total_duration_ms = (time.perf_counter() - gen_start) * 1000

        self._log.info(
            "Architecture decision complete",
            {
                "analysis_count": report.analysis_count,
                "decision_count": report.decision_count,
                "module_count": report.module_count,
                "service_count": report.service_count,
                "error_count": report.error_count,
                "warning_count": report.warning_count,
                "confidence": round(report.confidence, 3),
                "confidence_level": report.confidence_level,
                "ready": report.ready,
                "cache_hit": report.cache_hit,
                "duration_ms": round(total_duration_ms, 2),
            },
        )

        # Separate errors and warnings.
        error_findings = [
            f for f in report.findings
            if f.severity == SEVERITY_ERROR
        ]

        if error_findings:
            error_messages = [
                f"[{f.code}] {f.message}" for f in error_findings
            ]
            return self.failed(
                errors=error_messages,
                outputs={
                    "architecture_decision_report": report,
                },
                warnings=report.warnings,
            )

        return self.ok(
            outputs={
                "architecture_decision_report": report,
            },
            metadata={
                "analysis_count": report.analysis_count,
                "decision_count": report.decision_count,
                "module_count": report.module_count,
                "service_count": report.service_count,
                "error_count": report.error_count,
                "warning_count": report.warning_count,
                "confidence": round(report.confidence, 3),
                "confidence_level": report.confidence_level,
                "ready": report.ready,
                "cache_hit": report.cache_hit,
                "duration_ms": round(total_duration_ms, 2),
            },
        )

    # ----------------------------------------------------------------- #
    # Helpers
    # ----------------------------------------------------------------- #

    def _build_empty_report(
        self,
        requirement_data: RequirementNormalizationData,
        graph_data: IntelligenceGraphData,
        requirement_intelligence_data: RequirementIntelligenceData,
        semantic_data: SemanticUnderstandingData,
        knowledge_data: KnowledgeData,
    ) -> ArchitectureDecisionReport:
        """Build an empty report when no data sources are
        available."""
        provenance = self._assembler.build_provenance(
            requirement_data,
            graph_data,
            requirement_intelligence_data,
            semantic_data,
            knowledge_data,
        )
        report = ArchitectureDecisionReport(
            provenance=provenance,
        )
        report.add_finding(
            severity=SEVERITY_ERROR,
            code="no_data_sources",
            message=(
                "No data sources were available for the "
                "Architecture Decision Engine to process."
            ),
            affected="data_sources",
            resolution_hint=(
                "Provide at least one data source (normalized "
                "requirement model, intelligence graph, "
                "requirement intelligence report, or semantic "
                "understanding report)."
            ),
            category="quality",
        )
        report.summary = self._assembler._build_summary(report)
        report.notes = self._assembler.build_notes(
            report=report,
            requirement_data=requirement_data,
            graph_data=graph_data,
            requirement_intelligence_data=(
                requirement_intelligence_data
            ),
            semantic_data=semantic_data,
            knowledge_data=knowledge_data,
        )
        report.warnings = self._assembler.collect_warnings(report)
        return report

    # ----------------------------------------------------------------- #
    # Confidence calculation
    # ----------------------------------------------------------------- #

    def _calculate_confidence(
        self,
        requirement_data: RequirementNormalizationData,
        graph_data: IntelligenceGraphData,
        requirement_intelligence_data: RequirementIntelligenceData,
        semantic_data: SemanticUnderstandingData,
        knowledge_data: KnowledgeData,
        decisions: List[ArchitectureDecision],
    ) -> float:
        """Calculate the overall confidence in the architecture
        decision.

        The confidence is a weighted combination of:
        * Data source availability (40%).
        * Number of decisions (20%).
        * Number of validated decisions (25%).
        * Analysis coverage (15%).
        """
        # Data source availability (max 5 sources).
        sources_available = sum([
            requirement_data.available,
            graph_data.available,
            requirement_intelligence_data.available,
            semantic_data.available,
            knowledge_data.available,
        ])
        source_factor = sources_available / 5.0

        # Number of decisions (expect 8).
        if decisions:
            decision_factor = min(len(decisions) / 8.0, 1.0)
        else:
            decision_factor = 0.0

        # Number of validated decisions.
        if decisions:
            validated = sum(
                1 for d in decisions
                if d.reason and d.analysis and d.impact
                and d.rejected_alternatives
            )
            validated_factor = validated / len(decisions)
        else:
            validated_factor = 0.0

        # Analysis coverage (expect 5 dimensions).
        # This is simplified — all 5 analyses are always
        # performed, so the coverage is 1.0.
        analysis_factor = 1.0

        confidence = (
            (source_factor * 0.4)
            + (decision_factor * 0.2)
            + (validated_factor * 0.25)
            + (analysis_factor * 0.15)
        )

        # Clamp to [0.0, 1.0].
        return max(0.0, min(1.0, confidence))

    @staticmethod
    def _classify_confidence(confidence: float) -> str:
        """Classify the confidence into high/medium/low."""
        if confidence >= CONFIDENCE_HIGH_THRESHOLD:
            return "high"
        if confidence >= CONFIDENCE_MEDIUM_THRESHOLD:
            return "medium"
        return "low"


__all__ = ["ArchitectureDecisionEngine"]
