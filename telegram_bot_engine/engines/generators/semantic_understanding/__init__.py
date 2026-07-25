"""
Semantic Understanding Engine package (Specification 013).

This package contains the semantic understanding engine — the engine
that understands the **true meaning** of the user's request.  It does
not rely on keywords alone — it relies on understanding the intent,
the context, and the meaning.  The engine does **not** write code,
create files, choose libraries, or make build decisions.  Its sole
function is to produce the *Semantic Understanding Report* — a
structured, validated report that captures the unified intent, the
confidence, the keywords, the ambiguities, the clarifications, and the
relationships between the parts of the request.

Public surface
--------------
* :class:`SemanticUnderstandingEngine` — the engine itself.
* :class:`SemanticUnderstandingReport` and all of its sub-dataclasses
  (:class:`UnifiedIntent`, :class:`SentenceAnalysis`,
  :class:`SemanticAmbiguity`, :class:`ClarificationRequest`,
  :class:`RequirementRelationship`, :class:`ImportantKeyword`,
  :class:`SemanticFinding`, :class:`SemanticProvenance`).
* :class:`RequestReader`, :class:`RequirementReportReader`,
  :class:`ContextReader`, :class:`KnowledgeReader` — the four
  data-source readers.
* :class:`LanguageRules`, :class:`LanguageRulesData` — the
  built-in language rules loader and data container.
* :class:`SentenceAnalyzer` — the full sentence analysis helper.
* :class:`IntentExtractor` — the intent extraction helper.
* :class:`IntentMapper` — the intent mapping helper.
* :class:`AmbiguityDetector` — the ambiguity detection helper.
* :class:`ContextAwareness` — the context awareness helper.
* :class:`ConfidenceCalculator` — the confidence calculation helper.
* :class:`QualityGate` — the quality gate.
* :class:`ReportAssembler` — the final-report assembler.
* :class:`RequestData`, :class:`RequirementReportData`,
  :class:`ContextData`, :class:`KnowledgeData` — the intermediate
  data containers produced by the readers.
* Source-artefact, severity, language, style, intent-kind,
  ambiguity-kind, confidence-level, and clarification-kind
  constants.
"""

from __future__ import annotations

from .semantic_understanding_engine import SemanticUnderstandingEngine
from .report_data import (
    # Data model
    SentenceAnalysis,
    UnifiedIntent,
    SemanticAmbiguity,
    ClarificationRequest,
    RequirementRelationship,
    ImportantKeyword,
    SemanticFinding,
    SemanticProvenance,
    SemanticUnderstandingReport,
    # Source-artefact constants
    SOURCE_USER_REQUEST,
    SOURCE_REQUIREMENT_INTELLIGENCE,
    SOURCE_PROJECT_CONTEXT,
    SOURCE_KNOWLEDGE_BASE,
    SOURCE_LANGUAGE_RULES,
    ALL_SOURCES,
    # Severity constants
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    SEVERITY_INFO,
    ALL_SEVERITIES,
    # Language constants
    LANGUAGE_ARABIC,
    LANGUAGE_ENGLISH,
    LANGUAGE_MIXED,
    ALL_LANGUAGES,
    # Style constants
    STYLE_FORMAL,
    STYLE_COLLOQUIAL,
    STYLE_SLANG,
    STYLE_MIXED,
    ALL_STYLES,
    # Intent kind constants
    INTENT_KIND_CREATE,
    INTENT_KIND_MODIFY,
    INTENT_KIND_DELETE,
    INTENT_KIND_QUERY,
    INTENT_KIND_CONFIGURE,
    INTENT_KIND_DEPLOY,
    INTENT_KIND_UNKNOWN,
    ALL_INTENT_KINDS,
    # Ambiguity kind constants
    AMBIGUITY_VAGUE,
    AMBIGUITY_MULTIPLE_INTERPRETATIONS,
    AMBIGUITY_MISSING_CONTEXT,
    AMBIGUITY_UNDER_SPECIFIED,
    ALL_AMBIGUITY_KINDS,
    # Confidence level constants
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_LOW,
    ALL_CONFIDENCE_LEVELS,
    CONFIDENCE_HIGH_THRESHOLD,
    CONFIDENCE_MEDIUM_THRESHOLD,
    # Clarification kind constants
    CLARIFICATION_DISAMBIGUATE,
    CLARIFICATION_PROVIDE_CONTEXT,
    CLARIFICATION_SPECIFY,
    ALL_CLARIFICATION_KINDS,
)
from .request_reader import RequestReader, RequestData
from .requirement_report_reader import (
    RequirementReportReader,
    RequirementReportData,
)
from .context_reader import ContextReader, ContextData
from .knowledge_reader import KnowledgeReader, KnowledgeData
from .language_rules import (
    LanguageRules,
    LanguageRulesData,
    detect_language,
    detect_style,
    normalize_arabic_text,
)
from .sentence_analyzer import SentenceAnalyzer
from .intent_extractor import IntentExtractor
from .intent_mapper import IntentMapper
from .ambiguity_detector import AmbiguityDetector
from .context_awareness import ContextAwareness
from .confidence_calculator import ConfidenceCalculator
from .quality_gate import QualityGate
from .report_assembler import ReportAssembler

__all__ = [
    # Engine
    "SemanticUnderstandingEngine",
    # Data model
    "SentenceAnalysis",
    "UnifiedIntent",
    "SemanticAmbiguity",
    "ClarificationRequest",
    "RequirementRelationship",
    "ImportantKeyword",
    "SemanticFinding",
    "SemanticProvenance",
    "SemanticUnderstandingReport",
    # Source-artefact constants
    "SOURCE_USER_REQUEST",
    "SOURCE_REQUIREMENT_INTELLIGENCE",
    "SOURCE_PROJECT_CONTEXT",
    "SOURCE_KNOWLEDGE_BASE",
    "SOURCE_LANGUAGE_RULES",
    "ALL_SOURCES",
    # Severity constants
    "SEVERITY_ERROR",
    "SEVERITY_WARNING",
    "SEVERITY_INFO",
    "ALL_SEVERITIES",
    # Language constants
    "LANGUAGE_ARABIC",
    "LANGUAGE_ENGLISH",
    "LANGUAGE_MIXED",
    "ALL_LANGUAGES",
    # Style constants
    "STYLE_FORMAL",
    "STYLE_COLLOQUIAL",
    "STYLE_SLANG",
    "STYLE_MIXED",
    "ALL_STYLES",
    # Intent kind constants
    "INTENT_KIND_CREATE",
    "INTENT_KIND_MODIFY",
    "INTENT_KIND_DELETE",
    "INTENT_KIND_QUERY",
    "INTENT_KIND_CONFIGURE",
    "INTENT_KIND_DEPLOY",
    "INTENT_KIND_UNKNOWN",
    "ALL_INTENT_KINDS",
    # Ambiguity kind constants
    "AMBIGUITY_VAGUE",
    "AMBIGUITY_MULTIPLE_INTERPRETATIONS",
    "AMBIGUITY_MISSING_CONTEXT",
    "AMBIGUITY_UNDER_SPECIFIED",
    "ALL_AMBIGUITY_KINDS",
    # Confidence level constants
    "CONFIDENCE_HIGH",
    "CONFIDENCE_MEDIUM",
    "CONFIDENCE_LOW",
    "ALL_CONFIDENCE_LEVELS",
    "CONFIDENCE_HIGH_THRESHOLD",
    "CONFIDENCE_MEDIUM_THRESHOLD",
    # Clarification kind constants
    "CLARIFICATION_DISAMBIGUATE",
    "CLARIFICATION_PROVIDE_CONTEXT",
    "CLARIFICATION_SPECIFY",
    "ALL_CLARIFICATION_KINDS",
    # Readers + intermediate data
    "RequestReader",
    "RequestData",
    "RequirementReportReader",
    "RequirementReportData",
    "ContextReader",
    "ContextData",
    "KnowledgeReader",
    "KnowledgeData",
    # Language rules
    "LanguageRules",
    "LanguageRulesData",
    "detect_language",
    "detect_style",
    "normalize_arabic_text",
    # Helpers
    "SentenceAnalyzer",
    "IntentExtractor",
    "IntentMapper",
    "AmbiguityDetector",
    "ContextAwareness",
    "ConfidenceCalculator",
    "QualityGate",
    "ReportAssembler",
]
