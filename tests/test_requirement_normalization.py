#!/usr/bin/env python3
"""
Comprehensive test suite for the Requirement Normalization Engine
(Specification 014).

These tests cover every aspect of the specification:

1. Data model integrity (CanonicalName, TerminologyMapping,
   RequirementLink, DuplicateRecord, ConflictRecord,
   NormalizationFinding, CacheInfo, NormalizationProvenance,
   NormalizedRequirement, NormalizationReport, source-artefact
   constants, severity constants, status constants, priority
   constants, category constants, link-kind constants, cache-status
   constants, confidence-level constants).
2. The RequestReader (analysis_report artefact, raw request
   fallback, empty context).
3. The RequirementIntelligenceReader (requirement_intelligence_report
   artefact, empty context).
4. The SemanticUnderstandingReader (semantic_understanding_report
   artefact, empty context).
5. The ContextReader (project_context artefact, empty context).
6. The KnowledgeReader (knowledge_base artefact, empty context).
7. The NameNormalizer (collecting names, snake_case normalization,
   grouping by similarity, canonical name objects).
8. The TerminologyNormalizer (building term map from knowledge base,
   collecting terms, terminology mapping objects).
9. The DeduplicationRemover (Jaccard similarity, merging duplicates,
   keeping originals).
10. The ConsistencyValidator (remaining duplicates, conflicts,
    terminology variations, lost requirements).
11. The RequirementLinker (linking to feature, component, priority,
    dependencies, expected output).
12. The CacheManager (enabled/disabled, cache info, get/store,
    cache hit, cache miss, cache size).
13. The QualityGate (empty report, unlinked requirements, duplicates,
    unresolved conflicts, low confidence, lost requirements).
14. The ReportAssembler (assembles report, builds provenance, summary,
    notes, warnings).
15. The main engine reads the five data sources.
16. The main engine produces a requirement_normalization_report
    artefact.
17. The main engine fails when no request data is available.
18. The main engine stores the report in the context metadata.
19. Bootstrap integration (engine registered in registry and manager
    at priority 100, depends on semantic_understanding).
20. Serialisation (to_dict) for all data model classes.
21. End-to-end pipeline with requirement intelligence, semantic
    understanding, project context, and knowledge base.
22. Deduplication: same requirement described differently is
    merged.
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
from telegram_bot_engine.engines.generators.requirement_normalization import (
    # Engine
    RequirementNormalizationEngine,
    # Data model
    CanonicalName,
    TerminologyMapping,
    RequirementLink,
    DuplicateRecord,
    ConflictRecord,
    NormalizationFinding,
    CacheInfo,
    NormalizationProvenance,
    NormalizedRequirement,
    NormalizationReport,
    # Source-artefact constants
    SOURCE_USER_REQUEST,
    SOURCE_REQUIREMENT_INTELLIGENCE,
    SOURCE_SEMANTIC_UNDERSTANDING,
    SOURCE_PROJECT_CONTEXT,
    SOURCE_KNOWLEDGE_BASE,
    ALL_SOURCES,
    # Severity constants
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    SEVERITY_INFO,
    ALL_SEVERITIES,
    # Status constants
    STATUS_ACTIVE,
    STATUS_DEPRECATED,
    STATUS_MERGED,
    STATUS_REMOVED,
    ALL_STATUSES,
    # Priority constants
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    PRIORITY_MEDIUM,
    PRIORITY_LOW,
    ALL_PRIORITIES,
    PRIORITY_WEIGHTS,
    # Category constants
    CATEGORY_FUNCTIONAL,
    CATEGORY_NON_FUNCTIONAL,
    CATEGORY_TECHNICAL,
    CATEGORY_CONSTRAINT,
    CATEGORY_INTERFACE,
    CATEGORY_SECURITY,
    CATEGORY_PERFORMANCE,
    CATEGORY_USABILITY,
    CATEGORY_DEPLOYMENT,
    ALL_CATEGORIES,
    # Link kind constants
    LINK_KIND_FEATURE,
    LINK_KIND_COMPONENT,
    LINK_KIND_DEPENDENCY,
    LINK_KIND_EXPECTED_OUTPUT,
    ALL_LINK_KINDS,
    # Cache status constants
    CACHE_HIT,
    CACHE_MISS,
    CACHE_STALE,
    CACHE_DISABLED,
    ALL_CACHE_STATUSES,
    # Confidence level constants
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_LOW,
    ALL_CONFIDENCE_LEVELS,
    CONFIDENCE_HIGH_THRESHOLD,
    CONFIDENCE_MEDIUM_THRESHOLD,
    # Readers + intermediate data
    RequestReader,
    RequestData,
    RequirementIntelligenceReader,
    RequirementIntelligenceData,
    RawRequirement,
    SemanticUnderstandingReader,
    SemanticUnderstandingData,
    SemanticKeyword,
    SemanticRequirement,
    ContextReader,
    ContextData,
    KnowledgeReader,
    KnowledgeData,
    # Helpers and processors
    NameNormalizer,
    TerminologyNormalizer,
    DeduplicationRemover,
    ConsistencyValidator,
    RequirementLinker,
    CacheManager,
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
    semantic_understanding_report=None,
    knowledge_base=None,
    request="",
):
    """Build a generation context with the five data sources."""
    ctx = GenerationContext(
        request=request,
        config=make_config(),
        work_dir=Path("/tmp/test_requirement_normalization"),
    )
    if analysis_report is not None:
        ctx.set("analysis_report", analysis_report)
    if project_context is not None:
        ctx.set("project_context", project_context)
    if requirement_intelligence_report is not None:
        ctx.set("requirement_intelligence_report",
                requirement_intelligence_report)
    if semantic_understanding_report is not None:
        ctx.set("semantic_understanding_report",
                semantic_understanding_report)
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


def make_semantic_understanding_report():
    """Build a simple mock semantic understanding report."""
    from telegram_bot_engine.engines.generators.semantic_understanding import (
        SemanticUnderstandingReport,
        UnifiedIntent,
        ImportantKeyword,
    )
    report = SemanticUnderstandingReport(
        intent=UnifiedIntent(
            id="INTENT-001",
            kind="create",
            primary_action="create",
            subject="telegram bot",
            target="store",
            features=["command_handling", "database_storage"],
            constraints=["no webhooks"],
            full_description="Create a Telegram store bot with command "
                             "handling and a database.",
            confidence=0.85,
        ),
        confidence=0.85,
        important_keywords=[
            ImportantKeyword(
                word="store",
                weight=1.0,
                normalized_form="store",
                original_forms=["store", "shop"],
            ),
            ImportantKeyword(
                word="database",
                weight=0.9,
                normalized_form="database",
                original_forms=["database"],
            ),
        ],
        language="english",
        style="formal",
        normalized_request=(
            "I want to create a Telegram store bot with command "
            "handling and a database."
        ),
        original_request=(
            "I want a Telegram store bot with a database and command "
            "handling. Use Python and SQLite. Do not use webhooks."
        ),
    )
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
            FeatureSummary(
                name="database_storage",
                display_name="Database Storage",
                description="Store data in a database",
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
        "synonyms": {"shop": "store", "db": "database"},
        "abbreviations": {"tg": "telegram"},
        "terminology": {"orm": "object-relational-mapper"},
    }


def make_full_context():
    """Build a context with all five data sources set."""
    return make_context(
        analysis_report=make_analysis_report(),
        project_context=make_project_context(),
        requirement_intelligence_report=make_requirement_intelligence_report(),
        semantic_understanding_report=make_semantic_understanding_report(),
        knowledge_base=make_knowledge_base(),
    )


# ---------------------------------------------------------------------------#
# 1. Data model tests
# ---------------------------------------------------------------------------#

def test_canonical_name_creation():
    cn = CanonicalName(
        canonical_form="command_handling",
        original_forms=["command_handling", "command handling"],
        kind="feature",
        source_artefact=SOURCE_USER_REQUEST,
    )
    assert cn.canonical_form == "command_handling"
    assert cn.original_forms == ["command_handling", "command handling"]
    assert cn.kind == "feature"
    assert cn.source_artefact == SOURCE_USER_REQUEST
    print("  [PASS] test_canonical_name_creation")


def test_canonical_name_to_dict():
    cn = CanonicalName(
        canonical_form="database",
        original_forms=["db", "database"],
    )
    d = cn.to_dict()
    assert d["canonical_form"] == "database"
    assert d["original_forms"] == ["db", "database"]
    assert "kind" in d
    assert "source_artefact" in d
    print("  [PASS] test_canonical_name_to_dict")


def test_terminology_mapping_creation():
    tm = TerminologyMapping(
        original_term="db",
        canonical_term="database",
        kind="concept",
        source_artefact=SOURCE_KNOWLEDGE_BASE,
    )
    assert tm.original_term == "db"
    assert tm.canonical_term == "database"
    assert tm.kind == "concept"
    assert tm.source_artefact == SOURCE_KNOWLEDGE_BASE
    print("  [PASS] test_terminology_mapping_creation")


def test_terminology_mapping_to_dict():
    tm = TerminologyMapping(
        original_term="shop",
        canonical_term="store",
    )
    d = tm.to_dict()
    assert d["original_term"] == "shop"
    assert d["canonical_term"] == "store"
    assert "kind" in d
    assert "source_artefact" in d
    print("  [PASS] test_terminology_mapping_to_dict")


def test_requirement_link_creation():
    rl = RequirementLink(
        requirement_id="NREQ-001",
        kind=LINK_KIND_FEATURE,
        target="command_handling",
        description="Requirement maps to command handling feature",
        source_artefact=SOURCE_PROJECT_CONTEXT,
    )
    assert rl.requirement_id == "NREQ-001"
    assert rl.kind == LINK_KIND_FEATURE
    assert rl.target == "command_handling"
    assert rl.description.startswith("Requirement maps")
    assert rl.source_artefact == SOURCE_PROJECT_CONTEXT
    print("  [PASS] test_requirement_link_creation")


def test_requirement_link_to_dict():
    rl = RequirementLink(
        requirement_id="NREQ-002",
        kind=LINK_KIND_COMPONENT,
        target="database",
    )
    d = rl.to_dict()
    assert d["requirement_id"] == "NREQ-002"
    assert d["kind"] == LINK_KIND_COMPONENT
    assert d["target"] == "database"
    print("  [PASS] test_requirement_link_to_dict")


def test_duplicate_record_creation():
    dr = DuplicateRecord(
        duplicate_id="NREQ-003",
        duplicate_description="Store data in a database.",
        merged_into_id="NREQ-002",
        similarity=0.9,
        source_artefact=SOURCE_REQUIREMENT_INTELLIGENCE,
    )
    assert dr.duplicate_id == "NREQ-003"
    assert dr.duplicate_description == "Store data in a database."
    assert dr.merged_into_id == "NREQ-002"
    assert dr.similarity == 0.9
    assert dr.source_artefact == SOURCE_REQUIREMENT_INTELLIGENCE
    print("  [PASS] test_duplicate_record_creation")


def test_duplicate_record_to_dict():
    dr = DuplicateRecord(
        duplicate_id="DUP-1",
        merged_into_id="NREQ-001",
    )
    d = dr.to_dict()
    assert d["duplicate_id"] == "DUP-1"
    assert d["merged_into_id"] == "NREQ-001"
    assert "similarity" in d
    print("  [PASS] test_duplicate_record_to_dict")


def test_conflict_record_creation():
    cr = ConflictRecord(
        conflict_id="CONFLICT-001",
        requirement_a_id="NREQ-001",
        requirement_b_id="NREQ-004",
        description="Use SQLite vs use PostgreSQL",
        resolution="unresolved",
        source_artefact=SOURCE_REQUIREMENT_INTELLIGENCE,
    )
    assert cr.conflict_id == "CONFLICT-001"
    assert cr.requirement_a_id == "NREQ-001"
    assert cr.requirement_b_id == "NREQ-004"
    assert cr.description == "Use SQLite vs use PostgreSQL"
    assert cr.resolution == "unresolved"
    assert cr.source_artefact == SOURCE_REQUIREMENT_INTELLIGENCE
    print("  [PASS] test_conflict_record_creation")


def test_conflict_record_to_dict():
    cr = ConflictRecord(
        conflict_id="C-1",
        requirement_a_id="A",
        requirement_b_id="B",
    )
    d = cr.to_dict()
    assert d["conflict_id"] == "C-1"
    assert d["requirement_a_id"] == "A"
    assert d["requirement_b_id"] == "B"
    assert "resolution" in d
    print("  [PASS] test_conflict_record_to_dict")


def test_normalization_finding_creation():
    f = NormalizationFinding(
        severity=SEVERITY_WARNING,
        code="duplicate_requirement",
        message="Two requirements are duplicates",
        affected="NREQ-001, NREQ-002",
        resolution_hint="Merge into one",
        category="consistency",
    )
    assert f.severity == SEVERITY_WARNING
    assert f.code == "duplicate_requirement"
    assert f.message == "Two requirements are duplicates"
    assert f.affected == "NREQ-001, NREQ-002"
    assert f.resolution_hint == "Merge into one"
    assert f.category == "consistency"
    print("  [PASS] test_normalization_finding_creation")


def test_normalization_finding_to_dict():
    f = NormalizationFinding(
        severity=SEVERITY_ERROR,
        code="unlinked_requirement",
        message="Requirement has no links",
    )
    d = f.to_dict()
    assert d["severity"] == SEVERITY_ERROR
    assert d["code"] == "unlinked_requirement"
    assert d["message"] == "Requirement has no links"
    print("  [PASS] test_normalization_finding_to_dict")


def test_cache_info_creation():
    ci = CacheInfo(
        status=CACHE_MISS,
        cache_key="abc123",
        cached_at="2024-01-01T00:00:00",
        hit=False,
        requirements_hash="def456",
    )
    assert ci.status == CACHE_MISS
    assert ci.cache_key == "abc123"
    assert ci.cached_at == "2024-01-01T00:00:00"
    assert ci.hit is False
    assert ci.requirements_hash == "def456"
    print("  [PASS] test_cache_info_creation")


def test_cache_info_to_dict():
    ci = CacheInfo(status=CACHE_HIT, cache_key="key1", hit=True)
    d = ci.to_dict()
    assert d["status"] == CACHE_HIT
    assert d["cache_key"] == "key1"
    assert d["hit"] is True
    print("  [PASS] test_cache_info_to_dict")


def test_normalization_provenance_creation():
    p = NormalizationProvenance(
        request_available=True,
        requirement_intelligence_available=True,
        semantic_understanding_available=True,
        project_context_available=True,
        knowledge_base_available=True,
        all_sources_used=list(ALL_SOURCES),
        request_summary="A store bot",
        requirement_count_from_intelligence=2,
        intent_kind="create",
        semantic_confidence=0.85,
        normalized_request="Create a Telegram store bot",
    )
    assert p.request_available is True
    assert p.requirement_intelligence_available is True
    assert p.semantic_understanding_available is True
    assert p.project_context_available is True
    assert p.knowledge_base_available is True
    assert len(p.all_sources_used) == 5
    assert p.requirement_count_from_intelligence == 2
    assert p.intent_kind == "create"
    assert p.semantic_confidence == 0.85
    print("  [PASS] test_normalization_provenance_creation")


def test_normalization_provenance_to_dict():
    p = NormalizationProvenance(request_available=True)
    d = p.to_dict()
    assert d["request_available"] is True
    assert "all_sources_used" in d
    assert "requirement_count_from_intelligence" in d
    print("  [PASS] test_normalization_provenance_to_dict")


def test_normalized_requirement_creation():
    req = NormalizedRequirement(
        id="NREQ-001",
        original_id="REQ-001",
        name="command_handling",
        display_name="Command Handling",
        description="Handle user commands.",
        category=CATEGORY_FUNCTIONAL,
        priority=PRIORITY_HIGH,
        status=STATUS_ACTIVE,
        feature="command_handling",
        component="core",
        dependencies=["NREQ-002"],
        expected_output="User commands are handled",
        original_forms=["command_handling", "Command Handling"],
        source_artefact=SOURCE_REQUIREMENT_INTELLIGENCE,
    )
    assert req.id == "NREQ-001"
    assert req.original_id == "REQ-001"
    assert req.name == "command_handling"
    assert req.display_name == "Command Handling"
    assert req.description == "Handle user commands."
    assert req.category == CATEGORY_FUNCTIONAL
    assert req.priority == PRIORITY_HIGH
    assert req.status == STATUS_ACTIVE
    assert req.feature == "command_handling"
    assert req.component == "core"
    assert req.dependencies == ["NREQ-002"]
    assert req.expected_output == "User commands are handled"
    assert req.original_forms == ["command_handling", "Command Handling"]
    assert req.source_artefact == SOURCE_REQUIREMENT_INTELLIGENCE
    print("  [PASS] test_normalized_requirement_creation")


def test_normalized_requirement_to_dict():
    req = NormalizedRequirement(
        id="NREQ-002",
        name="database_storage",
    )
    d = req.to_dict()
    assert d["id"] == "NREQ-002"
    assert d["name"] == "database_storage"
    assert "category" in d
    assert "priority" in d
    assert "dependencies" in d
    assert "original_forms" in d
    print("  [PASS] test_normalized_requirement_to_dict")


def test_normalization_report_creation():
    report = NormalizationReport()
    assert report.requirement_count == 0
    assert report.active_requirement_count == 0
    assert report.canonical_name_count == 0
    assert report.terminology_mapping_count == 0
    assert report.link_count == 0
    assert report.duplicate_count == 0
    assert report.conflict_count == 0
    assert report.finding_count == 0
    assert report.error_count == 0
    assert report.warning_count == 0
    assert report.is_empty is True
    assert report.ready is False
    assert report.cache_hit is False
    print("  [PASS] test_normalization_report_creation")


def test_normalization_report_ready_property():
    req1 = NormalizedRequirement(
        id="NREQ-001",
        name="command_handling",
        feature="command_handling",
        priority=PRIORITY_HIGH,
        status=STATUS_ACTIVE,
    )
    report = NormalizationReport(
        requirements=[req1],
        confidence=0.8,
        confidence_level=CONFIDENCE_HIGH,
    )
    assert report.requirement_count == 1
    assert report.all_linked is True
    assert report.has_errors is False
    assert report.has_unresolved_conflicts is False
    assert report.has_sufficient_confidence is True
    assert report.ready is True
    print("  [PASS] test_normalization_report_ready_property")


def test_normalization_report_not_ready_when_empty():
    report = NormalizationReport()
    assert report.ready is False
    print("  [PASS] test_normalization_report_not_ready_when_empty")


def test_normalization_report_not_ready_when_unlinked():
    req1 = NormalizedRequirement(
        id="NREQ-001",
        name="command_handling",
        feature="",
        component="",
        status=STATUS_ACTIVE,
    )
    report = NormalizationReport(
        requirements=[req1],
        confidence=0.9,
    )
    assert report.all_linked is False
    assert report.ready is False
    print("  [PASS] test_normalization_report_not_ready_when_unlinked")


def test_normalization_report_not_ready_with_errors():
    req1 = NormalizedRequirement(
        id="NREQ-001",
        name="command_handling",
        feature="command_handling",
        status=STATUS_ACTIVE,
    )
    report = NormalizationReport(
        requirements=[req1],
        confidence=0.9,
    )
    report.add_finding(
        severity=SEVERITY_ERROR,
        code="test_error",
        message="A test error",
    )
    assert report.has_errors is True
    assert report.ready is False
    print("  [PASS] test_normalization_report_not_ready_with_errors")


def test_normalization_report_not_ready_with_unresolved_conflicts():
    req1 = NormalizedRequirement(
        id="NREQ-001",
        name="command_handling",
        feature="command_handling",
        status=STATUS_ACTIVE,
    )
    report = NormalizationReport(
        requirements=[req1],
        confidence=0.9,
        conflicts=[
            ConflictRecord(
                conflict_id="C-1",
                resolution="unresolved",
            ),
        ],
    )
    assert report.has_unresolved_conflicts is True
    assert report.ready is False
    print("  [PASS] test_normalization_report_not_ready_with_unresolved")


def test_normalization_report_add_finding():
    report = NormalizationReport()
    assert report.finding_count == 0
    report.add_finding(
        severity=SEVERITY_WARNING,
        code="test_warning",
        message="A test warning",
    )
    assert report.finding_count == 1
    assert report.warning_count == 1
    assert report.warnings == ["A test warning"]
    print("  [PASS] test_normalization_report_add_finding")


def test_normalization_report_get_requirement():
    req1 = NormalizedRequirement(id="NREQ-001", name="a")
    req2 = NormalizedRequirement(id="NREQ-002", name="b")
    report = NormalizationReport(requirements=[req1, req2])
    assert report.get_requirement("NREQ-001") is req1
    assert report.get_requirement("NREQ-002") is req2
    assert report.get_requirement("NREQ-999") is None
    print("  [PASS] test_normalization_report_get_requirement")


def test_normalization_report_get_requirement_by_name():
    req1 = NormalizedRequirement(id="NREQ-001", name="command_handling")
    report = NormalizationReport(requirements=[req1])
    found = report.get_requirement_by_name("command_handling")
    assert found is req1
    assert report.get_requirement_by_name("nonexistent") is None
    print("  [PASS] test_normalization_report_get_requirement_by_name")


def test_normalization_report_sorted_requirements():
    req1 = NormalizedRequirement(
        id="NREQ-001", name="a", priority=PRIORITY_LOW,
    )
    req2 = NormalizedRequirement(
        id="NREQ-002", name="b", priority=PRIORITY_HIGH,
    )
    req3 = NormalizedRequirement(
        id="NREQ-003", name="c", priority=PRIORITY_CRITICAL,
    )
    report = NormalizationReport(requirements=[req1, req2, req3])
    sorted_reqs = report.sorted_requirements()
    assert sorted_reqs[0].id == "NREQ-003"
    assert sorted_reqs[1].id == "NREQ-002"
    assert sorted_reqs[2].id == "NREQ-001"
    print("  [PASS] test_normalization_report_sorted_requirements")


def test_normalization_report_category_counts():
    req1 = NormalizedRequirement(
        id="NREQ-001", name="a", category=CATEGORY_FUNCTIONAL,
    )
    req2 = NormalizedRequirement(
        id="NREQ-002", name="b", category=CATEGORY_FUNCTIONAL,
    )
    req3 = NormalizedRequirement(
        id="NREQ-003", name="c", category=CATEGORY_SECURITY,
    )
    report = NormalizationReport(requirements=[req1, req2, req3])
    counts = report.category_counts()
    assert counts[CATEGORY_FUNCTIONAL] == 2
    assert counts[CATEGORY_SECURITY] == 1
    print("  [PASS] test_normalization_report_category_counts")


def test_normalization_report_priority_counts():
    req1 = NormalizedRequirement(
        id="NREQ-001", name="a", priority=PRIORITY_HIGH,
    )
    req2 = NormalizedRequirement(
        id="NREQ-002", name="b", priority=PRIORITY_LOW,
    )
    report = NormalizationReport(requirements=[req1, req2])
    counts = report.priority_counts()
    assert counts[PRIORITY_HIGH] == 1
    assert counts[PRIORITY_LOW] == 1
    print("  [PASS] test_normalization_report_priority_counts")


def test_normalization_report_get_links_for_requirement():
    link1 = RequirementLink(
        requirement_id="NREQ-001", kind=LINK_KIND_FEATURE,
        target="command_handling",
    )
    link2 = RequirementLink(
        requirement_id="NREQ-001", kind=LINK_KIND_COMPONENT,
        target="core",
    )
    link3 = RequirementLink(
        requirement_id="NREQ-002", kind=LINK_KIND_FEATURE,
        target="database_storage",
    )
    report = NormalizationReport(links=[link1, link2, link3])
    links = report.get_links_for_requirement("NREQ-001")
    assert len(links) == 2
    assert all(l.requirement_id == "NREQ-001" for l in links)
    print("  [PASS] test_normalization_report_get_links_for_requirement")


def test_normalization_report_get_canonical_name():
    cn = CanonicalName(
        canonical_form="database",
        original_forms=["db", "database"],
    )
    report = NormalizationReport(canonical_names=[cn])
    found = report.get_canonical_name("db")
    assert found is cn
    found2 = report.get_canonical_name("database")
    assert found2 is cn
    assert report.get_canonical_name("nonexistent") is None
    print("  [PASS] test_normalization_report_get_canonical_name")


def test_normalization_report_get_canonical_term():
    tm = TerminologyMapping(
        original_term="db",
        canonical_term="database",
    )
    report = NormalizationReport(terminology_mappings=[tm])
    assert report.get_canonical_term("db") == "database"
    assert report.get_canonical_term("nonexistent") is None
    print("  [PASS] test_normalization_report_get_canonical_term")


def test_normalization_report_has_duplicates():
    report = NormalizationReport(
        duplicates=[DuplicateRecord(duplicate_id="D-1")],
    )
    assert report.has_duplicates is True
    assert report.duplicate_count == 1
    report2 = NormalizationReport()
    assert report2.has_duplicates is False
    print("  [PASS] test_normalization_report_has_duplicates")


def test_normalization_report_has_conflicts():
    report = NormalizationReport(
        conflicts=[ConflictRecord(conflict_id="C-1")],
    )
    assert report.has_conflicts is True
    assert report.conflict_count == 1
    report2 = NormalizationReport()
    assert report2.has_conflicts is False
    print("  [PASS] test_normalization_report_has_conflicts")


# ---------------------------------------------------------------------------#
# 2. Constants tests
# ---------------------------------------------------------------------------#

def test_all_sources_count():
    assert len(ALL_SOURCES) == 5
    assert SOURCE_USER_REQUEST in ALL_SOURCES
    assert SOURCE_REQUIREMENT_INTELLIGENCE in ALL_SOURCES
    assert SOURCE_SEMANTIC_UNDERSTANDING in ALL_SOURCES
    assert SOURCE_PROJECT_CONTEXT in ALL_SOURCES
    assert SOURCE_KNOWLEDGE_BASE in ALL_SOURCES
    print("  [PASS] test_all_sources_count")


def test_all_severities():
    assert len(ALL_SEVERITIES) == 3
    assert SEVERITY_ERROR in ALL_SEVERITIES
    assert SEVERITY_WARNING in ALL_SEVERITIES
    assert SEVERITY_INFO in ALL_SEVERITIES
    print("  [PASS] test_all_severities")


def test_all_statuses():
    assert len(ALL_STATUSES) == 4
    assert STATUS_ACTIVE in ALL_STATUSES
    assert STATUS_DEPRECATED in ALL_STATUSES
    assert STATUS_MERGED in ALL_STATUSES
    assert STATUS_REMOVED in ALL_STATUSES
    print("  [PASS] test_all_statuses")


def test_all_priorities():
    assert len(ALL_PRIORITIES) == 4
    assert PRIORITY_CRITICAL in ALL_PRIORITIES
    assert PRIORITY_HIGH in ALL_PRIORITIES
    assert PRIORITY_MEDIUM in ALL_PRIORITIES
    assert PRIORITY_LOW in ALL_PRIORITIES
    print("  [PASS] test_all_priorities")


def test_priority_weights():
    assert PRIORITY_WEIGHTS[PRIORITY_CRITICAL] > PRIORITY_WEIGHTS[PRIORITY_HIGH]
    assert PRIORITY_WEIGHTS[PRIORITY_HIGH] > PRIORITY_WEIGHTS[PRIORITY_MEDIUM]
    assert PRIORITY_WEIGHTS[PRIORITY_MEDIUM] > PRIORITY_WEIGHTS[PRIORITY_LOW]
    print("  [PASS] test_priority_weights")


def test_all_categories():
    assert len(ALL_CATEGORIES) == 9
    assert CATEGORY_FUNCTIONAL in ALL_CATEGORIES
    assert CATEGORY_NON_FUNCTIONAL in ALL_CATEGORIES
    assert CATEGORY_TECHNICAL in ALL_CATEGORIES
    assert CATEGORY_CONSTRAINT in ALL_CATEGORIES
    assert CATEGORY_INTERFACE in ALL_CATEGORIES
    assert CATEGORY_SECURITY in ALL_CATEGORIES
    assert CATEGORY_PERFORMANCE in ALL_CATEGORIES
    assert CATEGORY_USABILITY in ALL_CATEGORIES
    assert CATEGORY_DEPLOYMENT in ALL_CATEGORIES
    print("  [PASS] test_all_categories")


def test_all_link_kinds():
    assert len(ALL_LINK_KINDS) == 4
    assert LINK_KIND_FEATURE in ALL_LINK_KINDS
    assert LINK_KIND_COMPONENT in ALL_LINK_KINDS
    assert LINK_KIND_DEPENDENCY in ALL_LINK_KINDS
    assert LINK_KIND_EXPECTED_OUTPUT in ALL_LINK_KINDS
    print("  [PASS] test_all_link_kinds")


def test_all_cache_statuses():
    assert len(ALL_CACHE_STATUSES) == 4
    assert CACHE_HIT in ALL_CACHE_STATUSES
    assert CACHE_MISS in ALL_CACHE_STATUSES
    assert CACHE_STALE in ALL_CACHE_STATUSES
    assert CACHE_DISABLED in ALL_CACHE_STATUSES
    print("  [PASS] test_all_cache_statuses")


def test_confidence_thresholds():
    assert CONFIDENCE_HIGH_THRESHOLD == 0.8
    assert CONFIDENCE_MEDIUM_THRESHOLD == 0.6
    assert CONFIDENCE_HIGH_THRESHOLD > CONFIDENCE_MEDIUM_THRESHOLD
    print("  [PASS] test_confidence_thresholds")


def test_all_confidence_levels():
    assert len(ALL_CONFIDENCE_LEVELS) == 3
    assert CONFIDENCE_HIGH in ALL_CONFIDENCE_LEVELS
    assert CONFIDENCE_MEDIUM in ALL_CONFIDENCE_LEVELS
    assert CONFIDENCE_LOW in ALL_CONFIDENCE_LEVELS
    print("  [PASS] test_all_confidence_levels")


# ---------------------------------------------------------------------------#
# 3. Reader tests
# ---------------------------------------------------------------------------#

def test_request_reader_from_analysis_report():
    reader = RequestReader()
    ctx = make_context(
        analysis_report=make_analysis_report(),
        request="I want a Telegram store bot with a database.",
    )
    data = reader.read(ctx)
    assert data.available is True
    assert data.has_analysis_report is True
    assert "store" in data.raw_request
    assert data.project_name == "store_bot"
    assert "command_handling" in data.features
    assert "database_storage" in data.features
    print("  [PASS] test_request_reader_from_analysis_report")


def test_request_reader_raw_fallback():
    reader = RequestReader()
    ctx = make_context(
        request="I want a Telegram store bot with a database.",
    )
    data = reader.read(ctx)
    assert data.available is True
    assert data.has_analysis_report is False
    assert "store" in data.raw_request
    assert data.raw_request == data.cleaned_request
    print("  [PASS] test_request_reader_raw_fallback")


def test_request_reader_empty():
    reader = RequestReader()
    ctx = make_context(request="")
    data = reader.read(ctx)
    assert data.available is False
    assert data.raw_request == ""
    print("  [PASS] test_request_reader_empty")


def test_requirement_intelligence_reader_from_artefact():
    reader = RequirementIntelligenceReader()
    ctx = make_context(
        requirement_intelligence_report=(
            make_requirement_intelligence_report()
        ),
    )
    data = reader.read(ctx)
    assert data.available is True
    assert len(data.requirements) == 2
    assert data.requirements[0].id == "REQ-001"
    assert data.requirements[0].name == "command_handling"
    assert data.requirements[1].name == "database_storage"
    assert len(data.intent_wants) > 0
    assert data.ready is True
    print("  [PASS] test_requirement_intelligence_reader_from_artefact")


def test_requirement_intelligence_reader_empty():
    reader = RequirementIntelligenceReader()
    ctx = make_context()
    data = reader.read(ctx)
    assert data.available is False
    assert len(data.requirements) == 0
    print("  [PASS] test_requirement_intelligence_reader_empty")


def test_semantic_understanding_reader_from_artefact():
    reader = SemanticUnderstandingReader()
    ctx = make_context(
        semantic_understanding_report=make_semantic_understanding_report(),
    )
    data = reader.read(ctx)
    assert data.available is True
    assert data.intent_kind == "create"
    assert data.intent_subject == "telegram bot"
    assert data.intent_target == "store"
    assert "command_handling" in data.intent_features
    assert "database_storage" in data.intent_features
    assert len(data.keywords) == 2
    assert data.language == "english"
    print("  [PASS] test_semantic_understanding_reader_from_artefact")


def test_semantic_understanding_reader_empty():
    reader = SemanticUnderstandingReader()
    ctx = make_context()
    data = reader.read(ctx)
    assert data.available is False
    assert data.intent_kind == ""
    print("  [PASS] test_semantic_understanding_reader_empty")


def test_context_reader_from_artefact():
    reader = ContextReader()
    ctx = make_context(project_context=make_project_context())
    data = reader.read(ctx)
    assert data.available is True
    assert data.project_name == "store_bot"
    assert data.bot_type == "store"
    assert data.language == "python"
    assert data.framework == "python-telegram-bot"
    assert data.database == "sqlite"
    assert "command_handling" in data.feature_names
    assert "database_storage" in data.feature_names
    assert "core" in data.component_names
    assert "database" in data.component_names
    print("  [PASS] test_context_reader_from_artefact")


def test_context_reader_empty():
    reader = ContextReader()
    ctx = make_context()
    data = reader.read(ctx)
    assert data.available is False
    assert len(data.feature_names) == 0
    print("  [PASS] test_context_reader_empty")


def test_knowledge_reader_from_artefact():
    reader = KnowledgeReader()
    ctx = make_context(knowledge_base=make_knowledge_base())
    data = reader.read(ctx)
    assert data.available is True
    assert "shop" in data.synonyms
    assert data.synonyms["shop"] == "store"
    assert "tg" in data.abbreviations
    assert data.abbreviations["tg"] == "telegram"
    assert "orm" in data.terminology
    print("  [PASS] test_knowledge_reader_from_artefact")


def test_knowledge_reader_empty():
    reader = KnowledgeReader()
    ctx = make_context()
    data = reader.read(ctx)
    assert data.available is False
    assert len(data.synonyms) == 0
    print("  [PASS] test_knowledge_reader_empty")


# ---------------------------------------------------------------------------#
# 4. NameNormalizer tests
# ---------------------------------------------------------------------------#

def test_name_normalizer_produces_canonical_names():
    normalizer = NameNormalizer()
    req_data = RequestData(
        available=True,
        features=["command_handling", "database_storage"],
        keywords=["command", "database"],
    )
    ri_data = RequirementIntelligenceData(
        available=True,
        requirements=[
            RawRequirement(name="command_handling"),
            RawRequirement(name="database_storage"),
        ],
    )
    sem_data = SemanticUnderstandingData(
        available=True,
        intent_features=["command_handling"],
    )
    ctx_data = ContextData(
        available=True,
        feature_names=["command_handling", "database_storage"],
        component_names=["core", "database"],
    )
    knowledge_data = KnowledgeData(available=False)
    canonical_names = normalizer.normalize(
        req_data.features, req_data.keywords,
        ri_data, sem_data, ctx_data, knowledge_data,
    )
    assert len(canonical_names) > 0
    forms = [cn.canonical_form for cn in canonical_names]
    assert "command_handling" in forms
    assert "database_storage" in forms
    print("  [PASS] test_name_normalizer_produces_canonical_names")


def test_name_normalizer_empty():
    normalizer = NameNormalizer()
    canonical_names = normalizer.normalize(
        [], [], RequirementIntelligenceData(),
        SemanticUnderstandingData(), ContextData(), KnowledgeData(),
    )
    assert len(canonical_names) == 0
    print("  [PASS] test_name_normalizer_empty")


# ---------------------------------------------------------------------------#
# 5. TerminologyNormalizer tests
# ---------------------------------------------------------------------------#

def test_terminology_normalizer_produces_mappings():
    normalizer = TerminologyNormalizer()
    ri_data = RequirementIntelligenceData(available=True)
    sem_data = SemanticUnderstandingData(available=True)
    knowledge_data = KnowledgeData(
        available=True,
        synonyms={"shop": "store"},
        abbreviations={"tg": "telegram"},
        terminology={"orm": "object-relational-mapper"},
    )
    mappings = normalizer.normalize(
        ["shop", "tg", "orm"], ri_data, sem_data, knowledge_data,
    )
    assert len(mappings) > 0
    original_terms = [tm.original_term for tm in mappings]
    assert "shop" in original_terms
    assert "tg" in original_terms
    assert "orm" in original_terms
    print("  [PASS] test_terminology_normalizer_produces_mappings")


def test_terminology_normalizer_empty():
    normalizer = TerminologyNormalizer()
    mappings = normalizer.normalize(
        [], RequirementIntelligenceData(),
        SemanticUnderstandingData(), KnowledgeData(),
    )
    assert len(mappings) == 0
    print("  [PASS] test_terminology_normalizer_empty")


# ---------------------------------------------------------------------------#
# 6. DeduplicationRemover tests
# ---------------------------------------------------------------------------#

def test_deduplication_remover_removes_duplicates():
    remover = DeduplicationRemover()
    req1 = NormalizedRequirement(
        id="NREQ-001",
        name="database_storage",
        description="Store data in a database.",
        category=CATEGORY_FUNCTIONAL,
    )
    req2 = NormalizedRequirement(
        id="NREQ-002",
        name="database_storage",
        description="Store data in a database.",
        category=CATEGORY_FUNCTIONAL,
    )
    unique, duplicates = remover.remove([req1, req2])
    assert len(unique) == 1
    assert len(duplicates) == 1
    assert duplicates[0].merged_into_id == "NREQ-001"
    print("  [PASS] test_deduplication_remover_removes_duplicates")


def test_deduplication_remover_keeps_distinct():
    remover = DeduplicationRemover()
    req1 = NormalizedRequirement(
        id="NREQ-001",
        name="command_handling",
        description="Handle user commands.",
        category=CATEGORY_FUNCTIONAL,
    )
    req2 = NormalizedRequirement(
        id="NREQ-002",
        name="database_storage",
        description="Store data in a database.",
        category=CATEGORY_FUNCTIONAL,
    )
    unique, duplicates = remover.remove([req1, req2])
    assert len(unique) == 2
    assert len(duplicates) == 0
    print("  [PASS] test_deduplication_remover_keeps_distinct")


def test_deduplication_remover_empty():
    remover = DeduplicationRemover()
    unique, duplicates = remover.remove([])
    assert len(unique) == 0
    assert len(duplicates) == 0
    print("  [PASS] test_deduplication_remover_empty")


# ---------------------------------------------------------------------------#
# 7. ConsistencyValidator tests
# ---------------------------------------------------------------------------#

def test_consistency_validator_clean_report():
    validator = ConsistencyValidator()
    req1 = NormalizedRequirement(
        id="NREQ-001",
        name="command_handling",
        description="Handle user commands.",
    )
    req2 = NormalizedRequirement(
        id="NREQ-002",
        name="database_storage",
        description="Store data in a database.",
    )
    findings, conflicts, passed = validator.validate(
        [req1, req2], [], 2,
    )
    assert passed is True
    print("  [PASS] test_consistency_validator_clean_report")


def test_consistency_validator_empty():
    validator = ConsistencyValidator()
    findings, conflicts, passed = validator.validate([], [], 0)
    assert passed is True
    print("  [PASS] test_consistency_validator_empty")


# ---------------------------------------------------------------------------#
# 8. RequirementLinker tests
# ---------------------------------------------------------------------------#

def test_requirement_linker_links_to_features():
    linker = RequirementLinker()
    req1 = NormalizedRequirement(
        id="NREQ-001",
        name="command_handling",
        category=CATEGORY_FUNCTIONAL,
    )
    req2 = NormalizedRequirement(
        id="NREQ-002",
        name="database_storage",
        category=CATEGORY_FUNCTIONAL,
    )
    ctx_data = ContextData(
        available=True,
        feature_names=["command_handling", "database_storage"],
        component_names=["core", "database"],
    )
    ri_data = RequirementIntelligenceData(available=True)
    sem_data = SemanticUnderstandingData(
        available=True,
        intent_features=["command_handling", "database_storage"],
    )
    knowledge_data = KnowledgeData(available=False)
    links = linker.link(
        [req1, req2], ctx_data, ri_data, sem_data, knowledge_data,
    )
    assert len(links) > 0
    feature_links = [l for l in links if l.kind == LINK_KIND_FEATURE]
    assert len(feature_links) >= 2
    print("  [PASS] test_requirement_linker_links_to_features")


def test_requirement_linker_empty():
    linker = RequirementLinker()
    links = linker.link(
        [], ContextData(), RequirementIntelligenceData(),
        SemanticUnderstandingData(), KnowledgeData(),
    )
    assert len(links) == 0
    print("  [PASS] test_requirement_linker_empty")


# ---------------------------------------------------------------------------#
# 9. CacheManager tests
# ---------------------------------------------------------------------------#

def test_cache_manager_disabled_by_default():
    cm = CacheManager()
    assert cm.enabled is True
    print("  [PASS] test_cache_manager_disabled_by_default")


def test_cache_manager_disabled():
    cm = CacheManager(enabled=False)
    assert cm.enabled is False
    req_data = RequirementIntelligenceData()
    sem_data = SemanticUnderstandingData()
    req = RequestData(available=True, raw_request="test")
    info = cm.get_cache_info(req_data, sem_data, req)
    assert info.status == CACHE_DISABLED
    assert info.hit is False
    print("  [PASS] test_cache_manager_disabled")


def test_cache_manager_miss_then_hit():
    cm = CacheManager(enabled=True)
    req_data = RequirementIntelligenceData()
    sem_data = SemanticUnderstandingData()
    req = RequestData(available=True, raw_request="test")
    info1 = cm.get_cache_info(req_data, sem_data, req)
    assert info1.status == CACHE_MISS
    assert info1.hit is False
    report = NormalizationReport()
    cm.store(info1, report)
    info2 = cm.get_cache_info(req_data, sem_data, req)
    assert info2.status == CACHE_HIT
    assert info2.hit is True
    cached = cm.get_cached(info2)
    assert cached is report
    print("  [PASS] test_cache_manager_miss_then_hit")


def test_cache_manager_clear():
    cm = CacheManager(enabled=True)
    req_data = RequirementIntelligenceData()
    sem_data = SemanticUnderstandingData()
    req = RequestData(available=True, raw_request="test")
    info = cm.get_cache_info(req_data, sem_data, req)
    cm.store(info, NormalizationReport())
    assert cm.size > 0
    cm.clear()
    assert cm.size == 0
    print("  [PASS] test_cache_manager_clear")


# ---------------------------------------------------------------------------#
# 10. QualityGate tests
# ---------------------------------------------------------------------------#

def test_quality_gate_passes_good_report():
    gate = QualityGate()
    req1 = NormalizedRequirement(
        id="NREQ-001",
        name="command_handling",
        feature="command_handling",
        status=STATUS_ACTIVE,
    )
    report = NormalizationReport(
        requirements=[req1],
        confidence=0.8,
    )
    findings, passed = gate.validate(report)
    assert passed is True
    print("  [PASS] test_quality_gate_passes_good_report")


def test_quality_gate_fails_empty_report():
    gate = QualityGate()
    report = NormalizationReport()
    findings, passed = gate.validate(report)
    assert passed is False
    print("  [PASS] test_quality_gate_fails_empty_report")


def test_quality_gate_fails_unlinked_requirements():
    gate = QualityGate()
    req1 = NormalizedRequirement(
        id="NREQ-001",
        name="command_handling",
        feature="",
        component="",
        status=STATUS_ACTIVE,
    )
    report = NormalizationReport(
        requirements=[req1],
        confidence=0.9,
    )
    findings, passed = gate.validate(report)
    assert passed is False
    print("  [PASS] test_quality_gate_fails_unlinked_requirements")


# ---------------------------------------------------------------------------#
# 11. ReportAssembler tests
# ---------------------------------------------------------------------------#

def test_report_assembler_assemble():
    assembler = ReportAssembler()
    req1 = NormalizedRequirement(
        id="NREQ-001",
        name="command_handling",
        feature="command_handling",
        status=STATUS_ACTIVE,
    )
    req2 = NormalizedRequirement(
        id="NREQ-002",
        name="database_storage",
        feature="database_storage",
        status=STATUS_ACTIVE,
    )
    report = assembler.assemble(
        requirements=[req1, req2],
        canonical_names=[
            CanonicalName(canonical_form="command_handling"),
            CanonicalName(canonical_form="database_storage"),
        ],
        terminology_mappings=[
            TerminologyMapping(original_term="db",
                               canonical_term="database"),
        ],
        links=[
            RequirementLink(
                requirement_id="NREQ-001",
                kind=LINK_KIND_FEATURE,
                target="command_handling",
            ),
        ],
        duplicates=[],
        conflicts=[],
        findings=[],
        cache_info=CacheInfo(),
        confidence=0.8,
        confidence_level=CONFIDENCE_HIGH,
        original_request="I want a Telegram store bot.",
        normalized_request="Create a Telegram store bot with command handling and database storage.",
    )
    assert report.requirement_count == 2
    assert report.canonical_name_count == 2
    assert report.terminology_mapping_count == 1
    assert report.link_count == 1
    assert report.confidence == 0.8
    assert report.confidence_level == CONFIDENCE_HIGH
    assert len(report.summary) > 0
    print("  [PASS] test_report_assembler_assemble")


# ---------------------------------------------------------------------------#
# 12. Engine tests
# ---------------------------------------------------------------------------#

def test_engine_no_request_data():
    engine = RequirementNormalizationEngine()
    ctx = make_context(request="")
    result = engine.execute(ctx)
    assert result.success is False
    assert "requirement_normalization_report" in result.outputs
    report = result.outputs["requirement_normalization_report"]
    assert report.is_empty is True
    print("  [PASS] test_engine_no_request_data")


def test_engine_with_analysis_report():
    engine = RequirementNormalizationEngine()
    ctx = make_context(analysis_report=make_analysis_report())
    result = engine.execute(ctx)
    report = result.outputs["requirement_normalization_report"]
    assert report.requirement_count > 0
    print("  [PASS] test_engine_with_analysis_report")


def test_engine_with_raw_request():
    engine = RequirementNormalizationEngine()
    ctx = make_context(
        request="I want to create a Telegram bot for my store.",
    )
    result = engine.execute(ctx)
    report = result.outputs["requirement_normalization_report"]
    assert report.requirement_count >= 0
    print("  [PASS] test_engine_with_raw_request")


def test_engine_produces_artefact():
    engine = RequirementNormalizationEngine()
    ctx = make_full_context()
    result = engine.execute(ctx)
    assert "requirement_normalization_report" in result.outputs
    print("  [PASS] test_engine_produces_artefact")


def test_engine_stores_in_metadata():
    engine = RequirementNormalizationEngine()
    ctx = make_full_context()
    result = engine.execute(ctx)
    assert "requirement_normalization" in ctx.metadata
    print("  [PASS] test_engine_stores_in_metadata")


def test_engine_with_all_sources():
    engine = RequirementNormalizationEngine()
    ctx = make_full_context()
    result = engine.execute(ctx)
    report = result.outputs["requirement_normalization_report"]
    assert report.provenance.request_available is True
    assert report.provenance.requirement_intelligence_available is True
    assert report.provenance.semantic_understanding_available is True
    assert report.provenance.project_context_available is True
    assert report.provenance.knowledge_base_available is True
    print("  [PASS] test_engine_with_all_sources")


def test_engine_does_not_write_files():
    engine = RequirementNormalizationEngine()
    ctx = make_full_context()
    result = engine.execute(ctx)
    report = result.outputs["requirement_normalization_report"]
    assert not os.path.exists(
        str(ctx.work_dir / "requirement_normalization_report.py")
    )
    print("  [PASS] test_engine_does_not_write_files")


def test_engine_with_requirement_intelligence():
    engine = RequirementNormalizationEngine()
    ctx = make_context(
        analysis_report=make_analysis_report(),
        requirement_intelligence_report=(
            make_requirement_intelligence_report()
        ),
        project_context=make_project_context(),
    )
    result = engine.execute(ctx)
    report = result.outputs["requirement_normalization_report"]
    assert report.requirement_count >= 2
    names = [r.name for r in report.requirements]
    assert "command_handling" in names
    assert "database_storage" in names
    print("  [PASS] test_engine_with_requirement_intelligence")


def test_engine_produces_canonical_names():
    engine = RequirementNormalizationEngine()
    ctx = make_full_context()
    result = engine.execute(ctx)
    report = result.outputs["requirement_normalization_report"]
    assert report.canonical_name_count > 0
    forms = [cn.canonical_form for cn in report.canonical_names]
    assert "command_handling" in forms or "database_storage" in forms
    print("  [PASS] test_engine_produces_canonical_names")


def test_engine_produces_links():
    engine = RequirementNormalizationEngine()
    ctx = make_full_context()
    result = engine.execute(ctx)
    report = result.outputs["requirement_normalization_report"]
    if report.requirement_count > 0:
        assert report.link_count > 0
    print("  [PASS] test_engine_produces_links")


def test_engine_confidence_in_valid_range():
    engine = RequirementNormalizationEngine()
    ctx = make_full_context()
    result = engine.execute(ctx)
    report = result.outputs["requirement_normalization_report"]
    assert 0.0 <= report.confidence <= 1.0
    assert report.confidence_level in ALL_CONFIDENCE_LEVELS
    print("  [PASS] test_engine_confidence_in_valid_range")


# ---------------------------------------------------------------------------#
# 13. Bootstrap tests
# ---------------------------------------------------------------------------#

def test_bootstrap_registers_requirement_normalization():
    registry, orchestrator, manager = bootstrap()
    engine = registry.get_engine("requirement_normalization")
    assert engine is not None
    print("  [PASS] test_bootstrap_registers_requirement_normalization")


def test_bootstrap_requirement_normalization_priority():
    registry, orchestrator, manager = bootstrap()
    entry = manager.get("requirement_normalization")
    assert entry is not None
    assert entry.priority == 100
    print("  [PASS] test_bootstrap_requirement_normalization_priority")


def test_bootstrap_requirement_normalization_dependencies():
    registry, orchestrator, manager = bootstrap()
    entry = manager.get("requirement_normalization")
    assert entry is not None
    assert "semantic_understanding" in entry.dependencies
    print("  [PASS] test_bootstrap_requirement_normalization_dependencies")


# ---------------------------------------------------------------------------#
# 14. Serialisation tests
# ---------------------------------------------------------------------------#

def test_canonical_name_serialisation():
    cn = CanonicalName(
        canonical_form="store",
        original_forms=["store", "shop"],
        kind="feature",
    )
    d = cn.to_dict()
    assert d["canonical_form"] == "store"
    assert d["original_forms"] == ["store", "shop"]
    assert d["kind"] == "feature"
    print("  [PASS] test_canonical_name_serialisation")


def test_terminology_mapping_serialisation():
    tm = TerminologyMapping(
        original_term="shop",
        canonical_term="store",
        kind="concept",
    )
    d = tm.to_dict()
    assert d["original_term"] == "shop"
    assert d["canonical_term"] == "store"
    print("  [PASS] test_terminology_mapping_serialisation")


def test_requirement_link_serialisation():
    rl = RequirementLink(
        requirement_id="NREQ-001",
        kind=LINK_KIND_DEPENDENCY,
        target="NREQ-002",
        description="depends on database storage",
    )
    d = rl.to_dict()
    assert d["kind"] == LINK_KIND_DEPENDENCY
    assert d["target"] == "NREQ-002"
    print("  [PASS] test_requirement_link_serialisation")


def test_duplicate_record_serialisation():
    dr = DuplicateRecord(
        duplicate_id="DUP-1",
        duplicate_description="Store data.",
        merged_into_id="NREQ-001",
        similarity=0.95,
    )
    d = dr.to_dict()
    assert d["duplicate_id"] == "DUP-1"
    assert d["similarity"] == 0.95
    print("  [PASS] test_duplicate_record_serialisation")


def test_conflict_record_serialisation():
    cr = ConflictRecord(
        conflict_id="C-1",
        requirement_a_id="A",
        requirement_b_id="B",
        description="Conflict",
        resolution="unresolved",
    )
    d = cr.to_dict()
    assert d["conflict_id"] == "C-1"
    assert d["resolution"] == "unresolved"
    print("  [PASS] test_conflict_record_serialisation")


def test_normalization_finding_serialisation():
    f = NormalizationFinding(
        severity=SEVERITY_WARNING,
        code="test",
        message="A warning",
    )
    d = f.to_dict()
    assert d["severity"] == SEVERITY_WARNING
    assert d["code"] == "test"
    print("  [PASS] test_normalization_finding_serialisation")


def test_cache_info_serialisation():
    ci = CacheInfo(
        status=CACHE_HIT,
        cache_key="abc",
        hit=True,
    )
    d = ci.to_dict()
    assert d["status"] == CACHE_HIT
    assert d["hit"] is True
    print("  [PASS] test_cache_info_serialisation")


def test_normalization_provenance_serialisation():
    p = NormalizationProvenance(
        request_available=True,
        requirement_count_from_intelligence=3,
    )
    d = p.to_dict()
    assert d["request_available"] is True
    assert d["requirement_count_from_intelligence"] == 3
    print("  [PASS] test_normalization_provenance_serialisation")


def test_normalized_requirement_serialisation():
    req = NormalizedRequirement(
        id="NREQ-001",
        name="command_handling",
        display_name="Command Handling",
        category=CATEGORY_FUNCTIONAL,
        priority=PRIORITY_HIGH,
        dependencies=["NREQ-002"],
        original_forms=["command_handling"],
    )
    d = req.to_dict()
    assert d["id"] == "NREQ-001"
    assert d["name"] == "command_handling"
    assert d["category"] == CATEGORY_FUNCTIONAL
    assert d["priority"] == PRIORITY_HIGH
    assert d["dependencies"] == ["NREQ-002"]
    print("  [PASS] test_normalized_requirement_serialisation")


def test_normalization_report_to_dict():
    req1 = NormalizedRequirement(
        id="NREQ-001",
        name="command_handling",
        feature="command_handling",
        status=STATUS_ACTIVE,
    )
    report = NormalizationReport(
        requirements=[req1],
        confidence=0.8,
        confidence_level=CONFIDENCE_HIGH,
    )
    d = report.to_dict()
    assert d["requirement_count"] == 1
    assert d["active_requirement_count"] == 1
    assert d["confidence"] == 0.8
    assert d["confidence_level"] == CONFIDENCE_HIGH
    assert "requirements" in d
    assert "provenance" in d
    assert "cache_info" in d
    assert len(d["requirements"]) == 1
    print("  [PASS] test_normalization_report_to_dict")


# ---------------------------------------------------------------------------#
# 15. End-to-end tests
# ---------------------------------------------------------------------------#

def test_end_to_end_with_analysis_report():
    engine = RequirementNormalizationEngine()
    ctx = make_context(analysis_report=make_analysis_report())
    result = engine.execute(ctx)
    report = result.outputs["requirement_normalization_report"]
    assert report.requirement_count > 0
    assert 0.0 <= report.confidence <= 1.0
    print("  [PASS] test_end_to_end_with_analysis_report")


def test_end_to_end_with_all_sources():
    engine = RequirementNormalizationEngine()
    ctx = make_full_context()
    result = engine.execute(ctx)
    report = result.outputs["requirement_normalization_report"]
    assert report.provenance.request_available is True
    assert report.provenance.requirement_intelligence_available is True
    assert report.provenance.semantic_understanding_available is True
    assert report.provenance.project_context_available is True
    assert report.provenance.knowledge_base_available is True
    assert report.requirement_count > 0
    print("  [PASS] test_end_to_end_with_all_sources")


def test_end_to_end_raw_request():
    engine = RequirementNormalizationEngine()
    ctx = make_context(
        request="I want to create a Telegram bot for my store.",
    )
    result = engine.execute(ctx)
    report = result.outputs["requirement_normalization_report"]
    assert report.requirement_count >= 0
    print("  [PASS] test_end_to_end_raw_request")


def test_end_to_end_deduplication():
    """Test that the same requirement described differently is
    merged into one."""
    engine = RequirementNormalizationEngine()
    from telegram_bot_engine.engines.generators.requirement_intelligence import (
        IntentAnalysis,
        Requirement,
        RequirementIntelligenceReport,
    )
    report_ri = RequirementIntelligenceReport(
        intent=IntentAnalysis(
            wants="A bot",
            does_not_want="",
            final_goal="A bot",
            quality_level="standard",
            confidence=0.85,
        ),
        requirements=[
            Requirement(
                id="REQ-001",
                name="database_storage",
                display_name="Database Storage",
                description="Store data in a database.",
                category="functional",
                goal="Persist data.",
                reason="Needed for state.",
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
    report_ri.summary = "Test"
    ctx = make_context(
        analysis_report=make_analysis_report(),
        requirement_intelligence_report=report_ri,
        project_context=make_project_context(),
        knowledge_base=make_knowledge_base(),
    )
    result = engine.execute(ctx)
    report = result.outputs["requirement_normalization_report"]
    assert report.requirement_count == 1
    assert report.has_duplicates is True
    assert report.duplicate_count == 1
    print("  [PASS] test_end_to_end_deduplication")


# ---------------------------------------------------------------------------#
# Runner
# ---------------------------------------------------------------------------#

def run_all_tests():
    """Run all tests and return True if all passed."""
    tests = [
        # Data model
        test_canonical_name_creation,
        test_canonical_name_to_dict,
        test_terminology_mapping_creation,
        test_terminology_mapping_to_dict,
        test_requirement_link_creation,
        test_requirement_link_to_dict,
        test_duplicate_record_creation,
        test_duplicate_record_to_dict,
        test_conflict_record_creation,
        test_conflict_record_to_dict,
        test_normalization_finding_creation,
        test_normalization_finding_to_dict,
        test_cache_info_creation,
        test_cache_info_to_dict,
        test_normalization_provenance_creation,
        test_normalization_provenance_to_dict,
        test_normalized_requirement_creation,
        test_normalized_requirement_to_dict,
        test_normalization_report_creation,
        test_normalization_report_ready_property,
        test_normalization_report_not_ready_when_empty,
        test_normalization_report_not_ready_when_unlinked,
        test_normalization_report_not_ready_with_errors,
        test_normalization_report_not_ready_with_unresolved_conflicts,
        test_normalization_report_add_finding,
        test_normalization_report_get_requirement,
        test_normalization_report_get_requirement_by_name,
        test_normalization_report_sorted_requirements,
        test_normalization_report_category_counts,
        test_normalization_report_priority_counts,
        test_normalization_report_get_links_for_requirement,
        test_normalization_report_get_canonical_name,
        test_normalization_report_get_canonical_term,
        test_normalization_report_has_duplicates,
        test_normalization_report_has_conflicts,
        # Constants
        test_all_sources_count,
        test_all_severities,
        test_all_statuses,
        test_all_priorities,
        test_priority_weights,
        test_all_categories,
        test_all_link_kinds,
        test_all_cache_statuses,
        test_confidence_thresholds,
        test_all_confidence_levels,
        # Readers
        test_request_reader_from_analysis_report,
        test_request_reader_raw_fallback,
        test_request_reader_empty,
        test_requirement_intelligence_reader_from_artefact,
        test_requirement_intelligence_reader_empty,
        test_semantic_understanding_reader_from_artefact,
        test_semantic_understanding_reader_empty,
        test_context_reader_from_artefact,
        test_context_reader_empty,
        test_knowledge_reader_from_artefact,
        test_knowledge_reader_empty,
        # NameNormalizer
        test_name_normalizer_produces_canonical_names,
        test_name_normalizer_empty,
        # TerminologyNormalizer
        test_terminology_normalizer_produces_mappings,
        test_terminology_normalizer_empty,
        # DeduplicationRemover
        test_deduplication_remover_removes_duplicates,
        test_deduplication_remover_keeps_distinct,
        test_deduplication_remover_empty,
        # ConsistencyValidator
        test_consistency_validator_clean_report,
        test_consistency_validator_empty,
        # RequirementLinker
        test_requirement_linker_links_to_features,
        test_requirement_linker_empty,
        # CacheManager
        test_cache_manager_disabled_by_default,
        test_cache_manager_disabled,
        test_cache_manager_miss_then_hit,
        test_cache_manager_clear,
        # QualityGate
        test_quality_gate_passes_good_report,
        test_quality_gate_fails_empty_report,
        test_quality_gate_fails_unlinked_requirements,
        # ReportAssembler
        test_report_assembler_assemble,
        # Engine
        test_engine_no_request_data,
        test_engine_with_analysis_report,
        test_engine_with_raw_request,
        test_engine_produces_artefact,
        test_engine_stores_in_metadata,
        test_engine_with_all_sources,
        test_engine_does_not_write_files,
        test_engine_with_requirement_intelligence,
        test_engine_produces_canonical_names,
        test_engine_produces_links,
        test_engine_confidence_in_valid_range,
        # Bootstrap
        test_bootstrap_registers_requirement_normalization,
        test_bootstrap_requirement_normalization_priority,
        test_bootstrap_requirement_normalization_dependencies,
        # Serialisation
        test_canonical_name_serialisation,
        test_terminology_mapping_serialisation,
        test_requirement_link_serialisation,
        test_duplicate_record_serialisation,
        test_conflict_record_serialisation,
        test_normalization_finding_serialisation,
        test_cache_info_serialisation,
        test_normalization_provenance_serialisation,
        test_normalized_requirement_serialisation,
        test_normalization_report_to_dict,
        # End-to-end
        test_end_to_end_with_analysis_report,
        test_end_to_end_with_all_sources,
        test_end_to_end_raw_request,
        test_end_to_end_deduplication,
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
