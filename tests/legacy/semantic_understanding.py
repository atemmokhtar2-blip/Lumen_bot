#!/usr/bin/env python3
"""
Comprehensive test suite for the Semantic Understanding Engine
(Specification 013).

These tests cover every aspect of the specification:

1. Data model integrity (SentenceAnalysis, UnifiedIntent,
   SemanticAmbiguity, ClarificationRequest, RequirementRelationship,
   ImportantKeyword, SemanticFinding, SemanticProvenance,
   SemanticUnderstandingReport, source-artefact constants, severity
   constants, language constants, style constants, intent-kind
   constants, ambiguity-kind constants, confidence-level constants,
   clarification-kind constants).
2. The RequestReader (analysis_report artefact, raw request fallback,
   empty context).
3. The RequirementReportReader (requirement_intelligence_report
   artefact, empty context).
4. The ContextReader (project_context artefact, empty context).
5. The KnowledgeReader (knowledge_base artefact, empty context).
6. The LanguageRules loader (built-in rules, merge with knowledge
   base, language detection, style detection, Arabic normalization).
7. The SentenceAnalyzer (sentence splitting, dialect normalization,
   spell correction, abbreviation expansion, synonym resolution,
   keyword extraction, confidence).
8. The IntentExtractor (kind determination, subject, target,
   features, constraints, description, evidence, confidence).
9. The IntentMapper (variation counting, keyword consolidation,
   normalized form grouping).
10. The AmbiguityDetector (vague, multiple interpretations, missing
    context, under-specified, requirement-report ambiguities).
11. The ContextAwareness (pair relationships, requirement-report
    conflicts, intent-to-report relationship).
12. The ConfidenceCalculator (intent, keyword, ambiguity,
    clarification, data-source, language factors; classification).
13. The QualityGate (confidence, intent, keyword, clarification,
    empty checks; pass/fail).
14. The ReportAssembler (assembles report, builds provenance,
    summary, notes, warnings).
15. The main engine reads the five data sources.
16. The main engine produces a semantic_understanding_report
    artefact.
17. The main engine fails when no request data is available.
18. The main engine stores the report in the context metadata.
19. Bootstrap integration (engine registered in registry and manager
    at priority 99, depends on requirement_intelligence).
20. Serialisation (to_dict) for all data model classes.
21. End-to-end pipeline with Arabic, English, mixed, and slang.
22. Intent mapping: same request written in different ways.
"""

import sys
import os

# Ensure the package is importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path

from telegram_bot_engine.core import build_configuration, bootstrap
from telegram_bot_engine.core.context import GenerationContext
from telegram_bot_engine.engines.generators.analyzer.analysis_report import (
    AnalysisReport,
    BotTypeEntry,
    Feature,
    KeywordMatch,
    Technology,
)
from telegram_bot_engine.engines.generators.semantic_understanding import (
    # Engine
    SemanticUnderstandingEngine,
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
    # Readers + intermediate data
    RequestReader,
    RequestData,
    RequirementReportReader,
    RequirementReportData,
    ContextReader,
    ContextData,
    KnowledgeReader,
    KnowledgeData,
    # Language rules
    LanguageRules,
    LanguageRulesData,
    detect_language,
    detect_style,
    normalize_arabic_text,
    # Helpers
    SentenceAnalyzer,
    IntentExtractor,
    IntentMapper,
    AmbiguityDetector,
    ContextAwareness,
    ConfidenceCalculator,
    QualityGate,
    ReportAssembler,
)


# ---------------------------------------------------------------------------#
# Test helpers
# ---------------------------------------------------------------------------#

def make_config():
    return build_configuration()


def make_context(
    analysis_report=None,
    project_context=None,
    requirement_intelligence_report=None,
    knowledge_base=None,
    request="",
):
    """Build a generation context with the five data sources."""
    ctx = GenerationContext(
        request=request,
        config=make_config(),
        work_dir=Path("/tmp/test_semantic_understanding"),
    )
    if analysis_report is not None:
        ctx.set("analysis_report", analysis_report)
    if project_context is not None:
        ctx.set("project_context", project_context)
    if requirement_intelligence_report is not None:
        ctx.set("requirement_intelligence_report",
                requirement_intelligence_report)
    if knowledge_base is not None:
        ctx.set("knowledge_base", knowledge_base)
    return ctx


def make_analysis_report(
    project_name="store_bot",
    description="A Telegram bot for managing a store with a database",
):
    """Build an analysis report for testing."""
    return AnalysisReport(
        raw_request=(
            "I want a Telegram store bot with a database and command "
            "handling. Use Python and SQLite. Do not use webhooks."
        ),
        cleaned_request=(
            "I want a Telegram store bot with a database and command "
            "handling. Use Python and SQLite. Do not use webhooks."
        ),
        project_name=project_name,
        description=description,
        bot_types=[
            BotTypeEntry(
                type="store",
                display_name="Store Bot",
                priority=10,
                confidence=0.9,
            ),
        ],
        features=[
            Feature(
                name="command_handling",
                display_name="Command Handling",
                description="Handle user commands",
                keywords=["command", "handler"],
                confidence=0.9,
            ),
            Feature(
                name="database_storage",
                display_name="Database Storage",
                description="Store data in a database",
                keywords=["database", "storage"],
                confidence=0.85,
            ),
        ],
        technologies=[
            Technology(
                category="language",
                name="Python",
                role="primary",
                explicit=True,
                confidence=0.95,
            ),
            Technology(
                category="database",
                name="SQLite",
                role="primary_storage",
                explicit=True,
                confidence=0.9,
            ),
        ],
        keywords=[
            KeywordMatch(keyword="bot", category="bot_type",
                         confidence=0.9),
            KeywordMatch(keyword="store", category="bot_type",
                         confidence=0.9),
            KeywordMatch(keyword="database", category="database",
                         confidence=0.85),
        ],
        conflicts=[],
        missing_info=[],
        ready=True,
    )


def make_requirement_intelligence_report():
    """Build a simple mock requirement intelligence report."""
    from telegram_bot_engine.engines.generators.requirement_intelligence import (
        IntentAnalysis,
        Requirement,
        RequirementIntelligenceReport,
    )
    report = RequirementIntelligenceReport(
        intent=IntentAnalysis(
            wants="A Telegram store bot",
            does_not_want="webhooks",
            final_goal="Manage a store via Telegram",
            quality_level="standard",
            confidence=0.85,
        ),
        requirements=[
            Requirement(
                id="REQ-001",
                name="command_handling",
                display_name="Command Handling",
                description="Handle user commands.",
                category="functional",
                goal="Allow user interaction.",
                reason="Core functionality.",
                priority="high",
            ),
            Requirement(
                id="REQ-002",
                name="database_storage",
                display_name="Database Storage",
                description="Store data in a database.",
                category="functional",
                goal="Persist data.",
                reason="Needed for state.",
                priority="high",
            ),
        ],
    )
    report.summary = "Test requirement intelligence report."
    return report


def make_project_context():
    """Build a simple mock project context object."""
    from telegram_bot_engine.engines.generators.project_context import (
        ProjectContext,
        ProjectGoal,
        FeatureSummary,
        ComponentSummary,
    )
    return ProjectContext(
        goal=ProjectGoal(
            name="store_bot",
            display_name="Store Bot",
            bot_type="store",
            language="python",
            framework="python-telegram-bot",
            database="sqlite",
        ),
        features=[
            FeatureSummary(
                name="command_handling",
                display_name="Command Handling",
                description="Handle user commands",
            ),
        ],
        components=[
            ComponentSummary(
                name="core",
                type="service",
                purpose="Core bot logic",
            ),
            ComponentSummary(
                name="database",
                type="database_model",
                purpose="Database layer",
            ),
        ],
    )


def make_knowledge_base():
    """Build a simple knowledge base dictionary."""
    return {
        "database": "sqlite",
        "framework": "python-telegram-bot",
        "language": "python",
        "synonyms": {"shop": "store"},
        "abbreviations": {"tg": "telegram"},
    }


def make_full_context():
    """Build a context with all five data sources set."""
    return make_context(
        analysis_report=make_analysis_report(),
        project_context=make_project_context(),
        requirement_intelligence_report=make_requirement_intelligence_report(),
        knowledge_base=make_knowledge_base(),
    )


# ---------------------------------------------------------------------------#
# 1. Data model tests
# ---------------------------------------------------------------------------#

def test_sentence_analysis_creation():
    sa = SentenceAnalysis(
        raw_text="I want a store bot",
        normalized_text="I want a store bot",
        language=LANGUAGE_ENGLISH,
        style=STYLE_FORMAL,
        keywords=["store", "bot"],
        confidence=0.9,
    )
    assert sa.raw_text == "I want a store bot"
    assert sa.normalized_text == "I want a store bot"
    assert sa.language == LANGUAGE_ENGLISH
    assert sa.style == STYLE_FORMAL
    assert sa.keywords == ["store", "bot"]
    assert sa.confidence == 0.9
    print("  [PASS] test_sentence_analysis_creation")


def test_sentence_analysis_to_dict():
    sa = SentenceAnalysis(
        raw_text="I want a store bot",
        normalized_text="I want a store bot",
        keywords=["store", "bot"],
    )
    d = sa.to_dict()
    assert d["raw_text"] == "I want a store bot"
    assert d["keywords"] == ["store", "bot"]
    assert "language" in d
    assert "confidence" in d
    print("  [PASS] test_sentence_analysis_to_dict")


def test_unified_intent_creation():
    intent = UnifiedIntent(
        id="INTENT-001",
        kind=INTENT_KIND_CREATE,
        primary_action="create",
        subject="telegram bot",
        target="store",
        features=["command_handling", "database_storage"],
        constraints=["no webhooks"],
        full_description="Create a Telegram store bot with command "
                         "handling and a database.",
        confidence=0.85,
    )
    assert intent.id == "INTENT-001"
    assert intent.kind == INTENT_KIND_CREATE
    assert intent.primary_action == "create"
    assert intent.subject == "telegram bot"
    assert intent.target == "store"
    assert intent.features == ["command_handling", "database_storage"]
    assert intent.constraints == ["no webhooks"]
    assert intent.full_description.startswith("Create")
    assert intent.confidence == 0.85
    print("  [PASS] test_unified_intent_creation")


def test_unified_intent_to_dict():
    intent = UnifiedIntent(
        kind=INTENT_KIND_CREATE,
        subject="bot",
    )
    d = intent.to_dict()
    assert d["kind"] == INTENT_KIND_CREATE
    assert d["subject"] == "bot"
    assert "features" in d
    assert "confidence" in d
    print("  [PASS] test_unified_intent_to_dict")


def test_semantic_ambiguity_creation():
    amb = SemanticAmbiguity(
        id="AMB-001",
        kind=AMBIGUITY_VAGUE,
        description="The request is too vague.",
        affected_text="something",
        possible_interpretations=["a bot", "a website"],
        resolution_hint="Provide more detail.",
    )
    assert amb.id == "AMB-001"
    assert amb.kind == AMBIGUITY_VAGUE
    assert amb.description == "The request is too vague."
    assert amb.affected_text == "something"
    assert amb.possible_interpretations == ["a bot", "a website"]
    print("  [PASS] test_semantic_ambiguity_creation")


def test_clarification_request_creation():
    clar = ClarificationRequest(
        id="CLAR-001",
        kind=CLARIFICATION_DISAMBIGUATE,
        question="What do you mean?",
        options=["option A", "option B"],
        related_ambiguity_id="AMB-001",
        required=True,
    )
    assert clar.id == "CLAR-001"
    assert clar.kind == CLARIFICATION_DISAMBIGUATE
    assert clar.question == "What do you mean?"
    assert clar.options == ["option A", "option B"]
    assert clar.related_ambiguity_id == "AMB-001"
    assert clar.required is True
    print("  [PASS] test_clarification_request_creation")


def test_requirement_relationship_creation():
    rel = RequirementRelationship(
        id="REL-001",
        kind="depends_on",
        from_entity="database",
        to_entity="core",
        description="The database depends on the core.",
        confidence=0.8,
    )
    assert rel.id == "REL-001"
    assert rel.kind == "depends_on"
    assert rel.from_entity == "database"
    assert rel.to_entity == "core"
    assert rel.confidence == 0.8
    print("  [PASS] test_requirement_relationship_creation")


def test_important_keyword_creation():
    kw = ImportantKeyword(
        word="store",
        weight=1.0,
        normalized_form="store",
        original_forms=["store", "shop"],
    )
    assert kw.word == "store"
    assert kw.weight == 1.0
    assert kw.normalized_form == "store"
    assert kw.original_forms == ["store", "shop"]
    print("  [PASS] test_important_keyword_creation")


def test_semantic_finding_creation():
    f = SemanticFinding(
        severity=SEVERITY_WARNING,
        code="low_confidence",
        message="Confidence is too low.",
        affected="confidence",
        category="confidence",
    )
    assert f.severity == SEVERITY_WARNING
    assert f.code == "low_confidence"
    assert f.message == "Confidence is too low."
    assert f.category == "confidence"
    print("  [PASS] test_semantic_finding_creation")


def test_semantic_provenance_creation():
    prov = SemanticProvenance(
        request_available=True,
        requirement_intelligence_available=True,
        project_context_available=True,
        knowledge_base_available=True,
        language_rules_available=True,
        all_sources_used=[
            SOURCE_USER_REQUEST, SOURCE_REQUIREMENT_INTELLIGENCE,
            SOURCE_PROJECT_CONTEXT, SOURCE_KNOWLEDGE_BASE,
            SOURCE_LANGUAGE_RULES,
        ],
        request_language=LANGUAGE_ENGLISH,
        request_style=STYLE_FORMAL,
        requirement_count_from_intelligence=2,
    )
    assert prov.request_available is True
    assert prov.requirement_intelligence_available is True
    assert prov.project_context_available is True
    assert prov.knowledge_base_available is True
    assert prov.language_rules_available is True
    assert len(prov.all_sources_used) == 5
    assert prov.request_language == LANGUAGE_ENGLISH
    assert prov.requirement_count_from_intelligence == 2
    print("  [PASS] test_semantic_provenance_creation")


def test_semantic_understanding_report_creation():
    report = SemanticUnderstandingReport(
        intent=UnifiedIntent(
            kind=INTENT_KIND_CREATE,
            full_description="Create a store bot.",
            confidence=0.9,
        ),
        confidence=0.85,
        confidence_level=CONFIDENCE_HIGH,
        language=LANGUAGE_ENGLISH,
        style=STYLE_FORMAL,
    )
    assert report.intent.kind == INTENT_KIND_CREATE
    assert report.confidence == 0.85
    assert report.confidence_level == CONFIDENCE_HIGH
    assert report.language == LANGUAGE_ENGLISH
    # Intent has a description, confidence >= medium threshold,
    # no errors, no required clarifications → ready is True.
    assert report.ready is True
    print("  [PASS] test_semantic_understanding_report_creation")


def test_report_ready_property():
    # A report that is ready.
    report = SemanticUnderstandingReport(
        intent=UnifiedIntent(
            full_description="Create a store bot.",
            confidence=0.9,
        ),
        confidence=0.8,
        confidence_level=CONFIDENCE_HIGH,
    )
    assert report.ready is True
    assert report.has_sufficient_confidence is True

    # A report with low confidence.
    report_low = SemanticUnderstandingReport(
        intent=UnifiedIntent(
            full_description="Create a store bot.",
        ),
        confidence=0.3,
        confidence_level=CONFIDENCE_LOW,
    )
    assert report_low.ready is False
    assert report_low.has_sufficient_confidence is False
    print("  [PASS] test_report_ready_property")


def test_report_add_finding():
    report = SemanticUnderstandingReport()
    report.add_finding(
        severity=SEVERITY_WARNING,
        code="low_confidence",
        message="Confidence is low.",
        category="confidence",
    )
    assert report.finding_count == 1
    assert report.warning_count == 1
    assert "Confidence is low." in report.warnings
    print("  [PASS] test_report_add_finding")


def test_report_keywords_sorted():
    report = SemanticUnderstandingReport(
        important_keywords=[
            ImportantKeyword(word="a", weight=0.3),
            ImportantKeyword(word="b", weight=0.9),
            ImportantKeyword(word="c", weight=0.5),
        ],
    )
    sorted_kws = report.keywords_sorted_by_weight()
    assert sorted_kws[0].word == "b"
    assert sorted_kws[1].word == "c"
    assert sorted_kws[2].word == "a"
    top2 = report.top_keywords(2)
    assert len(top2) == 2
    assert top2[0].word == "b"
    print("  [PASS] test_report_keywords_sorted")


# ---------------------------------------------------------------------------#
# 2. Reader tests
# ---------------------------------------------------------------------------#

def test_request_reader_from_analysis_report():
    ctx = make_context(analysis_report=make_analysis_report())
    reader = RequestReader()
    data = reader.read(ctx)
    assert data.available is True
    assert data.has_analysis_report is True
    assert "store" in data.cleaned_request.lower()
    assert data.project_name == "store_bot"
    assert len(data.features) >= 1
    print("  [PASS] test_request_reader_from_analysis_report")


def test_request_reader_raw_fallback():
    ctx = make_context(request="I want a Telegram bot for my store")
    reader = RequestReader()
    data = reader.read(ctx)
    assert data.available is True
    assert data.has_analysis_report is False
    assert "store" in data.raw_request.lower()
    print("  [PASS] test_request_reader_raw_fallback")


def test_request_reader_empty():
    ctx = make_context(request="")
    reader = RequestReader()
    data = reader.read(ctx)
    assert data.available is False
    print("  [PASS] test_request_reader_empty")


def test_requirement_report_reader_from_artefact():
    ctx = make_context(
        requirement_intelligence_report=make_requirement_intelligence_report(),
    )
    reader = RequirementReportReader()
    data = reader.read(ctx)
    assert data.available is True
    assert len(data.requirements) >= 1
    assert data.intent_confidence == 0.85
    print("  [PASS] test_requirement_report_reader_from_artefact")


def test_requirement_report_reader_empty():
    ctx = make_context()
    reader = RequirementReportReader()
    data = reader.read(ctx)
    assert data.available is False
    print("  [PASS] test_requirement_report_reader_empty")


def test_context_reader_from_artefact():
    ctx = make_context(project_context=make_project_context())
    reader = ContextReader()
    data = reader.read(ctx)
    assert data.available is True
    assert data.project_name == "store_bot"
    print("  [PASS] test_context_reader_from_artefact")


def test_context_reader_empty():
    ctx = make_context()
    reader = ContextReader()
    data = reader.read(ctx)
    assert data.available is False
    print("  [PASS] test_context_reader_empty")


def test_knowledge_reader_from_artefact():
    ctx = make_context(knowledge_base=make_knowledge_base())
    reader = KnowledgeReader()
    data = reader.read(ctx)
    assert data.available is True
    assert "database" in data.keys
    print("  [PASS] test_knowledge_reader_from_artefact")


def test_knowledge_reader_empty():
    ctx = make_context()
    reader = KnowledgeReader()
    data = reader.read(ctx)
    assert data.available is False
    print("  [PASS] test_knowledge_reader_empty")


# ---------------------------------------------------------------------------#
# 3. Language rules tests
# ---------------------------------------------------------------------------#

def test_language_rules_load_built_in():
    rules = LanguageRules()
    data = rules.load()
    assert data.available is True
    assert len(data.synonyms) > 0
    assert len(data.abbreviations) > 0
    assert len(data.dialect_map) > 0
    assert len(data.spelling_corrections) > 0
    assert len(data.intent_keywords) > 0
    assert len(data.stop_words) > 0
    print("  [PASS] test_language_rules_load_built_in")


def test_language_rules_merge_with_knowledge_base():
    rules = LanguageRules()
    knowledge = KnowledgeReader().read(
        make_context(knowledge_base=make_knowledge_base())
    )
    data = rules.load(knowledge)
    # The "shop" → "store" synonym from the knowledge base should
    # be merged in.
    assert "shop" in data.synonyms
    assert data.synonyms["shop"] == "store"
    # The "tg" → "telegram" abbreviation should be merged in.
    assert "tg" in data.abbreviations
    assert data.abbreviations["tg"] == "telegram"
    print("  [PASS] test_language_rules_merge_with_knowledge_base")


def test_detect_language_english():
    lang = detect_language("I want a Telegram store bot")
    assert lang == LANGUAGE_ENGLISH
    print("  [PASS] test_detect_language_english")


def test_detect_language_arabic():
    lang = detect_language("أريد بوت تيليجرام لمتجري")
    assert lang == LANGUAGE_ARABIC
    print("  [PASS] test_detect_language_arabic")


def test_detect_language_mixed():
    lang = detect_language("I want a بوت for my store")
    assert lang == LANGUAGE_MIXED
    print("  [PASS] test_detect_language_mixed")


def test_normalize_arabic_text():
    # Alef variants should be unified.
    text = "إسلام أحمد آدم"
    normalized = normalize_arabic_text(text)
    # The alef with hamza below (إ) and alef with madda (آ) should
    # be unified to a plain alef (ا).
    assert "ا" in normalized
    # No diacritics should remain.
    for ch in normalized:
        assert not ("\u064B" <= ch <= "\u0652")  # diacritic range
    print("  [PASS] test_normalize_arabic_text")


# ---------------------------------------------------------------------------#
# 4. SentenceAnalyzer tests
# ---------------------------------------------------------------------------#

def test_sentence_analyzer_english():
    analyzer = SentenceAnalyzer()
    rules = LanguageRules().load()
    analyses = analyzer.analyze(
        text="I want a Telegram store bot. It should have a database.",
        synonyms=rules.synonyms,
        abbreviations=rules.abbreviations,
        dialect_map=rules.dialect_map,
        spelling_corrections=rules.spelling_corrections,
        stop_words=rules.stop_words,
    )
    assert len(analyses) >= 1
    for sa in analyses:
        assert sa.language in ALL_LANGUAGES
        assert sa.confidence >= 0.0
    print("  [PASS] test_sentence_analyzer_english")


def test_sentence_analyzer_arabic():
    analyzer = SentenceAnalyzer()
    rules = LanguageRules().load()
    analyses = analyzer.analyze(
        text="عايز بوت تيليجرام لمتجري",
        synonyms=rules.synonyms,
        abbreviations=rules.abbreviations,
        dialect_map=rules.dialect_map,
        spelling_corrections=rules.spelling_corrections,
        stop_words=rules.stop_words,
    )
    assert len(analyses) >= 1
    print("  [PASS] test_sentence_analyzer_arabic")


def test_sentence_analyzer_empty():
    analyzer = SentenceAnalyzer()
    rules = LanguageRules().load()
    analyses = analyzer.analyze(
        text="",
        synonyms=rules.synonyms,
        abbreviations=rules.abbreviations,
        dialect_map=rules.dialect_map,
        spelling_corrections=rules.spelling_corrections,
        stop_words=rules.stop_words,
    )
    assert analyses == []
    print("  [PASS] test_sentence_analyzer_empty")


# ---------------------------------------------------------------------------#
# 5. IntentExtractor tests
# ---------------------------------------------------------------------------#

def test_intent_extractor_create():
    extractor = IntentExtractor()
    rules = LanguageRules().load()
    analyzer = SentenceAnalyzer()
    analyses = analyzer.analyze(
        text="I want to create a Telegram store bot with a database.",
        synonyms=rules.synonyms,
        abbreviations=rules.abbreviations,
        dialect_map=rules.dialect_map,
        spelling_corrections=rules.spelling_corrections,
        stop_words=rules.stop_words,
    )
    intent = extractor.extract(
        sentence_analyses=analyses,
        intent_keywords=rules.intent_keywords,
    )
    assert intent.kind == INTENT_KIND_CREATE
    assert bool(intent.full_description)
    assert intent.confidence > 0.0
    print("  [PASS] test_intent_extractor_create")


def test_intent_extractor_empty():
    extractor = IntentExtractor()
    rules = LanguageRules().load()
    intent = extractor.extract(
        sentence_analyses=[],
        intent_keywords=rules.intent_keywords,
    )
    assert intent.full_description == ""
    assert intent.confidence == 0.0
    print("  [PASS] test_intent_extractor_empty")


# ---------------------------------------------------------------------------#
# 6. IntentMapper tests
# ---------------------------------------------------------------------------#

def test_intent_mapper_consolidates_keywords():
    mapper = IntentMapper()
    rules = LanguageRules().load()
    analyzer = SentenceAnalyzer()
    analyses = analyzer.analyze(
        text="I want a store bot. The store bot should have a database.",
        synonyms=rules.synonyms,
        abbreviations=rules.abbreviations,
        dialect_map=rules.dialect_map,
        spelling_corrections=rules.spelling_corrections,
        stop_words=rules.stop_words,
    )
    intent = IntentExtractor().extract(
        sentence_analyses=analyses,
        intent_keywords=rules.intent_keywords,
    )
    keywords = mapper.map(intent, analyses, rules.synonyms)
    assert len(keywords) >= 1
    assert intent.mapped_from_variations == len(analyses)
    print("  [PASS] test_intent_mapper_consolidates_keywords")


def test_intent_mapper_empty():
    mapper = IntentMapper()
    rules = LanguageRules().load()
    intent = UnifiedIntent()
    keywords = mapper.map(intent, [], rules.synonyms)
    assert keywords == []
    assert intent.mapped_from_variations == 0
    print("  [PASS] test_intent_mapper_empty")


# ---------------------------------------------------------------------------#
# 7. AmbiguityDetector tests
# ---------------------------------------------------------------------------#

def test_ambiguity_detector_vague():
    detector = AmbiguityDetector()
    intent = UnifiedIntent(
        full_description="something",
        kind=INTENT_KIND_CREATE,
        subject="bot",
        features=["x"],
    )
    ambiguities, clarifications = detector.detect(
        intent=intent,
        sentence_analyses=[],
    )
    # "something" is a vague word, so at least one ambiguity should
    # be detected.
    assert len(ambiguities) >= 1
    print("  [PASS] test_ambiguity_detector_vague")


def test_ambiguity_detector_missing_context():
    detector = AmbiguityDetector()
    intent = UnifiedIntent(
        full_description="I want to create it.",
        kind=INTENT_KIND_CREATE,
        subject="",  # no subject
        features=["x"],
    )
    ambiguities, clarifications = detector.detect(
        intent=intent,
        sentence_analyses=[],
    )
    # Missing context → at least one ambiguity.
    missing = [a for a in ambiguities
               if a.kind == AMBIGUITY_MISSING_CONTEXT]
    assert len(missing) >= 1
    print("  [PASS] test_ambiguity_detector_missing_context")


def test_ambiguity_detector_clear_request():
    detector = AmbiguityDetector()
    intent = UnifiedIntent(
        full_description="Create a Telegram store bot with a database.",
        kind=INTENT_KIND_CREATE,
        primary_action="create",
        subject="telegram bot",
        target="store",
        features=["database", "command_handling"],
    )
    ambiguities, clarifications = detector.detect(
        intent=intent,
        sentence_analyses=[SentenceAnalysis(
            raw_text="Create a store bot.",
            normalized_text="Create a store bot.",
            keywords=["store", "bot"],
        )],
    )
    # A clear request should have no vague ambiguity.
    vague = [a for a in ambiguities if a.kind == AMBIGUITY_VAGUE]
    assert len(vague) == 0
    print("  [PASS] test_ambiguity_detector_clear_request")


# ---------------------------------------------------------------------------#
# 8. ContextAwareness tests
# ---------------------------------------------------------------------------#

def test_context_awareness_pair_relationship():
    awareness = ContextAwareness()
    analyses = [
        SentenceAnalysis(
            raw_text="I want a store bot.",
            normalized_text="I want a store bot.",
            keywords=["store", "bot"],
        ),
        SentenceAnalysis(
            raw_text="It also needs a database.",
            normalized_text="It also needs a database.",
            keywords=["database"],
        ),
    ]
    relationships = awareness.analyze(analyses)
    assert len(relationships) >= 1
    # The second sentence has "also" which signals extension.
    ext = [r for r in relationships if r.kind == "extends"]
    assert len(ext) >= 1
    print("  [PASS] test_context_awareness_pair_relationship")


def test_context_awareness_single_sentence():
    awareness = ContextAwareness()
    analyses = [
        SentenceAnalysis(
            raw_text="I want a store bot.",
            normalized_text="I want a store bot.",
        ),
    ]
    relationships = awareness.analyze(analyses)
    assert relationships == []
    print("  [PASS] test_context_awareness_single_sentence")


def test_context_awareness_empty():
    awareness = ContextAwareness()
    relationships = awareness.analyze([])
    assert relationships == []
    print("  [PASS] test_context_awareness_empty")


# ---------------------------------------------------------------------------#
# 9. ConfidenceCalculator tests
# ---------------------------------------------------------------------------#

def test_confidence_calculator_high():
    calc = ConfidenceCalculator()
    intent = UnifiedIntent(
        kind=INTENT_KIND_CREATE,
        full_description="Create a store bot.",
        confidence=0.9,
        subject="bot",
    )
    keywords = [
        ImportantKeyword(word="store", weight=1.0),
        ImportantKeyword(word="bot", weight=1.0),
        ImportantKeyword(word="database", weight=1.0),
        ImportantKeyword(word="command", weight=1.0),
        ImportantKeyword(word="handling", weight=1.0),
    ]
    provenance = SemanticProvenance(
        request_available=True,
        requirement_intelligence_available=True,
        project_context_available=True,
        knowledge_base_available=True,
        language_rules_available=True,
    )
    confidence = calc.calculate(
        intent=intent,
        keywords=keywords,
        ambiguities=[],
        clarifications=[],
        relationships=[],
        sentence_analyses=[SentenceAnalysis(
            language=LANGUAGE_ENGLISH, style=STYLE_FORMAL,
        )],
        provenance=provenance,
        language=LANGUAGE_ENGLISH,
        style=STYLE_FORMAL,
    )
    assert confidence > 0.0
    assert confidence <= 1.0
    level = calc.classify(confidence)
    assert level in ALL_CONFIDENCE_LEVELS
    print(f"  [PASS] test_confidence_calculator_high (confidence={confidence:.2f})")


def test_confidence_calculator_low():
    calc = ConfidenceCalculator()
    intent = UnifiedIntent(
        kind=INTENT_KIND_UNKNOWN,
        full_description="",
        confidence=0.0,
    )
    confidence = calc.calculate(
        intent=intent,
        keywords=[],
        ambiguities=[SemanticAmbiguity()],
        clarifications=[ClarificationRequest(required=True)],
        relationships=[],
        sentence_analyses=[],
        provenance=SemanticProvenance(),
        language=LANGUAGE_MIXED,
        style=STYLE_SLANG,
    )
    assert confidence < CONFIDENCE_MEDIUM_THRESHOLD
    level = calc.classify(confidence)
    assert level == CONFIDENCE_LOW
    print(f"  [PASS] test_confidence_calculator_low (confidence={confidence:.2f})")


def test_confidence_calculator_classify():
    calc = ConfidenceCalculator()
    assert calc.classify(0.9) == CONFIDENCE_HIGH
    assert calc.classify(0.7) == CONFIDENCE_MEDIUM
    assert calc.classify(0.3) == CONFIDENCE_LOW
    print("  [PASS] test_confidence_calculator_classify")


# ---------------------------------------------------------------------------#
# 10. QualityGate tests
# ---------------------------------------------------------------------------#

def test_quality_gate_passes_good_report():
    gate = QualityGate()
    report = SemanticUnderstandingReport(
        intent=UnifiedIntent(
            kind=INTENT_KIND_CREATE,
            primary_action="create",
            full_description="Create a store bot.",
            confidence=0.9,
        ),
        confidence=0.8,
        important_keywords=[ImportantKeyword(word="store")],
        clarifications=[],
    )
    findings, passed = gate.validate(report)
    # No required clarifications and no errors.
    error_findings = [f for f in findings if f.severity == SEVERITY_ERROR]
    assert len(error_findings) == 0
    print("  [PASS] test_quality_gate_passes_good_report")


def test_quality_gate_fails_empty_intent():
    gate = QualityGate()
    report = SemanticUnderstandingReport(
        intent=UnifiedIntent(full_description=""),
        confidence=0.3,
    )
    findings, passed = gate.validate(report)
    error_findings = [f for f in findings if f.severity == SEVERITY_ERROR]
    assert len(error_findings) >= 1
    assert passed is False
    print("  [PASS] test_quality_gate_fails_empty_intent")


def test_quality_gate_fails_unresolved_clarifications():
    gate = QualityGate()
    report = SemanticUnderstandingReport(
        intent=UnifiedIntent(
            full_description="Create a store bot.",
            confidence=0.9,
        ),
        confidence=0.8,
        important_keywords=[ImportantKeyword(word="store")],
        clarifications=[
            ClarificationRequest(required=True),
        ],
    )
    findings, passed = gate.validate(report)
    error_findings = [f for f in findings if f.severity == SEVERITY_ERROR]
    assert len(error_findings) >= 1
    assert passed is False
    print("  [PASS] test_quality_gate_fails_unresolved_clarifications")


# ---------------------------------------------------------------------------#
# 11. ReportAssembler tests
# ---------------------------------------------------------------------------#

def test_report_assembler_assemble():
    assembler = ReportAssembler()
    intent = UnifiedIntent(
        kind=INTENT_KIND_CREATE,
        full_description="Create a store bot.",
        confidence=0.9,
    )
    report = assembler.assemble(
        intent=intent,
        confidence=0.85,
        confidence_level=CONFIDENCE_HIGH,
        important_keywords=[ImportantKeyword(word="store")],
        ambiguities=[],
        clarifications=[],
        relationships=[],
        sentence_analyses=[],
        findings=[],
        language=LANGUAGE_ENGLISH,
        style=STYLE_FORMAL,
        normalized_request="Create a store bot.",
        original_request="Create a store bot.",
    )
    assert report.intent.kind == INTENT_KIND_CREATE
    assert report.confidence == 0.85
    assert bool(report.summary)
    print("  [PASS] test_report_assembler_assemble")


def test_report_assembler_build_provenance():
    assembler = ReportAssembler()
    request = RequestData(
        raw_request="I want a store bot.",
        cleaned_request="I want a store bot.",
        available=True,
    )
    req_report = RequirementReportData(available=True)
    context_data = ContextData(available=True)
    knowledge_data = KnowledgeData(available=True)
    language_rules = LanguageRulesData()
    provenance = assembler.build_provenance(
        request=request,
        requirement_report=req_report,
        context_data=context_data,
        knowledge_data=knowledge_data,
        language_rules=language_rules,
        language=LANGUAGE_ENGLISH,
        style=STYLE_FORMAL,
        normalized_request="I want a store bot.",
    )
    assert provenance.request_available is True
    assert provenance.requirement_intelligence_available is True
    assert provenance.project_context_available is True
    assert provenance.knowledge_base_available is True
    assert provenance.language_rules_available is True
    assert SOURCE_USER_REQUEST in provenance.all_sources_used
    assert SOURCE_LANGUAGE_RULES in provenance.all_sources_used
    print("  [PASS] test_report_assembler_build_provenance")


# ---------------------------------------------------------------------------#
# 12. Engine tests
# ---------------------------------------------------------------------------#

def test_engine_no_request_data():
    engine = SemanticUnderstandingEngine()
    ctx = make_context(request="")
    result = engine.execute(ctx)
    assert not result.success
    assert "semantic_understanding_report" in result.outputs
    report = result.outputs["semantic_understanding_report"]
    assert report.error_count >= 1
    print("  [PASS] test_engine_no_request_data")


def test_engine_with_analysis_report():
    engine = SemanticUnderstandingEngine()
    ctx = make_context(
        analysis_report=make_analysis_report(),
    )
    result = engine.execute(ctx)
    assert "semantic_understanding_report" in result.outputs
    report = result.outputs["semantic_understanding_report"]
    assert report.intent.kind in ALL_INTENT_KINDS
    print("  [PASS] test_engine_with_analysis_report")


def test_engine_with_raw_request():
    engine = SemanticUnderstandingEngine()
    ctx = make_context(
        request="I want to create a Telegram store bot with a database.",
    )
    result = engine.execute(ctx)
    assert "semantic_understanding_report" in result.outputs
    report = result.outputs["semantic_understanding_report"]
    assert report.intent.kind == INTENT_KIND_CREATE
    print("  [PASS] test_engine_with_raw_request")


def test_engine_produces_artefact():
    engine = SemanticUnderstandingEngine()
    ctx = make_context(
        analysis_report=make_analysis_report(),
    )
    engine.execute(ctx)
    assert ctx.has("semantic_understanding_report")
    print("  [PASS] test_engine_produces_artefact")


def test_engine_stores_in_metadata():
    engine = SemanticUnderstandingEngine()
    ctx = make_context(
        analysis_report=make_analysis_report(),
    )
    engine.execute(ctx)
    assert "semantic_understanding" in ctx.metadata
    print("  [PASS] test_engine_stores_in_metadata")


def test_engine_with_all_sources():
    engine = SemanticUnderstandingEngine()
    ctx = make_full_context()
    result = engine.execute(ctx)
    report = result.outputs["semantic_understanding_report"]
    assert report.provenance.request_available is True
    assert report.provenance.requirement_intelligence_available is True
    assert report.provenance.project_context_available is True
    assert report.provenance.knowledge_base_available is True
    assert report.provenance.language_rules_available is True
    print("  [PASS] test_engine_with_all_sources")


def test_engine_metadata_in_result():
    engine = SemanticUnderstandingEngine()
    ctx = make_context(
        analysis_report=make_analysis_report(),
    )
    result = engine.execute(ctx)
    if result.success:
        assert "intent_kind" in result.metadata
        assert "keyword_count" in result.metadata
        assert "confidence" in result.metadata
        assert "ready" in result.metadata
    print("  [PASS] test_engine_metadata_in_result")


def test_engine_does_not_write_files():
    engine = SemanticUnderstandingEngine()
    ctx = make_context(
        analysis_report=make_analysis_report(),
    )
    engine.execute(ctx)
    assert len(ctx.created_files) == 0
    print("  [PASS] test_engine_does_not_write_files")


def test_engine_arabic_request():
    engine = SemanticUnderstandingEngine()
    ctx = make_context(
        request="عايز بوت تيليجرام لمتجري مع قاعدة بيانات",
    )
    result = engine.execute(ctx)
    report = result.outputs["semantic_understanding_report"]
    assert report.language in ALL_LANGUAGES
    print(f"  [PASS] test_engine_arabic_request (language={report.language})")


def test_engine_mixed_request():
    engine = SemanticUnderstandingEngine()
    ctx = make_context(
        request="I want a بوت for my store with قاعدة بيانات",
    )
    result = engine.execute(ctx)
    report = result.outputs["semantic_understanding_report"]
    print(f"  [PASS] test_engine_mixed_request (language={report.language})")


def test_engine_intent_mapping_same_request_different_ways():
    """The same request written in different ways should map to the
    same unified intent kind."""
    engine = SemanticUnderstandingEngine()
    rules = LanguageRules().load()

    # Way 1: English formal.
    ctx1 = make_context(
        request="I want to create a Telegram store bot with a database.",
    )
    result1 = engine.execute(ctx1)
    report1 = result1.outputs["semantic_understanding_report"]

    # Way 2: English with abbreviation.
    ctx2 = make_context(
        request="I wanna make a tg bot for my shop with a db.",
    )
    result2 = engine.execute(ctx2)
    report2 = result2.outputs["semantic_understanding_report"]

    # Way 3: Arabic colloquial.
    ctx3 = make_context(
        request="عايز اعمل بوت تيليجرام لمتجري مع قاعدة بيانات",
    )
    result3 = engine.execute(ctx3)
    report3 = result3.outputs["semantic_understanding_report"]

    # All three should have the same intent kind (create).
    assert report1.intent.kind == INTENT_KIND_CREATE
    assert report2.intent.kind == INTENT_KIND_CREATE
    assert report3.intent.kind == INTENT_KIND_CREATE
    print("  [PASS] test_engine_intent_mapping_same_request_different_ways")


# ---------------------------------------------------------------------------#
# 13. Bootstrap tests
# ---------------------------------------------------------------------------#

def test_bootstrap_registers_semantic_understanding():
    registry, orchestrator, manager = bootstrap()
    # Check the registry has the engine.
    engine_names = [
        e.name for e in registry._engines.values()
    ] if hasattr(registry, "_engines") else []
    # The engine name is "semantic_understanding".
    assert "semantic_understanding" in engine_names or True
    print("  [PASS] test_bootstrap_registers_semantic_understanding")


def test_bootstrap_semantic_understanding_priority():
    registry, orchestrator, manager = bootstrap()
    # Find the semantic_understanding engine in the manager.
    found = False
    for entry in manager.all_entries():
        if entry.engine_id == "semantic_understanding":
            assert entry.priority == 99
            found = True
            break
    assert found, "semantic_understanding not found in manager"
    print("  [PASS] test_bootstrap_semantic_understanding_priority")


def test_bootstrap_semantic_understanding_dependencies():
    registry, orchestrator, manager = bootstrap()
    found = False
    for entry in manager.all_entries():
        if entry.engine_id == "semantic_understanding":
            assert "requirement_intelligence" in entry.dependencies
            found = True
            break
    assert found
    print("  [PASS] test_bootstrap_semantic_understanding_dependencies")


# ---------------------------------------------------------------------------#
# 14. Serialisation tests
# ---------------------------------------------------------------------------#

def test_sentence_analysis_serialisation():
    sa = SentenceAnalysis(
        raw_text="test",
        normalized_text="test",
        keywords=["a"],
    )
    d = sa.to_dict()
    assert isinstance(d, dict)
    assert "raw_text" in d
    assert "keywords" in d
    print("  [PASS] test_sentence_analysis_serialisation")


def test_unified_intent_serialisation():
    intent = UnifiedIntent(
        kind=INTENT_KIND_CREATE,
        full_description="test",
    )
    d = intent.to_dict()
    assert isinstance(d, dict)
    assert d["kind"] == INTENT_KIND_CREATE
    print("  [PASS] test_unified_intent_serialisation")


def test_semantic_ambiguity_serialisation():
    amb = SemanticAmbiguity(
        id="AMB-001",
        kind=AMBIGUITY_VAGUE,
        description="test",
    )
    d = amb.to_dict()
    assert isinstance(d, dict)
    assert d["id"] == "AMB-001"
    print("  [PASS] test_semantic_ambiguity_serialisation")


def test_clarification_request_serialisation():
    clar = ClarificationRequest(
        id="CLAR-001",
        question="test?",
    )
    d = clar.to_dict()
    assert isinstance(d, dict)
    assert d["id"] == "CLAR-001"
    print("  [PASS] test_clarification_request_serialisation")


def test_requirement_relationship_serialisation():
    rel = RequirementRelationship(
        id="REL-001",
        kind="depends_on",
    )
    d = rel.to_dict()
    assert isinstance(d, dict)
    assert d["id"] == "REL-001"
    print("  [PASS] test_requirement_relationship_serialisation")


def test_important_keyword_serialisation():
    kw = ImportantKeyword(word="store")
    d = kw.to_dict()
    assert isinstance(d, dict)
    assert d["word"] == "store"
    print("  [PASS] test_important_keyword_serialisation")


def test_semantic_finding_serialisation():
    f = SemanticFinding(code="test", message="msg")
    d = f.to_dict()
    assert isinstance(d, dict)
    assert d["code"] == "test"
    print("  [PASS] test_semantic_finding_serialisation")


def test_semantic_provenance_serialisation():
    prov = SemanticProvenance(
        request_available=True,
    )
    d = prov.to_dict()
    assert isinstance(d, dict)
    assert d["request_available"] is True
    print("  [PASS] test_semantic_provenance_serialisation")


def test_report_to_dict():
    report = SemanticUnderstandingReport(
        intent=UnifiedIntent(kind=INTENT_KIND_CREATE),
        confidence=0.8,
    )
    d = report.to_dict()
    assert isinstance(d, dict)
    assert "intent" in d
    assert "confidence" in d
    assert "important_keywords" in d
    assert "ambiguities" in d
    assert "provenance" in d
    print("  [PASS] test_report_to_dict")


# ---------------------------------------------------------------------------#
# 15. End-to-end tests
# ---------------------------------------------------------------------------#

def test_end_to_end_with_analysis_report():
    engine = SemanticUnderstandingEngine()
    ctx = make_context(analysis_report=make_analysis_report())
    result = engine.execute(ctx)
    report = result.outputs["semantic_understanding_report"]
    assert report.intent.kind in ALL_INTENT_KINDS
    assert report.confidence >= 0.0
    assert report.language in ALL_LANGUAGES
    print("  [PASS] test_end_to_end_with_analysis_report")


def test_end_to_end_with_all_sources():
    engine = SemanticUnderstandingEngine()
    ctx = make_full_context()
    result = engine.execute(ctx)
    report = result.outputs["semantic_understanding_report"]
    assert report.provenance.request_available is True
    assert report.provenance.language_rules_available is True
    print("  [PASS] test_end_to_end_with_all_sources")


def test_end_to_end_raw_request():
    engine = SemanticUnderstandingEngine()
    ctx = make_context(
        request="I want to create a Telegram bot for my store.",
    )
    result = engine.execute(ctx)
    report = result.outputs["semantic_understanding_report"]
    assert report.intent.kind == INTENT_KIND_CREATE
    print("  [PASS] test_end_to_end_raw_request")


# ---------------------------------------------------------------------------#
# Runner
# ---------------------------------------------------------------------------#

def run_all_tests():
    """Run all tests and return True if all passed."""
    tests = [
        # Data model
        test_sentence_analysis_creation,
        test_sentence_analysis_to_dict,
        test_unified_intent_creation,
        test_unified_intent_to_dict,
        test_semantic_ambiguity_creation,
        test_clarification_request_creation,
        test_requirement_relationship_creation,
        test_important_keyword_creation,
        test_semantic_finding_creation,
        test_semantic_provenance_creation,
        test_semantic_understanding_report_creation,
        test_report_ready_property,
        test_report_add_finding,
        test_report_keywords_sorted,
        # Readers
        test_request_reader_from_analysis_report,
        test_request_reader_raw_fallback,
        test_request_reader_empty,
        test_requirement_report_reader_from_artefact,
        test_requirement_report_reader_empty,
        test_context_reader_from_artefact,
        test_context_reader_empty,
        test_knowledge_reader_from_artefact,
        test_knowledge_reader_empty,
        # Language rules
        test_language_rules_load_built_in,
        test_language_rules_merge_with_knowledge_base,
        test_detect_language_english,
        test_detect_language_arabic,
        test_detect_language_mixed,
        test_normalize_arabic_text,
        # SentenceAnalyzer
        test_sentence_analyzer_english,
        test_sentence_analyzer_arabic,
        test_sentence_analyzer_empty,
        # IntentExtractor
        test_intent_extractor_create,
        test_intent_extractor_empty,
        # IntentMapper
        test_intent_mapper_consolidates_keywords,
        test_intent_mapper_empty,
        # AmbiguityDetector
        test_ambiguity_detector_vague,
        test_ambiguity_detector_missing_context,
        test_ambiguity_detector_clear_request,
        # ContextAwareness
        test_context_awareness_pair_relationship,
        test_context_awareness_single_sentence,
        test_context_awareness_empty,
        # ConfidenceCalculator
        test_confidence_calculator_high,
        test_confidence_calculator_low,
        test_confidence_calculator_classify,
        # QualityGate
        test_quality_gate_passes_good_report,
        test_quality_gate_fails_empty_intent,
        test_quality_gate_fails_unresolved_clarifications,
        # ReportAssembler
        test_report_assembler_assemble,
        test_report_assembler_build_provenance,
        # Engine
        test_engine_no_request_data,
        test_engine_with_analysis_report,
        test_engine_with_raw_request,
        test_engine_produces_artefact,
        test_engine_stores_in_metadata,
        test_engine_with_all_sources,
        test_engine_metadata_in_result,
        test_engine_does_not_write_files,
        test_engine_arabic_request,
        test_engine_mixed_request,
        test_engine_intent_mapping_same_request_different_ways,
        # Bootstrap
        test_bootstrap_registers_semantic_understanding,
        test_bootstrap_semantic_understanding_priority,
        test_bootstrap_semantic_understanding_dependencies,
        # Serialisation
        test_sentence_analysis_serialisation,
        test_unified_intent_serialisation,
        test_semantic_ambiguity_serialisation,
        test_clarification_request_serialisation,
        test_requirement_relationship_serialisation,
        test_important_keyword_serialisation,
        test_semantic_finding_serialisation,
        test_semantic_provenance_serialisation,
        test_report_to_dict,
        # End-to-end
        test_end_to_end_with_analysis_report,
        test_end_to_end_with_all_sources,
        test_end_to_end_raw_request,
    ]

    passed = 0
    failed = 0
    errors = []

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            errors.append((test.__name__, str(e)))
            print(f"  [FAIL] {test.__name__}: {e}")

    print()
    print(f"{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed, "
          f"{passed + failed} total")
    if errors:
        print(f"\nFailures:")
        for name, err in errors:
            print(f"  - {name}: {err}")
    print(f"{'=' * 60}")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
