"""
Report assembler — assembles the final Semantic Understanding Report.

The :class:`ReportAssembler` is the final step of the semantic
understanding pipeline.  It takes all the pieces produced by the other
helpers (intent, keywords, ambiguities, clarifications, relationships,
sentence analyses, provenance, confidence, language, style, normalized
request) and assembles them into a single
:class:`SemanticUnderstandingReport`.

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
from .language_rules import LanguageRulesData
from .report_data import (
    ClarificationRequest,
    CONFIDENCE_MEDIUM_THRESHOLD,
    ImportantKeyword,
    RequirementRelationship,
    SemanticAmbiguity,
    SemanticFinding,
    SemanticProvenance,
    SemanticUnderstandingReport,
    SentenceAnalysis,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    SOURCE_KNOWLEDGE_BASE,
    SOURCE_LANGUAGE_RULES,
    SOURCE_PROJECT_CONTEXT,
    SOURCE_REQUIREMENT_INTELLIGENCE,
    SOURCE_USER_REQUEST,
    UnifiedIntent,
)
from .request_reader import RequestData
from .requirement_report_reader import RequirementReportData


class ReportAssembler:
    """Assembles the final Semantic Understanding Report.

    The assembler takes all the pieces produced by the other helpers
    and assembles them into a single
    :class:`SemanticUnderstandingReport`.

    The assembler is the only component that creates the
    :class:`SemanticUnderstandingReport` — all other helpers produce
    their individual pieces.
    """

    def assemble(
        self,
        intent: UnifiedIntent,
        confidence: float,
        confidence_level: str,
        important_keywords: List[ImportantKeyword],
        ambiguities: List[SemanticAmbiguity],
        clarifications: List[ClarificationRequest],
        relationships: List[RequirementRelationship],
        sentence_analyses: List[SentenceAnalysis],
        findings: List[SemanticFinding],
        language: str,
        style: str,
        normalized_request: str,
        original_request: str,
    ) -> SemanticUnderstandingReport:
        """Assemble the final report from all the pieces.

        Parameters:
            intent: The unified intent.
            confidence: The overall confidence score (0.0–1.0).
            confidence_level: The confidence level (high/medium/low).
            important_keywords: The list of important keywords.
            ambiguities: The list of ambiguity points.
            clarifications: The list of clarification requests.
            relationships: The list of relationships.
            sentence_analyses: The list of sentence analyses.
            findings: The list of findings.
            language: The detected language.
            style: The detected style.
            normalized_request: The fully normalized request.
            original_request: The original, unmodified request.

        Returns:
            A :class:`SemanticUnderstandingReport`.
        """
        report = SemanticUnderstandingReport(
            intent=intent,
            confidence=confidence,
            confidence_level=confidence_level,
            important_keywords=important_keywords,
            ambiguities=ambiguities,
            clarifications=clarifications,
            relationships=relationships,
            sentence_analyses=sentence_analyses,
            findings=findings,
            language=language,
            style=style,
            normalized_request=normalized_request,
            original_request=original_request,
        )

        # Build the summary.
        report.summary = self._build_summary(report)

        return report

    # ----------------------------------------------------------------- #
    # Summary
    # ----------------------------------------------------------------- #

    @staticmethod
    def _build_summary(report: SemanticUnderstandingReport) -> str:
        """Build a human-readable summary of the report."""
        return (
            f"Semantic Understanding Report: "
            f"intent kind '{report.intent.kind}', "
            f"{report.keyword_count} keyword(s), "
            f"{report.ambiguity_count} ambiguity point(s), "
            f"{report.relationship_count} relationship(s), "
            f"{report.sentence_count} sentence(s), "
            f"{report.clarification_count} clarification(s), "
            f"{report.finding_count} finding(s). "
            f"Confidence: {report.confidence:.1%} ({report.confidence_level}). "
            f"Language: {report.language}, style: {report.style}. "
            f"{'Report is ready.' if report.ready else 'Report is not ready.'}"
        )

    # ----------------------------------------------------------------- #
    # Notes
    # ----------------------------------------------------------------- #

    def build_notes(
        self,
        report: SemanticUnderstandingReport,
        request: RequestData,
        context_data: ContextData,
        requirement_report: RequirementReportData,
        knowledge_data: KnowledgeData,
        language_rules: LanguageRulesData,
    ) -> List[str]:
        """Build the notes list for the report."""
        notes: List[str] = [
            f"Semantic Understanding Report generated at "
            f"{datetime.now(timezone.utc).isoformat()}.",
            f"Data sources used: "
            f"{', '.join(report.provenance.all_sources_used)}.",
            f"User request available: "
            f"{report.provenance.request_available}.",
            f"Requirement intelligence report available: "
            f"{report.provenance.requirement_intelligence_available}.",
            f"Project context available: "
            f"{report.provenance.project_context_available}.",
            f"Knowledge base available: "
            f"{report.provenance.knowledge_base_available}.",
            f"Language rules available: "
            f"{report.provenance.language_rules_available}.",
        ]

        if request.available:
            notes.append(
                f"Request language: {report.language}, "
                f"style: {report.style}."
            )

        if requirement_report.available:
            notes.append(
                f"Requirement intelligence report: "
                f"{len(requirement_report.requirements)} requirement(s), "
                f"intent confidence: "
                f"{requirement_report.intent_confidence:.1%}."
            )

        if context_data.available:
            notes.append(
                f"Project name from context: "
                f"{context_data.project_name or 'unknown'}."
            )

        if knowledge_data.available:
            notes.append(
                f"Knowledge base contributed "
                f"synonyms/abbreviations to the language rules."
            )

        if language_rules.available:
            notes.append(
                f"Language rules: "
                f"{len(language_rules.synonyms)} synonym(s), "
                f"{len(language_rules.abbreviations)} abbreviation(s), "
                f"{len(language_rules.dialect_map)} dialect mapping(s)."
            )

        if report.keyword_count > 0:
            top_kws = [
                kw.word for kw in report.top_keywords(5)
            ]
            notes.append(
                f"Top keywords: {', '.join(top_kws)}."
            )

        if report.ambiguity_count > 0:
            notes.append(
                f"Ambiguities detected: {report.ambiguity_count}."
            )

        if report.relationship_count > 0:
            notes.append(
                f"Relationships detected: {report.relationship_count}."
            )

        return notes

    # ----------------------------------------------------------------- #
    # Warnings
    # ----------------------------------------------------------------- #

    @staticmethod
    def collect_warnings(
        report: SemanticUnderstandingReport,
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
        requirement_report: RequirementReportData,
        context_data: ContextData,
        knowledge_data: KnowledgeData,
        language_rules: LanguageRulesData,
        language: str,
        style: str,
        normalized_request: str,
    ) -> SemanticProvenance:
        """Build the provenance record from the data sources."""
        sources_used: List[str] = []
        if request.available:
            sources_used.append(SOURCE_USER_REQUEST)
        if requirement_report.available:
            sources_used.append(SOURCE_REQUIREMENT_INTELLIGENCE)
        if context_data.available:
            sources_used.append(SOURCE_PROJECT_CONTEXT)
        if knowledge_data.available:
            sources_used.append(SOURCE_KNOWLEDGE_BASE)
        # Language rules are always available (built-in).
        sources_used.append(SOURCE_LANGUAGE_RULES)

        request_summary = (
            (request.cleaned_request or request.raw_request)[:200]
            if request.available else ""
        )

        requirement_count = (
            len(requirement_report.requirements)
            if requirement_report.available
            else 0
        )

        return SemanticProvenance(
            request_available=request.available,
            requirement_intelligence_available=(
                requirement_report.available
            ),
            project_context_available=context_data.available,
            knowledge_base_available=knowledge_data.available,
            language_rules_available=language_rules.available,
            all_sources_used=sources_used,
            request_summary=request_summary,
            request_language=language,
            request_style=style,
            requirement_count_from_intelligence=requirement_count,
        )


__all__ = ["ReportAssembler"]
