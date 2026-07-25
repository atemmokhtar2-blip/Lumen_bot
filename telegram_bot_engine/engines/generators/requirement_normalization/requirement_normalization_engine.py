"""
Requirement Normalization Engine (Specification 014).

The :class:`RequirementNormalizationEngine` is the engine responsible
for transforming **all** user requirements into a unified, canonical
model that all downstream engines can understand.  Its sole function
is normalization \u2014 it does not write code, create files, build the
project, or make architectural decisions.

Data sources
------------
The engine reads **five** data sources from the generation context:

1. **User Request** \u2014 the raw user message (via the
   ``analysis_report`` artefact, or the raw ``context.request``).
2. **Requirement Intelligence Report** \u2014 the
   ``requirement_intelligence_report`` artefact produced by the
   :class:`~telegram_bot_engine.engines.generators.requirement_intelligence.RequirementIntelligenceEngine`.
3. **Semantic Understanding Report** \u2014 the
   ``semantic_understanding_report`` artefact produced by the
   :class:`~telegram_bot_engine.engines.generators.semantic_understanding.SemanticUnderstandingEngine`.
4. **Project Context** \u2014 the ``project_context`` artefact produced by
   the
   :class:`~telegram_bot_engine.engines.generators.project_context.ProjectContextEngine`.
5. **Knowledge Base** \u2014 the ``knowledge_base`` artefact, if present
   (a free-form dictionary of pre-approved assumptions, synonyms,
   abbreviations, and domain knowledge).

Responsibility
--------------
* Unify all component names, feature names, module names, and
  terminology into a single canonical model.
* Remove duplicate requirements and irrelevant information.
* Preserve all important information \u2014 no requirement is lost.
* Validate consistency (no duplicates, no conflicts, no
  terminology variations for the same thing).
* Link each requirement to its Feature, Component, Priority,
  Dependencies, and Expected Output.
* Cache the normalized model for performance.
* Scale from small to very large projects.
* Enforce a quality rule: no requirement passes unless it has been
  converted to the canonical model.

What this engine does NOT do
----------------------------
* It does **not** write code.
* It does **not** create files on disk.
* It does **not** build the project.
* It does **not** make architectural decisions.

Output
------
The final output is a :class:`NormalizationReport`, stored in the
context as the ``requirement_normalization_report`` artefact.  This
is the **Normalized Requirement Model** (Canonical Model) that all
downstream engines use as their unified reference.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .cache_manager import CacheManager
from .consistency_validator import ConsistencyValidator
from .context_reader import ContextData, ContextReader
from .deduplication_remover import DeduplicationRemover
from .knowledge_reader import KnowledgeData, KnowledgeReader
from .name_normalizer import NameNormalizer
from .quality_gate import QualityGate
from .report_assembler import ReportAssembler
from .report_data import (
    CACHE_HIT,
    CONFIDENCE_HIGH_THRESHOLD,
    CONFIDENCE_MEDIUM_THRESHOLD,
    ConflictRecord,
    DuplicateRecord,
    NormalizationProvenance,
    NormalizationReport,
    NormalizedRequirement,
    PRIORITY_MEDIUM,
    RequirementLink,
    SEVERITY_ERROR,
    SOURCE_REQUIREMENT_INTELLIGENCE,
    STATUS_ACTIVE,
    TerminologyMapping,
)
from .request_reader import RequestData, RequestReader
from .requirement_intelligence_reader import (
    RequirementIntelligenceData,
    RequirementIntelligenceReader,
)
from .requirement_linker import RequirementLinker
from .semantic_understanding_reader import (
    SemanticUnderstandingData,
    SemanticUnderstandingReader,
)
from .terminology_normalizer import TerminologyNormalizer


class RequirementNormalizationEngine(BaseEngine):
    """The engine that transforms all user requirements into a
    unified, canonical model.

    This engine is the authority on *normalizing* the user's
    requirements.  It reads the five data sources (user request,
    requirement intelligence report, semantic understanding report,
    project context, knowledge base), unifies all names and
    terminology, removes duplicates, validates consistency, links
    each requirement to its feature/component/priority/dependencies/
    expected output, caches the result, and produces the
    ``requirement_normalization_report`` artefact.

    The engine does **not** write code, create files, build the
    project, or make architectural decisions.  Its sole function is
    to produce the Normalized Requirement Model.
    """

    def __init__(self) -> None:
        super().__init__(
            name="requirement_normalization",
            version="1.0.0",
            description=(
                "Transforms all user requirements into a unified, "
                "canonical model that all downstream engines can "
                "understand.  Reads the User Request, Requirement "
                "Intelligence Report, Semantic Understanding "
                "Report, Project Context, and Knowledge Base.  "
                "Unifies all component names, feature names, "
                "module names, and terminology.  Removes "
                "duplicates and irrelevant information.  "
                "Preserves all important information.  Validates "
                "consistency (no duplicates, no conflicts, no "
                "terminology variations).  Links each requirement "
                "to its Feature, Component, Priority, "
                "Dependencies, and Expected Output.  Caches the "
                "normalized model for performance.  Scales from "
                "small to very large projects.  Enforces a "
                "quality rule: no requirement passes unless it "
                "has been converted to the canonical model.  "
                "Does not write code, create files, build the "
                "project, or make architectural decisions."
            ),
            tags=["generation", "normalization", "canonical"],
            metadata={"phase": "normalization"},
        )
        self._request_reader = RequestReader()
        self._requirement_intelligence_reader = (
            RequirementIntelligenceReader()
        )
        self._semantic_understanding_reader = (
            SemanticUnderstandingReader()
        )
        self._context_reader = ContextReader()
        self._knowledge_reader = KnowledgeReader()
        self._name_normalizer = NameNormalizer()
        self._terminology_normalizer = TerminologyNormalizer()
        self._deduplication_remover = DeduplicationRemover()
        self._consistency_validator = ConsistencyValidator()
        self._requirement_linker = RequirementLinker()
        self._cache_manager = CacheManager()
        self._quality_gate = QualityGate()
        self._assembler = ReportAssembler()

    # ----------------------------------------------------------------- #
    # Main entry point
    # ----------------------------------------------------------------- #

    def execute(self, context: GenerationContext) -> StageResult:
        """Build the Normalization Report and produce the report
        artefact.

        Steps:
            1. Read the five data sources.
            2. Check the cache.
            3. Build the initial normalized requirements.
            4. Unify all names (name normalization).
            5. Unify all terminology (terminology normalization).
            6. Remove duplicates (deduplication).
            7. Validate consistency (consistency validation).
            8. Link each requirement (requirement linking).
            9. Build the provenance.
            10. Calculate the confidence score.
            11. Assemble the final report.
            12. Validate quality (quality gate).
            13. Store the report in the cache.
            14. Store the report in the generation context.
        """
        gen_start = time.perf_counter()

        # Step 1: read the five data sources.
        request = self._request_reader.read(context)
        requirement_data = (
            self._requirement_intelligence_reader.read(context)
        )
        semantic_data = self._semantic_understanding_reader.read(context)
        context_data = self._context_reader.read(context)
        knowledge_data = self._knowledge_reader.read(context)

        self._log.info(
            "Starting requirement normalization",
            {
                "request_available": request.available,
                "requirement_intelligence_available": (
                    requirement_data.available
                ),
                "semantic_understanding_available": (
                    semantic_data.available
                ),
                "context_available": context_data.available,
                "knowledge_available": knowledge_data.available,
            },
        )

        # If no request data at all, we cannot proceed.
        if not request.available:
            report = self._build_empty_report(
                request, requirement_data, semantic_data,
                context_data, knowledge_data,
            )
            context.set("requirement_normalization_report", report)
            return self.failed(
                errors=[
                    "No user request data available. The "
                    "Requirement Normalization Engine requires at "
                    "least the user's request to proceed."
                ],
                outputs={"requirement_normalization_report": report},
            )

        # Step 2: check the cache.
        cache_info = self._cache_manager.get_cache_info(
            requirement_data, semantic_data, request,
        )
        if cache_info.hit:
            cached_report = self._cache_manager.get_cached(cache_info)
            if cached_report is not None:
                # Rebuild the provenance and notes for the cached
                # report.
                cached_report.provenance = (
                    self._assembler.build_provenance(
                        request=request,
                        requirement_data=requirement_data,
                        semantic_data=semantic_data,
                        context_data=context_data,
                        knowledge_data=knowledge_data,
                    )
                )
                cached_report.notes = self._assembler.build_notes(
                    report=cached_report,
                    request=request,
                    requirement_data=requirement_data,
                    semantic_data=semantic_data,
                    context_data=context_data,
                    knowledge_data=knowledge_data,
                )
                cached_report.summary = (
                    self._assembler._build_summary(cached_report)
                )
                cached_report.warnings = (
                    self._assembler.collect_warnings(cached_report)
                )

                context.set(
                    "requirement_normalization_report",
                    cached_report,
                )
                context.metadata[
                    "requirement_normalization"
                ] = cached_report

                total_duration_ms = (
                    (time.perf_counter() - gen_start) * 1000
                )
                self._log.info(
                    "Requirement normalization served from cache",
                    {
                        "cache_key": cache_info.cache_key,
                        "requirement_count": (
                            cached_report.requirement_count
                        ),
                        "duration_ms": round(total_duration_ms, 2),
                    },
                )
                return self.ok(
                    outputs={
                        "requirement_normalization_report":
                            cached_report,
                    },
                    metadata={
                        "cache_hit": True,
                        "cache_key": cache_info.cache_key,
                        "requirement_count": (
                            cached_report.requirement_count
                        ),
                        "active_requirement_count": (
                            cached_report.active_requirement_count
                        ),
                        "confidence": cached_report.confidence,
                        "confidence_level": (
                            cached_report.confidence_level
                        ),
                        "ready": cached_report.ready,
                        "duration_ms": round(total_duration_ms, 2),
                    },
                )

        # Step 3: build the initial normalized requirements.
        requirements = self._build_initial_requirements(
            request, requirement_data, semantic_data,
        )
        original_count = len(requirements)
        self._log.info(
            "Initial requirements built",
            {
                "initial_count": original_count,
            },
        )

        # Step 4: unify all names (name normalization).
        canonical_names = self._name_normalizer.normalize(
            request_features=request.features,
            request_keywords=request.keywords,
            requirement_data=requirement_data,
            semantic_data=semantic_data,
            context_data=context_data,
            knowledge_data=knowledge_data,
        )
        self._log.info(
            "Name normalization complete",
            {
                "canonical_name_count": len(canonical_names),
            },
        )

        # Step 5: unify all terminology (terminology normalization).
        terminology_mappings = self._terminology_normalizer.normalize(
            request_keywords=request.keywords,
            requirement_data=requirement_data,
            semantic_data=semantic_data,
            knowledge_data=knowledge_data,
        )
        self._log.info(
            "Terminology normalization complete",
            {
                "terminology_mapping_count": len(terminology_mappings),
            },
        )

        # Step 6: remove duplicates (deduplication).
        requirements, duplicates = (
            self._deduplication_remover.remove(requirements)
        )
        self._log.info(
            "Deduplication complete",
            {
                "duplicate_count": len(duplicates),
                "remaining_count": len(requirements),
            },
        )

        # Step 7: validate consistency (consistency validation).
        consistency_findings, conflicts, consistency_passed = (
            self._consistency_validator.validate(
                requirements=requirements,
                terminology_mappings=terminology_mappings,
                original_count=original_count,
            )
        )
        self._log.info(
            "Consistency validation complete",
            {
                "consistency_findings": len(consistency_findings),
                "conflicts": len(conflicts),
                "passed": consistency_passed,
            },
        )

        # Step 8: link each requirement (requirement linking).
        links = self._requirement_linker.link(
            requirements=requirements,
            context_data=context_data,
            requirement_data=requirement_data,
            semantic_data=semantic_data,
            knowledge_data=knowledge_data,
        )
        self._log.info(
            "Requirement linking complete",
            {
                "link_count": len(links),
            },
        )

        # Step 9: build the provenance.
        provenance = self._assembler.build_provenance(
            request=request,
            requirement_data=requirement_data,
            semantic_data=semantic_data,
            context_data=context_data,
            knowledge_data=knowledge_data,
        )

        # Step 10: calculate the confidence score.
        confidence = self._calculate_confidence(
            request, requirement_data, semantic_data,
            context_data, knowledge_data, requirements, duplicates,
            conflicts,
        )
        confidence_level = self._classify_confidence(confidence)
        self._log.info(
            "Confidence calculated",
            {
                "confidence": confidence,
                "confidence_level": confidence_level,
            },
        )

        # Step 11: assemble the final report.
        all_findings = list(consistency_findings)
        report = self._assembler.assemble(
            requirements=requirements,
            canonical_names=canonical_names,
            terminology_mappings=terminology_mappings,
            links=links,
            duplicates=duplicates,
            conflicts=conflicts,
            cache_info=cache_info,
            findings=all_findings,
            confidence=confidence,
            confidence_level=confidence_level,
            original_request=(
                request.cleaned_request or request.raw_request
            ),
            normalized_request=(
                semantic_data.normalized_request
                or request.cleaned_request
                or request.raw_request
            ),
        )

        # Set the provenance on the report.
        report.provenance = provenance

        # Build the notes.
        report.notes = self._assembler.build_notes(
            report=report,
            request=request,
            requirement_data=requirement_data,
            semantic_data=semantic_data,
            context_data=context_data,
            knowledge_data=knowledge_data,
        )

        # Step 12: validate quality (quality gate).
        quality_findings, passed = self._quality_gate.validate(
            report, original_requirement_count=original_count,
        )

        # Rebuild the summary and warnings after quality validation.
        report.warnings = self._assembler.collect_warnings(report)

        self._log.info(
            "Quality validation complete",
            {
                "quality_findings": len(quality_findings),
                "passed": passed,
            },
        )

        # Step 13: store the report in the cache.
        self._cache_manager.store(cache_info, report)

        # Step 14: store the report in the generation context.
        context.set("requirement_normalization_report", report)
        context.metadata["requirement_normalization"] = report

        total_duration_ms = (time.perf_counter() - gen_start) * 1000

        self._log.info(
            "Requirement normalization complete",
            {
                "requirement_count": report.requirement_count,
                "active_requirement_count": (
                    report.active_requirement_count
                ),
                "canonical_name_count": (
                    report.canonical_name_count
                ),
                "terminology_mapping_count": (
                    report.terminology_mapping_count
                ),
                "link_count": report.link_count,
                "duplicate_count": report.duplicate_count,
                "conflict_count": report.conflict_count,
                "error_count": report.error_count,
                "warning_count": report.warning_count,
                "confidence": report.confidence,
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
                    "requirement_normalization_report": report,
                },
                warnings=report.warnings,
            )

        return self.ok(
            outputs={
                "requirement_normalization_report": report,
            },
            metadata={
                "requirement_count": report.requirement_count,
                "active_requirement_count": (
                    report.active_requirement_count
                ),
                "canonical_name_count": (
                    report.canonical_name_count
                ),
                "terminology_mapping_count": (
                    report.terminology_mapping_count
                ),
                "link_count": report.link_count,
                "duplicate_count": report.duplicate_count,
                "conflict_count": report.conflict_count,
                "error_count": report.error_count,
                "warning_count": report.warning_count,
                "confidence": report.confidence,
                "confidence_level": report.confidence_level,
                "ready": report.ready,
                "cache_hit": report.cache_hit,
                "duration_ms": round(total_duration_ms, 2),
            },
        )

    # ----------------------------------------------------------------- #
    # Helpers
    # ----------------------------------------------------------------- #

    def _build_initial_requirements(
        self,
        request: RequestData,
        requirement_data: RequirementIntelligenceData,
        semantic_data: SemanticUnderstandingData,
    ) -> List[NormalizedRequirement]:
        """Build the initial normalized requirements from the data
        sources.

        If the requirement intelligence report has requirements, use
        them.  Otherwise, build requirements from the semantic
        understanding features or the request features.
        """
        requirements: List[NormalizedRequirement] = []

        # If the requirement intelligence report has requirements,
        # convert them to NormalizedRequirement objects.
        if requirement_data.available and requirement_data.requirements:
            for i, raw in enumerate(
                requirement_data.requirements, start=1,
            ):
                req_id = f"NREQ-{i:03d}"
                original_id = raw.id or ""
                name = raw.name or ""
                display_name = raw.display_name or name
                description = raw.description or ""
                category = raw.category or "functional"
                priority = (
                    raw.priority.lower()
                    if raw.priority
                    and raw.priority.lower() in (
                        "critical", "high", "medium", "low",
                    )
                    else PRIORITY_MEDIUM
                )
                expected_output = raw.goal or ""

                original_forms: List[str] = []
                if name:
                    original_forms.append(name)
                if display_name and display_name != name:
                    original_forms.append(display_name)

                requirements.append(NormalizedRequirement(
                    id=req_id,
                    original_id=original_id,
                    name=name,
                    display_name=display_name,
                    description=description,
                    category=category,
                    priority=priority,
                    status=STATUS_ACTIVE,
                    expected_output=expected_output,
                    original_forms=original_forms,
                    source_artefact=(
                        SOURCE_REQUIREMENT_INTELLIGENCE
                    ),
                ))
            return requirements

        # If the semantic understanding report has features, build
        # requirements from them.
        if semantic_data.available and semantic_data.intent_features:
            for i, feature in enumerate(
                semantic_data.intent_features, start=1,
            ):
                req_id = f"NREQ-{i:03d}"
                name = feature or ""
                display_name = name.replace("_", " ").title()
                description = (
                    semantic_data.intent_description or ""
                )
                requirements.append(NormalizedRequirement(
                    id=req_id,
                    name=name,
                    display_name=display_name,
                    description=description,
                    category="functional",
                    priority=PRIORITY_MEDIUM,
                    status=STATUS_ACTIVE,
                    original_forms=[name] if name else [],
                    source_artefact=(
                        SOURCE_REQUIREMENT_INTELLIGENCE
                    ),
                ))
            return requirements

        # If the request has features, build requirements from them.
        if request.features:
            for i, feature in enumerate(
                request.features, start=1,
            ):
                req_id = f"NREQ-{i:03d}"
                name = feature
                display_name = feature.replace("_", " ").title()
                description = (
                    request.description or request.cleaned_request or ""
                )
                requirements.append(NormalizedRequirement(
                    id=req_id,
                    name=name,
                    display_name=display_name,
                    description=description,
                    category="functional",
                    priority=PRIORITY_MEDIUM,
                    status=STATUS_ACTIVE,
                    original_forms=[name],
                    source_artefact=(
                        SOURCE_REQUIREMENT_INTELLIGENCE
                    ),
                ))

        return requirements

    def _build_empty_report(
        self,
        request: RequestData,
        requirement_data: RequirementIntelligenceData,
        semantic_data: SemanticUnderstandingData,
        context_data: ContextData,
        knowledge_data: KnowledgeData,
    ) -> NormalizationReport:
        """Build an empty report when no request data is available."""
        provenance = self._assembler.build_provenance(
            request=request,
            requirement_data=requirement_data,
            semantic_data=semantic_data,
            context_data=context_data,
            knowledge_data=knowledge_data,
        )
        report = NormalizationReport(
            provenance=provenance,
        )
        report.add_finding(
            severity=SEVERITY_ERROR,
            code="no_request_data",
            message=(
                "No user request data was available for the "
                "Requirement Normalization Engine to process."
            ),
            affected="request",
            resolution_hint=(
                "Provide a user request for the engine to "
                "normalize."
            ),
            category="quality",
        )
        report.summary = self._assembler._build_summary(report)
        report.notes = self._assembler.build_notes(
            report=report,
            request=request,
            requirement_data=requirement_data,
            semantic_data=semantic_data,
            context_data=context_data,
            knowledge_data=knowledge_data,
        )
        report.warnings = self._assembler.collect_warnings(report)
        return report

    # ----------------------------------------------------------------- #
    # Confidence calculation
    # ----------------------------------------------------------------- #

    def _calculate_confidence(
        self,
        request: RequestData,
        requirement_data: RequirementIntelligenceData,
        semantic_data: SemanticUnderstandingData,
        context_data: ContextData,
        knowledge_data: KnowledgeData,
        requirements: List[NormalizedRequirement],
        duplicates: List[DuplicateRecord],
        conflicts: List[ConflictRecord],
    ) -> float:
        """Calculate the overall confidence in the normalization.

        The confidence is a weighted combination of:
        * Data source availability (40%).
        * Number of requirements (20%).
        * Number of duplicates (10% penalty).
        * Number of conflicts (15% penalty).
        * Linking success (15%).
        """
        # Data source availability (max 5 sources).
        sources_available = sum([
            request.available,
            requirement_data.available,
            semantic_data.available,
            context_data.available,
            knowledge_data.available,
        ])
        source_factor = sources_available / 5.0

        # Number of requirements.
        if requirements:
            req_factor = min(
                len(requirements) / 5.0, 1.0,
            )
        else:
            req_factor = 0.0

        # Duplicate penalty.
        if requirements:
            dup_penalty = len(duplicates) / (
                len(requirements) + len(duplicates)
            )
        else:
            dup_penalty = 0.0

        # Conflict penalty.
        if requirements:
            conflict_penalty = len(conflicts) / len(requirements)
        else:
            conflict_penalty = 0.0

        # Linking success.
        if requirements:
            linked = sum(
                1 for r in requirements
                if r.status == STATUS_ACTIVE
                and (r.feature or r.component)
            )
            link_factor = linked / len(requirements)
        else:
            link_factor = 0.0

        confidence = (
            (source_factor * 0.4)
            + (req_factor * 0.2)
            - (dup_penalty * 0.1)
            - (conflict_penalty * 0.15)
            + (link_factor * 0.15)
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


__all__ = ["RequirementNormalizationEngine"]
