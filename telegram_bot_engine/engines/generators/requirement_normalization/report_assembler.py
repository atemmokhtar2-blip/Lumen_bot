"""
Report assembler \u2014 assembles the final Normalization Report
(Normalized Requirement Model).

The :class:`ReportAssembler` is the final step of the requirement
normalization pipeline.  It takes all the pieces produced by the
other helpers (normalized requirements, canonical names, terminology
mappings, links, duplicates, conflicts, cache info, findings,
provenance, confidence) and assembles them into a single
:class:`NormalizationReport`.

The assembler also:
* Builds the human-readable summary.
* Builds the notes list.
* Collects warnings from all sources.
* Builds the provenance record.

The assembler does **not** write code, create files, or make build
decisions.  It only *assembles* the report.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List

from .context_reader import ContextData
from .knowledge_reader import KnowledgeData
from .report_data import (
    CONFIDENCE_MEDIUM_THRESHOLD,
    ConflictRecord,
    DuplicateRecord,
    NormalizationProvenance,
    NormalizationReport,
    NormalizedRequirement,
    SEVERITY_WARNING,
    SOURCE_KNOWLEDGE_BASE,
    SOURCE_PROJECT_CONTEXT,
    SOURCE_REQUIREMENT_INTELLIGENCE,
    SOURCE_SEMANTIC_UNDERSTANDING,
    SOURCE_USER_REQUEST,
    TerminologyMapping,
)
from .request_reader import RequestData
from .requirement_intelligence_reader import (
    RequirementIntelligenceData,
)
from .semantic_understanding_reader import SemanticUnderstandingData


class ReportAssembler:
    """Assembles the final Normalization Report.

    The assembler takes all the pieces produced by the other helpers
    and assembles them into a single
    :class:`NormalizationReport`.

    The assembler is the only component that creates the
    :class:`NormalizationReport` \u2014 all other helpers produce
    their individual pieces.
    """

    def assemble(
        self,
        requirements: List[NormalizedRequirement],
        canonical_names: List,
        terminology_mappings: List[TerminologyMapping],
        links: List,
        duplicates: List[DuplicateRecord],
        conflicts: List[ConflictRecord],
        cache_info,
        findings: List,
        confidence: float,
        confidence_level: str,
        original_request: str,
        normalized_request: str,
    ) -> NormalizationReport:
        """Assemble the final report from all the pieces.

        Parameters:
            requirements: The list of normalized requirements.
            canonical_names: The list of canonical names.
            terminology_mappings: The list of terminology
                mappings.
            links: The list of requirement links.
            duplicates: The list of duplicate records.
            conflicts: The list of conflict records.
            cache_info: The cache info.
            findings: The list of findings.
            confidence: The overall confidence score (0.0\u20131.0).
            confidence_level: The confidence level
                (high/medium/low).
            original_request: The original, unmodified request.
            normalized_request: The fully normalized request.

        Returns:
            A :class:`NormalizationReport`.
        """
        report = NormalizationReport(
            requirements=requirements,
            canonical_names=canonical_names,
            terminology_mappings=terminology_mappings,
            links=links,
            duplicates=duplicates,
            conflicts=conflicts,
            cache_info=cache_info,
            findings=findings,
            confidence=confidence,
            confidence_level=confidence_level,
            original_request=original_request,
            normalized_request=normalized_request,
        )

        # Build the summary.
        report.summary = self._build_summary(report)

        return report

    # ----------------------------------------------------------------- #
    # Summary
    # ----------------------------------------------------------------- #

    @staticmethod
    def _build_summary(report: NormalizationReport) -> str:
        """Build a human-readable summary of the report."""
        return (
            f"Normalization Report: "
            f"{report.requirement_count} requirement(s) "
            f"({report.active_requirement_count} active), "
            f"{report.canonical_name_count} canonical name(s), "
            f"{report.terminology_mapping_count} terminology "
            f"mapping(s), {report.link_count} link(s), "
            f"{report.duplicate_count} duplicate(s), "
            f"{report.conflict_count} conflict(s), "
            f"{report.finding_count} finding(s). "
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
        report: NormalizationReport,
        request: RequestData,
        requirement_data: RequirementIntelligenceData,
        semantic_data: SemanticUnderstandingData,
        context_data: ContextData,
        knowledge_data: KnowledgeData,
    ) -> List[str]:
        """Build the notes list for the report."""
        notes: List[str] = [
            f"Normalization Report generated at "
            f"{datetime.now(timezone.utc).isoformat()}.",
            f"Data sources used: "
            f"{', '.join(report.provenance.all_sources_used)}.",
            f"User request available: "
            f"{report.provenance.request_available}.",
            f"Requirement intelligence report available: "
            f"{report.provenance.requirement_intelligence_available}.",
            f"Semantic understanding report available: "
            f"{report.provenance.semantic_understanding_available}.",
            f"Project context available: "
            f"{report.provenance.project_context_available}.",
            f"Knowledge base available: "
            f"{report.provenance.knowledge_base_available}.",
        ]

        if request.available:
            notes.append(
                f"Original request: "
                f"{(request.cleaned_request or request.raw_request)[:100]}"
                f"..."
                if len(request.cleaned_request or request.raw_request) > 100
                else f"Original request: "
                     f"{request.cleaned_request or request.raw_request}"
            )

        if requirement_data.available:
            notes.append(
                f"Requirement intelligence report: "
                f"{len(requirement_data.requirements)} "
                f"requirement(s), intent confidence: "
                f"{requirement_data.intent_confidence:.1%}."
            )

        if semantic_data.available:
            notes.append(
                f"Semantic understanding report: intent kind "
                f"'{semantic_data.intent_kind}', "
                f"{len(semantic_data.keywords)} keyword(s), "
                f"confidence: {semantic_data.confidence:.1%}."
            )

        if context_data.available:
            notes.append(
                f"Project context: "
                f"{len(context_data.feature_names)} feature(s), "
                f"{len(context_data.component_names)} "
                f"component(s)."
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

        if report.canonical_name_count > 0:
            notes.append(
                f"Canonical names: "
                f"{report.canonical_name_count} unified name(s)."
            )

        if report.terminology_mapping_count > 0:
            notes.append(
                f"Terminology mappings: "
                f"{report.terminology_mapping_count} unified "
                f"term(s)."
            )

        if report.duplicate_count > 0:
            notes.append(
                f"Duplicates removed: "
                f"{report.duplicate_count}."
            )

        if report.conflict_count > 0:
            notes.append(
                f"Conflicts detected: "
                f"{report.conflict_count}."
            )

        if report.cache_hit:
            notes.append(
                "Cache hit: the normalized model was served from "
                "cache."
            )

        return notes

    # ----------------------------------------------------------------- #
    # Warnings
    # ----------------------------------------------------------------- #

    @staticmethod
    def collect_warnings(
        report: NormalizationReport,
    ) -> List[str]:
        """Collect all warnings from the report."""
        warnings: List[str] = []

        # Warnings from findings.
        for finding in report.findings:
            if finding.severity == SEVERITY_WARNING:
                warnings.append(f"[{finding.code}] {finding.message}")

        return warnings

    # ----------------------------------------------------------------- #
    # Provenance builder
    # ----------------------------------------------------------------- #

    @staticmethod
    def build_provenance(
        request: RequestData,
        requirement_data: RequirementIntelligenceData,
        semantic_data: SemanticUnderstandingData,
        context_data: ContextData,
        knowledge_data: KnowledgeData,
    ) -> NormalizationProvenance:
        """Build the provenance record from the data sources."""
        sources_used: List[str] = []
        if request.available:
            sources_used.append(SOURCE_USER_REQUEST)
        if requirement_data.available:
            sources_used.append(SOURCE_REQUIREMENT_INTELLIGENCE)
        if semantic_data.available:
            sources_used.append(SOURCE_SEMANTIC_UNDERSTANDING)
        if context_data.available:
            sources_used.append(SOURCE_PROJECT_CONTEXT)
        if knowledge_data.available:
            sources_used.append(SOURCE_KNOWLEDGE_BASE)

        request_summary = (
            (request.cleaned_request or request.raw_request)[:200]
            if request.available else ""
        )

        requirement_count = (
            len(requirement_data.requirements)
            if requirement_data.available
            else 0
        )

        return NormalizationProvenance(
            request_available=request.available,
            requirement_intelligence_available=(
                requirement_data.available
            ),
            semantic_understanding_available=(
                semantic_data.available
            ),
            project_context_available=context_data.available,
            knowledge_base_available=knowledge_data.available,
            all_sources_used=sources_used,
            request_summary=request_summary,
            requirement_count_from_intelligence=requirement_count,
            intent_kind=semantic_data.intent_kind,
            semantic_confidence=semantic_data.confidence,
            normalized_request=semantic_data.normalized_request,
        )


__all__ = ["ReportAssembler"]
