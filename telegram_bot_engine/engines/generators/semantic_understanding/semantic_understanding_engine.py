"""
Semantic Understanding Engine (Specification 013).

The :class:`SemanticUnderstandingEngine` is the engine responsible for
understanding the **true meaning** of the user's request.  It does not
rely on keywords alone — it relies on understanding the **intent**, the
**context**, and the **meaning**.

Data sources
------------
The engine reads **five** data sources from the generation context:

1. **User Request** — the raw user message (via the
   ``analysis_report`` artefact, or the raw ``context.request``).
2. **Requirement Intelligence Report** — the
   ``requirement_intelligence_report`` artefact produced by the
   :class:`~telegram_bot_engine.engines.generators.requirement_intelligence.RequirementIntelligenceEngine`.
3. **Project Context** — the ``project_context`` artefact produced by
   the
   :class:`~telegram_bot_engine.engines.generators.project_context.ProjectContextEngine`.
4. **Knowledge Base** — the ``knowledge_base`` artefact, if present.
5. **Language Rules** — the built-in language rules (Arabic, English,
   slang, formal, abbreviations, spelling mistakes, mixed languages).

Responsibility
--------------
* Understand the *true meaning* of the user's request.
* Handle Arabic, English, slang, formal, colloquial, and mixed
  languages.
* Map all the different ways the user could write the same request to
  a single, unified :class:`UnifiedIntent`.
* Detect points of ambiguity and request clarification (no guessing).
* Understand the relationships between the parts of the request.
* Calculate the confidence score.
* Produce a :class:`SemanticUnderstandingReport` stored as the
  ``semantic_understanding_report`` artefact.

What this engine does NOT do
----------------------------
* It does **not** write code.
* It does **not** create files on disk.
* It does **not** choose libraries.
* It does **not** make build decisions.

Output
------
The final output is a :class:`SemanticUnderstandingReport`, stored in
the context as the ``semantic_understanding_report`` artefact.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .ambiguity_detector import AmbiguityDetector
from .confidence_calculator import ConfidenceCalculator
from .context_awareness import ContextAwareness
from .context_reader import ContextData, ContextReader
from .intent_extractor import IntentExtractor
from .intent_mapper import IntentMapper
from .knowledge_reader import KnowledgeData, KnowledgeReader
from .language_rules import LanguageRules, LanguageRulesData
from .quality_gate import QualityGate
from .report_assembler import ReportAssembler
from .report_data import (
    CONFIDENCE_MEDIUM_THRESHOLD,
    RequirementRelationship,
    SEVERITY_ERROR,
    SemanticUnderstandingReport,
)
from .request_reader import RequestData, RequestReader
from .requirement_report_reader import (
    RequirementReportData,
    RequirementReportReader,
)
from .sentence_analyzer import SentenceAnalyzer


class SemanticUnderstandingEngine(BaseEngine):
    """The engine that understands the true meaning of the user's
    request.

    This engine is the authority on *understanding* the user's intent.
    It reads the five data sources (user request, requirement
    intelligence report, project context, knowledge base, language
    rules), performs full sentence analysis, extracts the true
    intent, maps all variations to a unified intent, detects
    ambiguities, understands the relationships between the parts of
    the request, calculates the confidence score, and produces the
    ``semantic_understanding_report`` artefact.

    The engine does **not** write code, create files, choose
    libraries, or make build decisions.  Its sole function is to
    understand the user's intent.
    """

    def __init__(self) -> None:
        super().__init__(
            name="semantic_understanding",
            version="1.0.0",
            description=(
                "Understands the true meaning of the user's request. "
                "Reads the User Request, Requirement Intelligence "
                "Report, Project Context, Knowledge Base, and "
                "Language Rules.  Performs full sentence analysis "
                "(dialect normalization, spell correction, "
                "abbreviation expansion, synonym resolution), "
                "extracts the true intent, maps all variations to "
                "a unified intent, detects ambiguities and requests "
                "clarification, understands the relationships "
                "between the parts of the request, calculates the "
                "confidence score, and produces the Semantic "
                "Understanding Report.  Does not write code, create "
                "files, or make build decisions."
            ),
            tags=["generation", "understanding", "semantic"],
            metadata={"phase": "understanding"},
        )
        self._request_reader = RequestReader()
        self._requirement_report_reader = RequirementReportReader()
        self._context_reader = ContextReader()
        self._knowledge_reader = KnowledgeReader()
        self._language_rules = LanguageRules()
        self._sentence_analyzer = SentenceAnalyzer()
        self._intent_extractor = IntentExtractor()
        self._intent_mapper = IntentMapper()
        self._ambiguity_detector = AmbiguityDetector()
        self._context_awareness = ContextAwareness()
        self._confidence_calculator = ConfidenceCalculator()
        self._quality_gate = QualityGate()
        self._assembler = ReportAssembler()

    # ----------------------------------------------------------------- #
    # Main entry point
    # ----------------------------------------------------------------- #

    def execute(self, context: GenerationContext) -> StageResult:
        """Build the Semantic Understanding Report and produce the
        report artefact.

        Steps:
            1. Read the five data sources.
            2. Load the language rules.
            3. Perform the full sentence analysis.
            4. Extract the true intent.
            5. Map all variations to the unified intent.
            6. Detect ambiguities and create clarification requests.
            7. Understand the relationships between the parts.
            8. Calculate the confidence score.
            9. Build the provenance.
            10. Assemble the final report.
            11. Validate quality (quality gate).
            12. Store the report in the generation context.
        """
        gen_start = time.perf_counter()

        # Step 1: read the five data sources.
        request = self._request_reader.read(context)
        requirement_report = self._requirement_report_reader.read(context)
        context_data = self._context_reader.read(context)
        knowledge_data = self._knowledge_reader.read(context)

        # Step 2: load the language rules (the fifth data source).
        language_rules = self._language_rules.load(knowledge_data)

        self._log.info(
            "Starting semantic understanding",
            {
                "request_available": request.available,
                "requirement_report_available":
                    requirement_report.available,
                "context_available": context_data.available,
                "knowledge_available": knowledge_data.available,
                "language_rules_available": language_rules.available,
            },
        )

        # If no request data at all, we cannot proceed.
        if not request.available:
            report = self._build_empty_report(
                request, requirement_report, context_data,
                knowledge_data, language_rules,
            )
            context.set("semantic_understanding_report", report)
            return self.failed(
                errors=[
                    "No user request data available. The Semantic "
                    "Understanding Engine requires at least the "
                    "user's request to proceed."
                ],
                outputs={"semantic_understanding_report": report},
            )

        # Step 3: perform the full sentence analysis.
        raw_request = request.cleaned_request or request.raw_request
        sentence_analyses = self._sentence_analyzer.analyze(
            text=raw_request,
            synonyms=language_rules.synonyms,
            abbreviations=language_rules.abbreviations,
            dialect_map=language_rules.dialect_map,
            spelling_corrections=language_rules.spelling_corrections,
            stop_words=language_rules.stop_words,
        )
        self._log.info(
            "Sentence analysis complete",
            {
                "sentence_count": len(sentence_analyses),
            },
        )

        # Detect the language and style from the first sentence
        # analysis (or from the raw request).
        if sentence_analyses:
            language = sentence_analyses[0].language
            style = sentence_analyses[0].style
        else:
            language = "english"
            style = "formal"

        # Build the normalized request.
        normalized_request = " ".join(
            sa.normalized_text for sa in sentence_analyses
        ).strip()

        # Step 4: extract the true intent.
        intent = self._intent_extractor.extract(
            sentence_analyses=sentence_analyses,
            intent_keywords=language_rules.intent_keywords,
            requirement_report=requirement_report,
            request_data=request,
        )
        self._log.info(
            "Intent extraction complete",
            {
                "kind": intent.kind,
                "has_description": bool(intent.full_description),
                "confidence": intent.confidence,
            },
        )

        # Step 5: map all variations to the unified intent.
        important_keywords = self._intent_mapper.map(
            intent=intent,
            sentence_analyses=sentence_analyses,
            synonyms=language_rules.synonyms,
        )
        self._log.info(
            "Intent mapping complete",
            {
                "mapped_from_variations": intent.mapped_from_variations,
                "keyword_count": len(important_keywords),
            },
        )

        # Step 6: detect ambiguities and create clarification
        # requests.
        ambiguities, clarifications = self._ambiguity_detector.detect(
            intent=intent,
            sentence_analyses=sentence_analyses,
            requirement_report=requirement_report,
            request_data=request,
        )
        self._log.info(
            "Ambiguity detection complete",
            {
                "ambiguities": len(ambiguities),
                "clarifications": len(clarifications),
            },
        )

        # Step 7: understand the relationships between the parts.
        relationships = self._context_awareness.analyze(
            sentence_analyses=sentence_analyses,
            intent=intent,
            requirement_report=requirement_report,
        )
        self._log.info(
            "Context awareness complete",
            {
                "relationships": len(relationships),
            },
        )

        # Step 8: build the provenance.
        provenance = self._assembler.build_provenance(
            request=request,
            requirement_report=requirement_report,
            context_data=context_data,
            knowledge_data=knowledge_data,
            language_rules=language_rules,
            language=language,
            style=style,
            normalized_request=normalized_request,
        )

        # Step 9: calculate the confidence score.
        confidence = self._confidence_calculator.calculate(
            intent=intent,
            keywords=important_keywords,
            ambiguities=ambiguities,
            clarifications=clarifications,
            relationships=relationships,
            sentence_analyses=sentence_analyses,
            provenance=provenance,
            language=language,
            style=style,
        )
        confidence_level = self._confidence_calculator.classify(
            confidence,
        )
        self._log.info(
            "Confidence calculated",
            {
                "confidence": confidence,
                "confidence_level": confidence_level,
            },
        )

        # Step 10: assemble the final report.
        report = self._assembler.assemble(
            intent=intent,
            confidence=confidence,
            confidence_level=confidence_level,
            important_keywords=important_keywords,
            ambiguities=ambiguities,
            clarifications=clarifications,
            relationships=relationships,
            sentence_analyses=sentence_analyses,
            findings=[],
            language=language,
            style=style,
            normalized_request=normalized_request,
            original_request=raw_request,
        )

        # Set the provenance on the report.
        report.provenance = provenance

        # Build the notes.
        report.notes = self._assembler.build_notes(
            report=report,
            request=request,
            context_data=context_data,
            requirement_report=requirement_report,
            knowledge_data=knowledge_data,
            language_rules=language_rules,
        )

        # Step 11: validate quality (quality gate).
        quality_findings, passed = self._quality_gate.validate(report)

        # Rebuild the summary and warnings after quality validation.
        report.warnings = self._assembler.collect_warnings(report)

        self._log.info(
            "Quality validation complete",
            {
                "quality_findings": len(quality_findings),
                "passed": passed,
            },
        )

        # Step 12: store the report in the generation context.
        context.set("semantic_understanding_report", report)
        context.metadata["semantic_understanding"] = report

        total_duration_ms = (time.perf_counter() - gen_start) * 1000

        self._log.info(
            "Semantic understanding complete",
            {
                "intent_kind": report.intent.kind,
                "keyword_count": report.keyword_count,
                "ambiguity_count": report.ambiguity_count,
                "relationship_count": report.relationship_count,
                "sentence_count": report.sentence_count,
                "clarification_count": report.clarification_count,
                "error_count": report.error_count,
                "warning_count": report.warning_count,
                "confidence": report.confidence,
                "confidence_level": report.confidence_level,
                "ready": report.ready,
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
                outputs={"semantic_understanding_report": report},
                warnings=report.warnings,
            )

        return self.ok(
            outputs={"semantic_understanding_report": report},
            metadata={
                "intent_kind": report.intent.kind,
                "keyword_count": report.keyword_count,
                "ambiguity_count": report.ambiguity_count,
                "relationship_count": report.relationship_count,
                "sentence_count": report.sentence_count,
                "clarification_count": report.clarification_count,
                "error_count": report.error_count,
                "warning_count": report.warning_count,
                "confidence": report.confidence,
                "confidence_level": report.confidence_level,
                "ready": report.ready,
                "duration_ms": round(total_duration_ms, 2),
            },
        )

    # ----------------------------------------------------------------- #
    # Helpers
    # ----------------------------------------------------------------- #

    def _build_empty_report(
        self,
        request: RequestData,
        requirement_report: RequirementReportData,
        context_data: ContextData,
        knowledge_data: KnowledgeData,
        language_rules: LanguageRulesData,
    ) -> SemanticUnderstandingReport:
        """Build an empty report when no request data is available."""
        provenance = self._assembler.build_provenance(
            request=request,
            requirement_report=requirement_report,
            context_data=context_data,
            knowledge_data=knowledge_data,
            language_rules=language_rules,
            language="english",
            style="formal",
            normalized_request="",
        )
        report = SemanticUnderstandingReport(
            provenance=provenance,
        )
        report.add_finding(
            severity=SEVERITY_ERROR,
            code="no_request_data",
            message=(
                "No user request data was available for the "
                "Semantic Understanding Engine to process."
            ),
            affected="request",
            resolution_hint=(
                "Provide a user request for the engine to understand."
            ),
            category="quality",
        )
        report.summary = self._assembler._build_summary(report)
        report.notes = self._assembler.build_notes(
            report=report,
            request=request,
            context_data=context_data,
            requirement_report=requirement_report,
            knowledge_data=knowledge_data,
            language_rules=language_rules,
        )
        report.warnings = self._assembler.collect_warnings(report)
        return report


__all__ = ["SemanticUnderstandingEngine"]
