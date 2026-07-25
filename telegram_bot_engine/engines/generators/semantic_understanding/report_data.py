"""
Semantic Understanding Report data model (Specification 013).

This module defines the :class:`SemanticUnderstandingReport` — the
complete, authoritative output of the
:class:`~telegram_bot_engine.engines.generators.semantic_understanding.SemanticUnderstandingEngine`.

The Semantic Understanding Engine is the engine responsible for
understanding the *true meaning* of the user's request.  It does not
rely on keywords alone — it relies on understanding the **intent**,
the **context**, and the **meaning**.

Data sources
-------------
The engine reads **five** data sources:

1. **User Request** — the raw user message (via the
   ``analysis_report`` artefact produced by the
   :class:`~telegram_bot_engine.engines.generators.analyzer.AnalyzerEngine`,
   or the raw ``context.request``).
2. **Requirement Intelligence Report** — the
   ``requirement_intelligence_report`` artefact produced by the
   :class:`~telegram_bot_engine.engines.generators.requirement_intelligence.RequirementIntelligenceEngine`.
3. **Project Context** — the ``project_context`` artefact produced by
   the
   :class:`~telegram_bot_engine.engines.generators.project_context.ProjectContextEngine`.
4. **Knowledge Base** — the ``knowledge_base`` artefact, if present
   (a free-form dictionary of pre-approved assumptions and domain
   knowledge).
5. **Language Rules** — the built-in language rules that the engine
   uses to understand Arabic, English, slang, formal, abbreviations,
   spelling mistakes, and mixed languages.

Design principles
-----------------
* **Meaning, not keywords.**  The engine does not rely on keyword
  matching alone.  It understands the intent, the context, and the
  meaning of the request.
* **Same request, many ways.**  The engine must understand the same
  request even if it is written in tens or hundreds of different ways.
  All variations are mapped to a single unified Intent.
* **Intent mapping.**  All the different forms of the request are
  converted to a unified Intent so that all engines work on the same
  understanding.
* **No guessing.**  When a request is ambiguous (it admits more than
  one interpretation), the engine detects the ambiguity and requests
  clarification.  It does not guess.
* **Context awareness.**  The engine understands the relationship
  between the parts of the request.  It does not process each
  sentence separately.
* **Scalability.**  The engine is designed to handle simple requests,
  professional requests, very large requests, and projects with
  hundreds of requirements.
* **Quality gate.**  The engine does not allow any request to pass
  unless it is understood with sufficient confidence.
* **Traceability.**  Every understanding records the data source it
  was derived from (``source_artefact``) so any downstream decision
  can trace its data back to the original source.

The report is a plain data container — no logic lives here.  The
engine and its helpers populate it; downstream consumers read it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------#
# Source-artefact constants
# ---------------------------------------------------------------------------#
#
# Every understanding records the data source it was derived from.  These
# constants are the stable identifiers for the five data sources.

SOURCE_USER_REQUEST = "user_request"
SOURCE_REQUIREMENT_INTELLIGENCE = "requirement_intelligence"
SOURCE_PROJECT_CONTEXT = "project_context"
SOURCE_KNOWLEDGE_BASE = "knowledge_base"
SOURCE_LANGUAGE_RULES = "language_rules"

ALL_SOURCES = (
    SOURCE_USER_REQUEST,
    SOURCE_REQUIREMENT_INTELLIGENCE,
    SOURCE_PROJECT_CONTEXT,
    SOURCE_KNOWLEDGE_BASE,
    SOURCE_LANGUAGE_RULES,
)


# ---------------------------------------------------------------------------#
# Severity constants
# ---------------------------------------------------------------------------#

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"

ALL_SEVERITIES = (SEVERITY_ERROR, SEVERITY_WARNING, SEVERITY_INFO)


# ---------------------------------------------------------------------------#
# Language constants
# ---------------------------------------------------------------------------#
#
# The languages the engine understands.

LANGUAGE_ARABIC = "arabic"
LANGUAGE_ENGLISH = "english"
LANGUAGE_MIXED = "mixed"

ALL_LANGUAGES = (LANGUAGE_ARABIC, LANGUAGE_ENGLISH, LANGUAGE_MIXED)


# ---------------------------------------------------------------------------#
# Language style constants
# ---------------------------------------------------------------------------#
#
# The style of the language the user used.

STYLE_FORMAL = "formal"
STYLE_COLLOQUIAL = "colloquial"
STYLE_SLANG = "slang"
STYLE_MIXED = "mixed"

ALL_STYLES = (STYLE_FORMAL, STYLE_COLLOQUIAL, STYLE_SLANG, STYLE_MIXED)


# ---------------------------------------------------------------------------#
# Intent kind constants
# ---------------------------------------------------------------------------#
#
# The kind of intent the user is expressing.

INTENT_KIND_CREATE = "create"
INTENT_KIND_MODIFY = "modify"
INTENT_KIND_DELETE = "delete"
INTENT_KIND_QUERY = "query"
INTENT_KIND_CONFIGURE = "configure"
INTENT_KIND_DEPLOY = "deploy"
INTENT_KIND_UNKNOWN = "unknown"

ALL_INTENT_KINDS = (
    INTENT_KIND_CREATE,
    INTENT_KIND_MODIFY,
    INTENT_KIND_DELETE,
    INTENT_KIND_QUERY,
    INTENT_KIND_CONFIGURE,
    INTENT_KIND_DEPLOY,
    INTENT_KIND_UNKNOWN,
)


# ---------------------------------------------------------------------------#
# Ambiguity kind constants
# ---------------------------------------------------------------------------#

AMBIGUITY_VAGUE = "vague"
AMBIGUITY_MULTIPLE_INTERPRETATIONS = "multiple_interpretations"
AMBIGUITY_MISSING_CONTEXT = "missing_context"
AMBIGUITY_UNDER_SPECIFIED = "under_specified"

ALL_AMBIGUITY_KINDS = (
    AMBIGUITY_VAGUE,
    AMBIGUITY_MULTIPLE_INTERPRETATIONS,
    AMBIGUITY_MISSING_CONTEXT,
    AMBIGUITY_UNDER_SPECIFIED,
)


# ---------------------------------------------------------------------------#
# Confidence level constants
# ---------------------------------------------------------------------------#
#
# The confidence levels the engine assigns to its understanding.

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"

ALL_CONFIDENCE_LEVELS = (CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW)

# Numeric confidence thresholds.
CONFIDENCE_HIGH_THRESHOLD = 0.8
CONFIDENCE_MEDIUM_THRESHOLD = 0.6


# ---------------------------------------------------------------------------#
# Clarification kind constants
# ---------------------------------------------------------------------------#
#
# The kind of clarification the engine requests when the request is
# ambiguous.

CLARIFICATION_DISAMBIGUATE = "disambiguate"
CLARIFICATION_PROVIDE_CONTEXT = "provide_context"
CLARIFICATION_SPECIFY = "specify"

ALL_CLARIFICATION_KINDS = (
    CLARIFICATION_DISAMBIGUATE,
    CLARIFICATION_PROVIDE_CONTEXT,
    CLARIFICATION_SPECIFY,
)


# ---------------------------------------------------------------------------#
# Sentence analysis
# ---------------------------------------------------------------------------#

@dataclass
class SentenceAnalysis:
    """The analysis of a single sentence in the user's request.

    The Semantic Understanding Engine analyses each sentence in the
    request.  This data class holds the result of that analysis.

    Attributes:
        raw_text: The original, unmodified sentence text.
        normalized_text: The sentence after normalization (dialect,
            spelling, abbreviation, and synonym resolution).
        language: The detected language (one of the ``LANGUAGE_*``
            constants).
        style: The detected language style (one of the
            ``STYLE_*`` constants).
        keywords: The important keywords extracted from the
            sentence.
        resolved_synonyms: A mapping of original word → resolved
            synonym (the canonical form).
        spelling_corrections: A mapping of misspelled word →
            corrected word.
        expanded_abbreviations: A mapping of abbreviation →
            expanded form.
        confidence: 0.0–1.0 confidence in the sentence analysis.
        source_artefact: The artefact this analysis was derived
            from.
    """

    raw_text: str = ""
    normalized_text: str = ""
    language: str = LANGUAGE_ENGLISH
    style: str = STYLE_FORMAL
    keywords: List[str] = field(default_factory=list)
    resolved_synonyms: Dict[str, str] = field(default_factory=dict)
    spelling_corrections: Dict[str, str] = field(default_factory=dict)
    expanded_abbreviations: Dict[str, str] = field(default_factory=dict)
    confidence: float = 1.0
    source_artefact: str = SOURCE_USER_REQUEST

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "normalized_text": self.normalized_text,
            "language": self.language,
            "style": self.style,
            "keywords": list(self.keywords),
            "resolved_synonyms": dict(self.resolved_synonyms),
            "spelling_corrections": dict(self.spelling_corrections),
            "expanded_abbreviations": dict(self.expanded_abbreviations),
            "confidence": self.confidence,
            "source_artefact": self.source_artefact,
        }


# ---------------------------------------------------------------------------#
# Unified intent
# ---------------------------------------------------------------------------#

@dataclass
class UnifiedIntent:
    """The unified intent — the single, canonical understanding of the
    user's request.

    All the different ways the user could write the same request are
    mapped to a single :class:`UnifiedIntent`.  This is the object that
    all downstream engines work on.

    Attributes:
        id: A unique, machine-readable identifier (e.g.
            ``"INTENT-001"``).
        kind: The kind of intent (one of the ``INTENT_KIND_*``
            constants).
        primary_action: The primary action the user wants (e.g.
            ``"create a telegram bot"``).
        subject: The subject of the action (e.g. ``"telegram bot"``,
            ``"store bot"``).
        target: The target of the action, if any (e.g.
            ``"ecommerce"``, ``"store"``).
        features: The features the user wants.
        constraints: The constraints the user specified.
        full_description: A full, natural-language description of
            the understood intent.
        confidence: 0.0–1.0 confidence that the intent was
            correctly understood.
        evidence: The evidence (keywords, phrases, artefact
            references) that led to this intent.
        source_artefact: The artefact this intent was derived
            from.
        mapped_from_variations: The number of different request
            variations that were mapped to this intent.
    """

    id: str = "INTENT-001"
    kind: str = INTENT_KIND_CREATE
    primary_action: str = ""
    subject: str = ""
    target: str = ""
    features: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    full_description: str = ""
    confidence: float = 1.0
    evidence: List[str] = field(default_factory=list)
    source_artefact: str = SOURCE_USER_REQUEST
    mapped_from_variations: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "primary_action": self.primary_action,
            "subject": self.subject,
            "target": self.target,
            "features": list(self.features),
            "constraints": list(self.constraints),
            "full_description": self.full_description,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "source_artefact": self.source_artefact,
            "mapped_from_variations": self.mapped_from_variations,
        }


# ---------------------------------------------------------------------------#
# Ambiguity point
# ---------------------------------------------------------------------------#

@dataclass
class SemanticAmbiguity:
    """A point of ambiguity detected in the user's request.

    When the request admits more than one interpretation, the engine
    detects the ambiguity and records it here.  The engine does not
    guess — it requests clarification.

    Attributes:
        id: A unique, machine-readable identifier (e.g.
            ``"AMB-001"``).
        kind: The ambiguity kind (one of the ``AMBIGUITY_*``
            constants).
        description: A human-readable description of the
            ambiguity.
        affected_text: The text in the user's request that is
            ambiguous.
        possible_interpretations: The possible interpretations
            of the ambiguous text.
        resolution_hint: An optional suggestion on how to resolve
            the ambiguity.
        source_artefact: The artefact this ambiguity was derived
            from.
    """

    id: str = ""
    kind: str = AMBIGUITY_VAGUE
    description: str = ""
    affected_text: str = ""
    possible_interpretations: List[str] = field(default_factory=list)
    resolution_hint: str = ""
    source_artefact: str = SOURCE_USER_REQUEST

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "description": self.description,
            "affected_text": self.affected_text,
            "possible_interpretations": list(self.possible_interpretations),
            "resolution_hint": self.resolution_hint,
            "source_artefact": self.source_artefact,
        }


# ---------------------------------------------------------------------------#
# Clarification request
# ---------------------------------------------------------------------------#

@dataclass
class ClarificationRequest:
    """A clarification the engine requests from the user.

    When the engine detects ambiguity, it does not guess.  Instead it
    records a :class:`ClarificationRequest` so the caller can ask the
    user for clarification.

    Attributes:
        id: A unique, machine-readable identifier (e.g.
            ``"CLAR-001"``).
        kind: The clarification kind (one of the
            ``CLARIFICATION_*`` constants).
        question: The question to ask the user.
        options: Suggested options for the answer.
        related_ambiguity_id: The ID of the ambiguity this
            clarification resolves.
        required: Whether this clarification must be answered to
            proceed.
        source_artefact: The artefact this clarification was
            derived from.
    """

    id: str = ""
    kind: str = CLARIFICATION_DISAMBIGUATE
    question: str = ""
    options: List[str] = field(default_factory=list)
    related_ambiguity_id: str = ""
    required: bool = True
    source_artefact: str = SOURCE_USER_REQUEST

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "question": self.question,
            "options": list(self.options),
            "related_ambiguity_id": self.related_ambiguity_id,
            "required": self.required,
            "source_artefact": self.source_artefact,
        }


# ---------------------------------------------------------------------------#
# Requirement relationship
# ---------------------------------------------------------------------------#

@dataclass
class RequirementRelationship:
    """A relationship between two requirements or parts of the
    request.

    The engine understands the relationship between the parts of the
    request.  It does not process each sentence separately.  This
    data class records the relationships it detected.

    Attributes:
        id: A unique, machine-readable identifier (e.g.
            ``"REL-001"``).
        kind: The relationship kind (e.g. ``"depends_on"``,
            ``"part_of"``, ``"contradicts"``, ``"extends"``).
        from_entity: The entity the relationship starts from.
        to_entity: The entity the relationship points to.
        description: A human-readable description of the
            relationship.
        confidence: 0.0–1.0 confidence in the relationship.
        source_artefact: The artefact this relationship was
            derived from.
    """

    id: str = ""
    kind: str = "depends_on"
    from_entity: str = ""
    to_entity: str = ""
    description: str = ""
    confidence: float = 1.0
    source_artefact: str = SOURCE_USER_REQUEST

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "from_entity": self.from_entity,
            "to_entity": self.to_entity,
            "description": self.description,
            "confidence": self.confidence,
            "source_artefact": self.source_artefact,
        }


# ---------------------------------------------------------------------------#
# Important keyword
# ---------------------------------------------------------------------------#

@dataclass
class ImportantKeyword:
    """An important keyword extracted from the user's request.

    The engine extracts the important keywords from the request.  These
    are the keywords that carry the meaning of the request.

    Attributes:
        word: The keyword.
        weight: 0.0–1.0 importance weight.
        normalized_form: The canonical form of the keyword (after
            synonym, spelling, and abbreviation resolution).
        original_forms: The different forms the keyword appeared in
            (the variations that were mapped to this keyword).
        source_artefact: The artefact this keyword was derived
            from.
    """

    word: str = ""
    weight: float = 1.0
    normalized_form: str = ""
    original_forms: List[str] = field(default_factory=list)
    source_artefact: str = SOURCE_USER_REQUEST

    def to_dict(self) -> Dict[str, Any]:
        return {
            "word": self.word,
            "weight": self.weight,
            "normalized_form": self.normalized_form,
            "original_forms": list(self.original_forms),
            "source_artefact": self.source_artefact,
        }


# ---------------------------------------------------------------------------#
# Report finding
# ---------------------------------------------------------------------------#

@dataclass
class SemanticFinding:
    """A general finding produced during semantic understanding.

    Attributes:
        severity: ``"error"``, ``"warning"``, or ``"info"``.
        code: A short, machine-readable code (e.g.
            ``"low_confidence"``).
        message: A human-readable description.
        affected: The name of the affected element.
        resolution_hint: An optional suggestion on how to fix
            the issue.
        category: The finding category (``"intent"``,
            ``"ambiguity"``, ``"confidence"``, ``"quality"``).
    """

    severity: str = SEVERITY_WARNING
    code: str = ""
    message: str = ""
    affected: str = ""
    resolution_hint: str = ""
    category: str = "validation"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "affected": self.affected,
            "resolution_hint": self.resolution_hint,
            "category": self.category,
        }


# ---------------------------------------------------------------------------#
# Source provenance
# ---------------------------------------------------------------------------#

@dataclass
class SemanticProvenance:
    """Records which data sources were used to build the report.

    Attributes:
        request_available: Whether the user request was available.
        requirement_intelligence_available: Whether the
            requirement intelligence report was available.
        project_context_available: Whether the project context
            was available.
        knowledge_base_available: Whether the knowledge base was
            available.
        language_rules_available: Whether language rules were
            available (always True — they are built-in).
        all_sources_used: The list of all source artefact
            identifiers that contributed to the report.
        request_summary: A short summary of the user request.
        request_language: The detected language of the request.
        request_style: The detected style of the request.
        requirement_count_from_intelligence: The number of
            requirements from the requirement intelligence report.
    """

    request_available: bool = False
    requirement_intelligence_available: bool = False
    project_context_available: bool = False
    knowledge_base_available: bool = False
    language_rules_available: bool = True
    all_sources_used: List[str] = field(default_factory=list)
    request_summary: str = ""
    request_language: str = LANGUAGE_ENGLISH
    request_style: str = STYLE_FORMAL
    requirement_count_from_intelligence: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_available": self.request_available,
            "requirement_intelligence_available":
                self.requirement_intelligence_available,
            "project_context_available": self.project_context_available,
            "knowledge_base_available": self.knowledge_base_available,
            "language_rules_available": self.language_rules_available,
            "all_sources_used": list(self.all_sources_used),
            "request_summary": self.request_summary,
            "request_language": self.request_language,
            "request_style": self.request_style,
            "requirement_count_from_intelligence":
                self.requirement_count_from_intelligence,
        }


# ---------------------------------------------------------------------------#
# The full Semantic Understanding Report
# ---------------------------------------------------------------------------#

@dataclass
class SemanticUnderstandingReport:
    """The complete, authoritative output of the Semantic Understanding
    Engine.

    This is the **only** object the engine produces.  It is stored in
    the generation context as the ``semantic_understanding_report``
    artefact.

    The report contains:
    * The unified Intent (the final, canonical understanding).
    * The confidence score (0.0–1.0).
    * The important keywords.
    * The ambiguity points.
    * The relationships between requirements.
    * The sentence analyses.
    * The clarification requests.
    * The findings.
    * The provenance (traceability).

    Attributes:
        intent: The :class:`UnifiedIntent` — the final, canonical
            understanding of the user's request.
        confidence: 0.0–1.0 confidence that the intent was
            correctly understood.
        confidence_level: The confidence level (one of the
            ``CONFIDENCE_*`` constants).
        important_keywords: The list of :class:`ImportantKeyword`
            objects.
        ambiguities: The list of :class:`SemanticAmbiguity`
            objects (points of ambiguity).
        relationships: The list of :class:`RequirementRelationship`
            objects (relationships between requirements).
        sentence_analyses: The list of :class:`SentenceAnalysis`
            objects (one per sentence in the request).
        clarifications: The list of :class:`ClarificationRequest`
            objects (clarifications the engine requests).
        findings: The list of :class:`SemanticFinding` objects.
        provenance: The :class:`SemanticProvenance` —
            traceability record.
        summary: A human-readable summary.
        notes: General notes about the report.
        warnings: Warnings produced during report building.
        language: The detected language of the request.
        style: The detected style of the request.
        normalized_request: The fully normalized request (after
            all language processing).
        original_request: The original, unmodified request.
    """

    intent: UnifiedIntent = field(default_factory=UnifiedIntent)
    confidence: float = 0.0
    confidence_level: str = CONFIDENCE_LOW
    important_keywords: List[ImportantKeyword] = field(default_factory=list)
    ambiguities: List[SemanticAmbiguity] = field(default_factory=list)
    relationships: List[RequirementRelationship] = field(default_factory=list)
    sentence_analyses: List[SentenceAnalysis] = field(default_factory=list)
    clarifications: List[ClarificationRequest] = field(default_factory=list)
    findings: List[SemanticFinding] = field(default_factory=list)
    provenance: SemanticProvenance = field(default_factory=SemanticProvenance)
    summary: str = ""
    notes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    language: str = LANGUAGE_ENGLISH
    style: str = STYLE_FORMAL
    normalized_request: str = ""
    original_request: str = ""

    # -- convenience -------------------------------------------------------#

    @property
    def keyword_count(self) -> int:
        return len(self.important_keywords)

    @property
    def ambiguity_count(self) -> int:
        return len(self.ambiguities)

    @property
    def relationship_count(self) -> int:
        return len(self.relationships)

    @property
    def sentence_count(self) -> int:
        return len(self.sentence_analyses)

    @property
    def clarification_count(self) -> int:
        return len(self.clarifications)

    @property
    def finding_count(self) -> int:
        return len(self.findings)

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == SEVERITY_ERROR)

    @property
    def warning_count(self) -> int:
        return sum(
            1 for f in self.findings if f.severity == SEVERITY_WARNING
        )

    @property
    def has_ambiguity(self) -> bool:
        return self.ambiguity_count > 0

    @property
    def has_unresolved_clarifications(self) -> bool:
        return self.clarification_count > 0

    @property
    def is_empty(self) -> bool:
        return not self.intent.full_description

    @property
    def has_errors(self) -> bool:
        return self.error_count > 0

    @property
    def has_sufficient_confidence(self) -> bool:
        """``True`` when the confidence is above the medium threshold."""
        return self.confidence >= CONFIDENCE_MEDIUM_THRESHOLD

    @property
    def ready(self) -> bool:
        """``True`` when the report is complete enough to proceed.

        The report is ready when:
        * The intent has a full description.
        * The confidence is at or above the medium threshold.
        * There are no error-level findings.
        * There are no unresolved required clarifications.
        """
        return (
            bool(self.intent.full_description)
            and self.has_sufficient_confidence
            and not self.has_errors
            and not any(c.required for c in self.clarifications)
        )

    # -- look-up helpers --------------------------------------------------#

    def get_keyword(self, word: str) -> Optional[ImportantKeyword]:
        """Return the keyword with the given word, or ``None``."""
        for kw in self.important_keywords:
            if kw.word == word or kw.normalized_form == word:
                return kw
        return None

    def keywords_sorted_by_weight(self) -> List[ImportantKeyword]:
        """Return all keywords sorted by weight (descending)."""
        return sorted(
            self.important_keywords, key=lambda k: -k.weight,
        )

    def top_keywords(self, n: int = 10) -> List[ImportantKeyword]:
        """Return the top-n keywords by weight."""
        return self.keywords_sorted_by_weight()[:n]

    # -- finding management -----------------------------------------------#

    def add_finding(
        self,
        severity: str,
        code: str,
        message: str,
        affected: str = "",
        resolution_hint: str = "",
        category: str = "validation",
    ) -> None:
        """Add a finding to the report."""
        self.findings.append(SemanticFinding(
            severity=severity,
            code=code,
            message=message,
            affected=affected,
            resolution_hint=resolution_hint,
            category=category,
        ))
        if severity == SEVERITY_WARNING:
            self.warnings.append(message)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent.to_dict(),
            "confidence": self.confidence,
            "confidence_level": self.confidence_level,
            "keyword_count": self.keyword_count,
            "ambiguity_count": self.ambiguity_count,
            "relationship_count": self.relationship_count,
            "sentence_count": self.sentence_count,
            "clarification_count": self.clarification_count,
            "finding_count": self.finding_count,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "has_ambiguity": self.has_ambiguity,
            "has_unresolved_clarifications":
                self.has_unresolved_clarifications,
            "has_sufficient_confidence": self.has_sufficient_confidence,
            "ready": self.ready,
            "language": self.language,
            "style": self.style,
            "normalized_request": self.normalized_request,
            "original_request": self.original_request,
            "summary": self.summary,
            "notes": list(self.notes),
            "warnings": list(self.warnings),
            "important_keywords": [
                kw.to_dict() for kw in self.important_keywords
            ],
            "ambiguities": [a.to_dict() for a in self.ambiguities],
            "relationships": [r.to_dict() for r in self.relationships],
            "sentence_analyses": [
                sa.to_dict() for sa in self.sentence_analyses
            ],
            "clarifications": [
                c.to_dict() for c in self.clarifications
            ],
            "findings": [f.to_dict() for f in self.findings],
            "provenance": self.provenance.to_dict(),
        }


__all__ = [
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
]
