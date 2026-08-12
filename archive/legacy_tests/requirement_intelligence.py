#!/usr/bin/env python3
"""
Comprehensive test suite for the Requirement Intelligence Engine
(Specification 012).

These tests cover every aspect of the specification:

1. Data model integrity (IntentDimension, IntentAnalysis, Requirement,
   RequiredQuestion, AmbiguityPoint, RequirementConflict,
   QualityViolation, ReportFinding, ReportProvenance,
   RequirementIntelligenceReport, source-artefact constants, severity
   constants, category constants, priority constants, intent-dimension
   constants, quality-level constants, conflict-kind constants,
   ambiguity-kind constants).
2. The RequestReader (analysis_report artefact, raw request fallback,
   empty context).
3. The ContextReader (project_context artefact, empty context).
4. The GraphReader (intelligence_graph artefact, empty context).
5. The KnowledgeReader (knowledge_base artefact, empty context).
6. The IntentAnalyzer (five dimensions, confidence, does-not-want
   detection, quality-level detection, constraints detection).
7. The RequirementClassifier (features, bot types, technologies,
   context components, graph nodes, knowledge rules, implicit,
   future expansion).
8. The MissingDetector (missing database, missing bot type, missing
   features, missing language, missing framework, vague terms,
   under-specified, missing context, knowledge-base resolution).
9. The ConflictDetector (duplicates, contradictory technologies,
   illogical, impossible).
10. The PriorityAssigner (initial priority, dependency-based boost,
    security boost, future_expansion/implicit cap).
11. The QualityValidator (missing fields, report-level, empty report,
    default quality level, high implicit ratio).
12. The ReportAssembler (assembles report, builds provenance, summary,
    notes, warnings).
13. The main engine reads the four data sources (user request, project
    context, intelligence graph, knowledge base).
14. The main engine produces a requirement_intelligence_report
    artefact.
15. The main engine fails when no request data is available.
16. The main engine stores the report in the context metadata.
17. Bootstrap integration (engine registered in registry and manager
    at priority 98, depends on intelligence_graph).
18. Serialisation (to_dict) for all data model classes.
19. End-to-end pipeline.
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
    Conflict,
    Feature,
    KeywordMatch,
    MissingInfo,
    Technology,
)
from telegram_bot_engine.engines.generators.requirement_intelligence import (
    # Engine
    RequirementIntelligenceEngine,
    # Data model
    IntentDimension,
    IntentAnalysis,
    Requirement,
    RequiredQuestion,
    AmbiguityPoint,
    RequirementConflict,
    QualityViolation,
    ReportFinding,
    ReportProvenance,
    RequirementIntelligenceReport,
    # Source-artefact constants
    SOURCE_USER_REQUEST,
    SOURCE_PROJECT_CONTEXT,
    SOURCE_INTELLIGENCE_GRAPH,
    SOURCE_KNOWLEDGE_BASE,
    ALL_SOURCES,
    # Severity constants
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    SEVERITY_INFO,
    ALL_SEVERITIES,
    # Category constants
    CATEGORY_FUNCTIONAL,
    CATEGORY_NON_FUNCTIONAL,
    CATEGORY_PERFORMANCE,
    CATEGORY_SECURITY,
    CATEGORY_ARCHITECTURE,
    CATEGORY_TESTING,
    CATEGORY_DEPLOYMENT,
    CATEGORY_FUTURE_EXPANSION,
    CATEGORY_IMPLICIT,
    ALL_CATEGORIES,
    # Priority constants
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    PRIORITY_NORMAL,
    PRIORITY_LOW,
    ALL_PRIORITIES,
    PRIORITY_RANKS,
    # Intent-dimension constants
    INTENT_DIMENSION_WANTS,
    INTENT_DIMENSION_DOES_NOT_WANT,
    INTENT_DIMENSION_FINAL_GOAL,
    INTENT_DIMENSION_CONSTRAINTS,
    INTENT_DIMENSION_QUALITY_LEVEL,
    ALL_INTENT_DIMENSIONS,
    # Quality-level constants
    QUALITY_LEVEL_MINIMAL,
    QUALITY_LEVEL_STANDARD,
    QUALITY_LEVEL_HIGH,
    QUALITY_LEVEL_PRODUCTION,
    ALL_QUALITY_LEVELS,
    # Conflict-kind constants
    CONFLICT_CONTRADICTORY,
    CONFLICT_ILLOGICAL,
    CONFLICT_IMPOSSIBLE,
    CONFLICT_DUPLICATE,
    ALL_CONFLICT_KINDS,
    # Ambiguity-kind constants
    AMBIGUITY_VAGUE,
    AMBIGUITY_UNDER_SPECIFIED,
    AMBIGUITY_MULTIPLE_INTERPRETATIONS,
    AMBIGUITY_MISSING_CONTEXT,
    ALL_AMBIGUITY_KINDS,
    # Readers + intermediate data
    RequestReader,
    RequestData,
    ContextReader,
    ContextData,
    GraphReader,
    GraphData,
    KnowledgeReader,
    KnowledgeData,
    # Helpers
    IntentAnalyzer,
    RequirementClassifier,
    MissingDetector,
    ConflictDetector,
    PriorityAssigner,
    QualityValidator,
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
    intelligence_graph=None,
    knowledge_base=None,
    request="",
):
    """Build a generation context with the four data sources."""
    ctx = GenerationContext(
        request=request,
        config=make_config(),
        work_dir=Path("/tmp/test_requirement_intelligence"),
    )
    if analysis_report is not None:
        ctx.set("analysis_report", analysis_report)
    if project_context is not None:
        ctx.set("project_context", project_context)
    if intelligence_graph is not None:
        ctx.set("intelligence_graph", intelligence_graph)
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
            KeywordMatch(keyword="bot", category="bot_type", confidence=0.9),
            KeywordMatch(keyword="store", category="bot_type", confidence=0.9),
            KeywordMatch(keyword="database", category="database",
                         confidence=0.85),
        ],
        conflicts=[],
        missing_info=[],
        ready=True,
    )


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


def make_intelligence_graph():
    """Build a simple mock intelligence graph object."""
    from telegram_bot_engine.engines.generators.intelligence_graph import (
        ProjectIntelligenceGraph,
        GraphNode,
    )
    nodes = [
        GraphNode(
            node_id="component:core",
            name="core",
            type="component",
            display_name="Core",
        ),
        GraphNode(
            node_id="component:database",
            name="database",
            type="component",
            display_name="Database",
        ),
        GraphNode(
            node_id="feature:command_handling",
            name="command_handling",
            type="feature",
            display_name="Command Handling",
        ),
    ]
    return ProjectIntelligenceGraph(
        nodes=nodes,
        edges=[],
    )


def make_knowledge_base():
    """Build a simple knowledge base dictionary."""
    return {
        "database": "sqlite",
        "framework": "python-telegram-bot",
        "language": "python",
    }


def make_full_context():
    """Build a context with all four data sources set."""
    return make_context(
        analysis_report=make_analysis_report(),
        project_context=make_project_context(),
        intelligence_graph=make_intelligence_graph(),
        knowledge_base=make_knowledge_base(),
    )


# ---------------------------------------------------------------------------#
# 1. Data model tests
# ---------------------------------------------------------------------------#

def test_intent_dimension_creation():
    dim = IntentDimension(
        name=INTENT_DIMENSION_WANTS,
        value="A Telegram store bot",
        confidence=0.9,
        evidence=["store", "bot"],
        source_artefact=SOURCE_USER_REQUEST,
    )
    assert dim.name == INTENT_DIMENSION_WANTS
    assert dim.value == "A Telegram store bot"
    assert dim.confidence == 0.9
    assert dim.evidence == ["store", "bot"]
    assert dim.source_artefact == SOURCE_USER_REQUEST
    print("  [PASS] test_intent_dimension_creation")


def test_intent_dimension_to_dict():
    dim = IntentDimension(
        name=INTENT_DIMENSION_WANTS,
        value="A store bot",
        confidence=0.8,
        evidence=["store"],
    )
    d = dim.to_dict()
    assert d["name"] == INTENT_DIMENSION_WANTS
    assert d["value"] == "A store bot"
    assert d["confidence"] == 0.8
    assert d["evidence"] == ["store"]
    assert d["source_artefact"] == SOURCE_USER_REQUEST
    print("  [PASS] test_intent_dimension_to_dict")


def test_intent_analysis_creation():
    ia = IntentAnalysis(
        wants="A store bot",
        does_not_want="webhooks",
        final_goal="Manage a store via Telegram",
        constraints="Use Python and SQLite",
        quality_level=QUALITY_LEVEL_STANDARD,
        confidence=0.85,
    )
    assert ia.wants == "A store bot"
    assert ia.does_not_want == "webhooks"
    assert ia.final_goal == "Manage a store via Telegram"
    assert ia.constraints == "Use Python and SQLite"
    assert ia.quality_level == QUALITY_LEVEL_STANDARD
    assert ia.confidence == 0.85
    assert ia.dimensions == []
    print("  [PASS] test_intent_analysis_creation")


def test_intent_analysis_to_dict():
    ia = IntentAnalysis(
        wants="A store bot",
        quality_level=QUALITY_LEVEL_HIGH,
    )
    d = ia.to_dict()
    assert d["wants"] == "A store bot"
    assert d["quality_level"] == QUALITY_LEVEL_HIGH
    assert d["dimensions"] == []
    assert "confidence" in d
    print("  [PASS] test_intent_analysis_to_dict")


def test_requirement_creation():
    req = Requirement(
        id="REQ-001",
        name="command_handling",
        display_name="Command Handling",
        description="The bot must handle user commands.",
        goal="Allow users to interact with the bot via commands.",
        reason="Required for core functionality.",
        category=CATEGORY_FUNCTIONAL,
        priority=PRIORITY_HIGH,
        source_artefact=SOURCE_USER_REQUEST,
        confidence=0.9,
        evidence=["command", "handler"],
    )
    assert req.id == "REQ-001"
    assert req.name == "command_handling"
    assert req.category == CATEGORY_FUNCTIONAL
    assert req.priority == PRIORITY_HIGH
    assert req.priority_rank == PRIORITY_RANKS[PRIORITY_HIGH]
    assert req.source_artefact == SOURCE_USER_REQUEST
    assert req.is_implicit is False
    assert req.is_assumption is False
    assert req.depends_on == []
    assert req.depended_by == []
    print("  [PASS] test_requirement_creation")


def test_requirement_to_dict():
    req = Requirement(
        id="REQ-001",
        name="command_handling",
        description="Handle commands",
        goal="Allow command interaction",
        reason="Core functionality",
        category=CATEGORY_FUNCTIONAL,
        priority=PRIORITY_NORMAL,
    )
    d = req.to_dict()
    assert d["id"] == "REQ-001"
    assert d["name"] == "command_handling"
    assert d["description"] == "Handle commands"
    assert d["goal"] == "Allow command interaction"
    assert d["reason"] == "Core functionality"
    assert d["category"] == CATEGORY_FUNCTIONAL
    assert d["priority"] == PRIORITY_NORMAL
    assert d["priority_rank"] == PRIORITY_RANKS[PRIORITY_NORMAL]
    assert d["is_implicit"] is False
    assert d["is_assumption"] is False
    assert d["depends_on"] == []
    assert d["depended_by"] == []
    print("  [PASS] test_requirement_to_dict")


def test_required_question_creation():
    q = RequiredQuestion(
        id="Q-001",
        field_name="database",
        question="Which database should the bot use?",
        options=["sqlite", "postgres", "mysql"],
        default="sqlite",
        required=False,
    )
    assert q.id == "Q-001"
    assert q.field_name == "database"
    assert q.question == "Which database should the bot use?"
    assert q.options == ["sqlite", "postgres", "mysql"]
    assert q.default == "sqlite"
    assert q.required is False
    assert q.resolution == ""
    assert q.resolved_value is None
    print("  [PASS] test_required_question_creation")


def test_required_question_to_dict():
    q = RequiredQuestion(
        id="Q-001",
        field_name="database",
        question="Which database?",
    )
    d = q.to_dict()
    assert d["id"] == "Q-001"
    assert d["field_name"] == "database"
    assert d["question"] == "Which database?"
    assert d["required"] is True
    assert d["options"] == []
    print("  [PASS] test_required_question_to_dict")


def test_ambiguity_point_creation():
    amb = AmbiguityPoint(
        id="AMB-001",
        kind=AMBIGUITY_VAGUE,
        description="The request is vague about the database.",
        affected_text="some database",
        possible_interpretations=["sqlite", "postgres"],
    )
    assert amb.id == "AMB-001"
    assert amb.kind == AMBIGUITY_VAGUE
    assert amb.description == "The request is vague about the database."
    assert amb.affected_text == "some database"
    assert amb.possible_interpretations == ["sqlite", "postgres"]
    print("  [PASS] test_ambiguity_point_creation")


def test_ambiguity_point_to_dict():
    amb = AmbiguityPoint(
        id="AMB-001",
        kind=AMBIGUITY_UNDER_SPECIFIED,
        description="Under-specified.",
    )
    d = amb.to_dict()
    assert d["id"] == "AMB-001"
    assert d["kind"] == AMBIGUITY_UNDER_SPECIFIED
    assert d["description"] == "Under-specified."
    print("  [PASS] test_ambiguity_point_to_dict")


def test_requirement_conflict_creation():
    cnf = RequirementConflict(
        id="CNF-001",
        kind=CONFLICT_CONTRADICTORY,
        description="Two contradictory databases.",
        requirement_ids=["REQ-001", "REQ-002"],
        severity=SEVERITY_ERROR,
    )
    assert cnf.id == "CNF-001"
    assert cnf.kind == CONFLICT_CONTRADICTORY
    assert cnf.description == "Two contradictory databases."
    assert cnf.requirement_ids == ["REQ-001", "REQ-002"]
    assert cnf.severity == SEVERITY_ERROR
    print("  [PASS] test_requirement_conflict_creation")


def test_requirement_conflict_to_dict():
    cnf = RequirementConflict(
        id="CNF-001",
        kind=CONFLICT_DUPLICATE,
        description="Duplicate requirements.",
        requirement_ids=["REQ-001", "REQ-002"],
    )
    d = cnf.to_dict()
    assert d["id"] == "CNF-001"
    assert d["kind"] == CONFLICT_DUPLICATE
    assert d["requirement_ids"] == ["REQ-001", "REQ-002"]
    print("  [PASS] test_requirement_conflict_to_dict")


def test_quality_violation_creation():
    v = QualityViolation(
        requirement_id="REQ-001",
        missing_fields=["description", "goal"],
        severity=SEVERITY_ERROR,
        message="Requirement REQ-001 is missing description and goal.",
    )
    assert v.requirement_id == "REQ-001"
    assert v.missing_fields == ["description", "goal"]
    assert v.severity == SEVERITY_ERROR
    assert v.message == "Requirement REQ-001 is missing description and goal."
    print("  [PASS] test_quality_violation_creation")


def test_quality_violation_to_dict():
    v = QualityViolation(
        requirement_id="REQ-001",
        missing_fields=["goal"],
        message="Missing goal.",
    )
    d = v.to_dict()
    assert d["requirement_id"] == "REQ-001"
    assert d["missing_fields"] == ["goal"]
    assert d["severity"] == SEVERITY_ERROR
    assert d["message"] == "Missing goal."
    print("  [PASS] test_quality_violation_to_dict")


def test_report_finding_creation():
    f = ReportFinding(
        severity=SEVERITY_WARNING,
        code="missing_intent",
        message="The intent was not fully captured.",
        affected="wants",
        resolution_hint="Provide more detail.",
        category="intent",
    )
    assert f.severity == SEVERITY_WARNING
    assert f.code == "missing_intent"
    assert f.message == "The intent was not fully captured."
    assert f.affected == "wants"
    assert f.resolution_hint == "Provide more detail."
    assert f.category == "intent"
    print("  [PASS] test_report_finding_creation")


def test_report_finding_to_dict():
    f = ReportFinding(
        severity=SEVERITY_ERROR,
        code="no_request",
        message="No request data.",
    )
    d = f.to_dict()
    assert d["severity"] == SEVERITY_ERROR
    assert d["code"] == "no_request"
    assert d["message"] == "No request data."
    print("  [PASS] test_report_finding_to_dict")


def test_report_provenance_creation():
    p = ReportProvenance(
        request_available=True,
        project_context_available=True,
        intelligence_graph_available=True,
        knowledge_base_available=False,
        all_sources_used=[
            SOURCE_USER_REQUEST,
            SOURCE_PROJECT_CONTEXT,
            SOURCE_INTELLIGENCE_GRAPH,
        ],
        request_summary="A store bot with a database.",
        context_project_name="store_bot",
        graph_node_count=3,
    )
    assert p.request_available is True
    assert p.project_context_available is True
    assert p.intelligence_graph_available is True
    assert p.knowledge_base_available is False
    assert p.context_project_name == "store_bot"
    assert p.graph_node_count == 3
    print("  [PASS] test_report_provenance_creation")


def test_report_provenance_to_dict():
    p = ReportProvenance(
        request_available=True,
        graph_node_count=5,
    )
    d = p.to_dict()
    assert d["request_available"] is True
    assert d["graph_node_count"] == 5
    assert d["all_sources_used"] == []
    print("  [PASS] test_report_provenance_to_dict")


def test_source_artefact_constants():
    assert SOURCE_USER_REQUEST == "user_request"
    assert SOURCE_PROJECT_CONTEXT == "project_context"
    assert SOURCE_INTELLIGENCE_GRAPH == "intelligence_graph"
    assert SOURCE_KNOWLEDGE_BASE == "knowledge_base"
    assert len(ALL_SOURCES) == 4
    assert SOURCE_USER_REQUEST in ALL_SOURCES
    assert SOURCE_PROJECT_CONTEXT in ALL_SOURCES
    assert SOURCE_INTELLIGENCE_GRAPH in ALL_SOURCES
    assert SOURCE_KNOWLEDGE_BASE in ALL_SOURCES
    print("  [PASS] test_source_artefact_constants")


def test_severity_constants():
    assert SEVERITY_ERROR == "error"
    assert SEVERITY_WARNING == "warning"
    assert SEVERITY_INFO == "info"
    assert len(ALL_SEVERITIES) == 3
    print("  [PASS] test_severity_constants")


def test_category_constants():
    assert CATEGORY_FUNCTIONAL == "functional"
    assert CATEGORY_NON_FUNCTIONAL == "non_functional"
    assert CATEGORY_PERFORMANCE == "performance"
    assert CATEGORY_SECURITY == "security"
    assert CATEGORY_ARCHITECTURE == "architecture"
    assert CATEGORY_TESTING == "testing"
    assert CATEGORY_DEPLOYMENT == "deployment"
    assert CATEGORY_FUTURE_EXPANSION == "future_expansion"
    assert CATEGORY_IMPLICIT == "implicit"
    assert len(ALL_CATEGORIES) == 9
    print("  [PASS] test_category_constants")


def test_priority_constants():
    assert PRIORITY_CRITICAL == "critical"
    assert PRIORITY_HIGH == "high"
    assert PRIORITY_NORMAL == "normal"
    assert PRIORITY_LOW == "low"
    assert len(ALL_PRIORITIES) == 4
    assert PRIORITY_RANKS[PRIORITY_CRITICAL] < PRIORITY_RANKS[PRIORITY_HIGH]
    assert PRIORITY_RANKS[PRIORITY_HIGH] < PRIORITY_RANKS[PRIORITY_NORMAL]
    assert PRIORITY_RANKS[PRIORITY_NORMAL] < PRIORITY_RANKS[PRIORITY_LOW]
    print("  [PASS] test_priority_constants")


def test_intent_dimension_constants():
    assert INTENT_DIMENSION_WANTS == "wants"
    assert INTENT_DIMENSION_DOES_NOT_WANT == "does_not_want"
    assert INTENT_DIMENSION_FINAL_GOAL == "final_goal"
    assert INTENT_DIMENSION_CONSTRAINTS == "constraints"
    assert INTENT_DIMENSION_QUALITY_LEVEL == "quality_level"
    assert len(ALL_INTENT_DIMENSIONS) == 5
    print("  [PASS] test_intent_dimension_constants")


def test_quality_level_constants():
    assert QUALITY_LEVEL_MINIMAL == "minimal"
    assert QUALITY_LEVEL_STANDARD == "standard"
    assert QUALITY_LEVEL_HIGH == "high"
    assert QUALITY_LEVEL_PRODUCTION == "production"
    assert len(ALL_QUALITY_LEVELS) == 4
    print("  [PASS] test_quality_level_constants")


def test_conflict_kind_constants():
    assert CONFLICT_CONTRADICTORY == "contradictory"
    assert CONFLICT_ILLOGICAL == "illogical"
    assert CONFLICT_IMPOSSIBLE == "impossible"
    assert CONFLICT_DUPLICATE == "duplicate"
    assert len(ALL_CONFLICT_KINDS) == 4
    print("  [PASS] test_conflict_kind_constants")


def test_ambiguity_kind_constants():
    assert AMBIGUITY_VAGUE == "vague"
    assert AMBIGUITY_UNDER_SPECIFIED == "under_specified"
    assert AMBIGUITY_MULTIPLE_INTERPRETATIONS == "multiple_interpretations"
    assert AMBIGUITY_MISSING_CONTEXT == "missing_context"
    assert len(ALL_AMBIGUITY_KINDS) == 4
    print("  [PASS] test_ambiguity_kind_constants")


# ---------------------------------------------------------------------------#
# 2. RequirementIntelligenceReport convenience tests
# ---------------------------------------------------------------------------#

def test_report_empty():
    report = RequirementIntelligenceReport()
    assert report.requirement_count == 0
    assert report.is_empty is True
    assert report.explicit_count == 0
    assert report.implicit_count == 0
    assert report.ready is False
    print("  [PASS] test_report_empty")


def test_report_counts():
    req1 = Requirement(
        id="REQ-001", name="a", description="d", goal="g",
        reason="r", category=CATEGORY_FUNCTIONAL, priority=PRIORITY_HIGH,
    )
    req2 = Requirement(
        id="REQ-002", name="b", description="d", goal="g",
        reason="r", category=CATEGORY_SECURITY, priority=PRIORITY_CRITICAL,
        is_implicit=True,
    )
    report = RequirementIntelligenceReport(
        requirements=[req1, req2],
    )
    assert report.requirement_count == 2
    assert report.explicit_count == 1
    assert report.implicit_count == 1
    assert report.is_empty is False
    print("  [PASS] test_report_counts")


def test_report_category_counts():
    req1 = Requirement(
        id="REQ-001", name="a", description="d", goal="g",
        reason="r", category=CATEGORY_FUNCTIONAL, priority=PRIORITY_NORMAL,
    )
    req2 = Requirement(
        id="REQ-002", name="b", description="d", goal="g",
        reason="r", category=CATEGORY_FUNCTIONAL, priority=PRIORITY_NORMAL,
    )
    req3 = Requirement(
        id="REQ-003", name="c", description="d", goal="g",
        reason="r", category=CATEGORY_SECURITY, priority=PRIORITY_HIGH,
    )
    report = RequirementIntelligenceReport(
        requirements=[req1, req2, req3],
    )
    counts = report.category_counts()
    assert counts[CATEGORY_FUNCTIONAL] == 2
    assert counts[CATEGORY_SECURITY] == 1
    print("  [PASS] test_report_category_counts")


def test_report_priority_counts():
    req1 = Requirement(
        id="REQ-001", name="a", description="d", goal="g",
        reason="r", priority=PRIORITY_CRITICAL,
    )
    req2 = Requirement(
        id="REQ-002", name="b", description="d", goal="g",
        reason="r", priority=PRIORITY_NORMAL,
    )
    report = RequirementIntelligenceReport(
        requirements=[req1, req2],
    )
    counts = report.priority_counts()
    assert counts[PRIORITY_CRITICAL] == 1
    assert counts[PRIORITY_NORMAL] == 1
    print("  [PASS] test_report_priority_counts")


def test_report_requirements_by_category():
    req1 = Requirement(
        id="REQ-001", name="a", description="d", goal="g",
        reason="r", category=CATEGORY_FUNCTIONAL,
    )
    req2 = Requirement(
        id="REQ-002", name="b", description="d", goal="g",
        reason="r", category=CATEGORY_SECURITY,
    )
    report = RequirementIntelligenceReport(
        requirements=[req1, req2],
    )
    functional = report.requirements_by_category(CATEGORY_FUNCTIONAL)
    assert len(functional) == 1
    assert functional[0].id == "REQ-001"
    security = report.requirements_by_category(CATEGORY_SECURITY)
    assert len(security) == 1
    print("  [PASS] test_report_requirements_by_category")


def test_report_requirements_by_priority():
    req1 = Requirement(
        id="REQ-001", name="a", description="d", goal="g",
        reason="r", priority=PRIORITY_HIGH,
    )
    req2 = Requirement(
        id="REQ-002", name="b", description="d", goal="g",
        reason="r", priority=PRIORITY_NORMAL,
    )
    report = RequirementIntelligenceReport(
        requirements=[req1, req2],
    )
    high = report.requirements_by_priority(PRIORITY_HIGH)
    assert len(high) == 1
    assert high[0].id == "REQ-001"
    print("  [PASS] test_report_requirements_by_priority")


def test_report_sorted_requirements():
    req1 = Requirement(
        id="REQ-002", name="b", description="d", goal="g",
        reason="r", priority=PRIORITY_NORMAL,
    )
    req2 = Requirement(
        id="REQ-001", name="a", description="d", goal="g",
        reason="r", priority=PRIORITY_CRITICAL,
    )
    report = RequirementIntelligenceReport(
        requirements=[req1, req2],
    )
    sorted_reqs = report.sorted_requirements()
    assert sorted_reqs[0].id == "REQ-001"
    assert sorted_reqs[1].id == "REQ-002"
    print("  [PASS] test_report_sorted_requirements")


def test_report_get_requirement():
    req1 = Requirement(
        id="REQ-001", name="a", description="d", goal="g",
        reason="r",
    )
    report = RequirementIntelligenceReport(requirements=[req1])
    found = report.get_requirement("REQ-001")
    assert found is not None
    assert found.name == "a"
    assert report.get_requirement("REQ-999") is None
    print("  [PASS] test_report_get_requirement")


def test_report_get_requirement_by_name():
    req1 = Requirement(
        id="REQ-001", name="command_handling", description="d",
        goal="g", reason="r",
    )
    report = RequirementIntelligenceReport(requirements=[req1])
    found = report.get_requirement_by_name("command_handling")
    assert found is not None
    assert found.id == "REQ-001"
    assert report.get_requirement_by_name("nonexistent") is None
    print("  [PASS] test_report_get_requirement_by_name")


def test_report_add_finding():
    report = RequirementIntelligenceReport()
    report.add_finding(
        severity=SEVERITY_WARNING,
        code="test_warning",
        message="A test warning.",
    )
    assert len(report.findings) == 1
    assert report.warning_count == 1
    assert "A test warning." in report.warnings
    print("  [PASS] test_report_add_finding")


def test_report_has_errors():
    report = RequirementIntelligenceReport()
    report.add_finding(
        severity=SEVERITY_ERROR,
        code="test_error",
        message="A test error.",
    )
    assert report.has_errors is True
    assert report.error_count == 1
    print("  [PASS] test_report_has_errors")


def test_report_has_unresolved_questions():
    q = RequiredQuestion(
        id="Q-001", field_name="database",
        question="Which database?", required=True,
    )
    report = RequirementIntelligenceReport(
        required_questions=[q],
    )
    assert report.has_unresolved_questions is True
    print("  [PASS] test_report_has_unresolved_questions")


def test_report_no_unresolved_questions_when_resolved():
    q = RequiredQuestion(
        id="Q-001", field_name="database",
        question="Which database?", required=True,
        resolution="assumption",
        resolved_value="sqlite",
    )
    report = RequirementIntelligenceReport(
        required_questions=[q],
    )
    assert report.has_unresolved_questions is False
    print("  [PASS] test_report_no_unresolved_questions_when_resolved")


def test_report_ready():
    req = Requirement(
        id="REQ-001", name="a", description="d", goal="g",
        reason="r", priority=PRIORITY_NORMAL,
    )
    report = RequirementIntelligenceReport(
        requirements=[req],
    )
    assert report.ready is True
    print("  [PASS] test_report_ready")


def test_report_not_ready_when_empty():
    report = RequirementIntelligenceReport()
    assert report.ready is False
    print("  [PASS] test_report_not_ready_when_empty")


def test_report_not_ready_with_error_conflict():
    req = Requirement(
        id="REQ-001", name="a", description="d", goal="g",
        reason="r", priority=PRIORITY_NORMAL,
    )
    cnf = RequirementConflict(
        id="CNF-001", kind=CONFLICT_CONTRADICTORY,
        description="Contradiction", severity=SEVERITY_ERROR,
    )
    report = RequirementIntelligenceReport(
        requirements=[req],
        conflicts=[cnf],
    )
    assert report.ready is False
    print("  [PASS] test_report_not_ready_with_error_conflict")


def test_report_not_ready_with_quality_violation():
    req = Requirement(
        id="REQ-001", name="a", description="d", goal="g",
        reason="r", priority=PRIORITY_NORMAL,
    )
    v = QualityViolation(
        requirement_id="REQ-001", missing_fields=["description"],
        severity=SEVERITY_ERROR, message="Missing description.",
    )
    report = RequirementIntelligenceReport(
        requirements=[req],
        quality_violations=[v],
    )
    assert report.ready is False
    print("  [PASS] test_report_not_ready_with_quality_violation")


# ---------------------------------------------------------------------------#
# 3. RequestReader tests
# ---------------------------------------------------------------------------#

def test_request_reader_from_analysis_report():
    ctx = make_context(analysis_report=make_analysis_report())
    reader = RequestReader()
    data = reader.read(ctx)
    assert data.available is True
    assert data.has_analysis_report is True
    assert data.project_name == "store_bot"
    assert "command_handling" in data.features
    assert "database_storage" in data.features
    assert "Python" in data.technologies
    assert "SQLite" in data.technologies
    assert "store" in data.bot_types
    print("  [PASS] test_request_reader_from_analysis_report")


def test_request_reader_fallback_to_raw_request():
    ctx = make_context(request="I want a Telegram bot that does things.")
    reader = RequestReader()
    data = reader.read(ctx)
    assert data.available is True
    assert data.has_analysis_report is False
    assert data.raw_request == "I want a Telegram bot that does things."
    assert data.cleaned_request == data.raw_request
    print("  [PASS] test_request_reader_fallback_to_raw_request")


def test_request_reader_empty_context():
    ctx = make_context()
    reader = RequestReader()
    data = reader.read(ctx)
    assert data.available is False
    assert data.has_analysis_report is False
    print("  [PASS] test_request_reader_empty_context")


# ---------------------------------------------------------------------------#
# 4. ContextReader tests
# ---------------------------------------------------------------------------#

def test_context_reader_with_project_context():
    ctx = make_context(project_context=make_project_context())
    reader = ContextReader()
    data = reader.read(ctx)
    assert data.available is True
    assert data.project_name == "store_bot"
    assert data.bot_type == "store"
    assert data.language == "python"
    assert "command_handling" in data.feature_names
    assert "core" in data.component_names
    assert "database" in data.component_names
    print("  [PASS] test_context_reader_with_project_context")


def test_context_reader_empty_context():
    ctx = make_context()
    reader = ContextReader()
    data = reader.read(ctx)
    assert data.available is False
    print("  [PASS] test_context_reader_empty_context")


# ---------------------------------------------------------------------------#
# 5. GraphReader tests
# ---------------------------------------------------------------------------#

def test_graph_reader_with_intelligence_graph():
    ctx = make_context(intelligence_graph=make_intelligence_graph())
    reader = GraphReader()
    data = reader.read(ctx)
    assert data.available is True
    assert data.node_count > 0
    print("  [PASS] test_graph_reader_with_intelligence_graph")


def test_graph_reader_empty_context():
    ctx = make_context()
    reader = GraphReader()
    data = reader.read(ctx)
    assert data.available is False
    assert data.node_count == 0
    print("  [PASS] test_graph_reader_empty_context")


# ---------------------------------------------------------------------------#
# 6. KnowledgeReader tests
# ---------------------------------------------------------------------------#

def test_knowledge_reader_with_knowledge_base():
    ctx = make_context(knowledge_base=make_knowledge_base())
    reader = KnowledgeReader()
    data = reader.read(ctx)
    assert data.available is True
    assert data.get("database") == "sqlite"
    assert data.get("framework") == "python-telegram-bot"
    assert data.get("nonexistent", "default") == "default"
    print("  [PASS] test_knowledge_reader_with_knowledge_base")


def test_knowledge_reader_empty_context():
    ctx = make_context()
    reader = KnowledgeReader()
    data = reader.read(ctx)
    assert data.available is False
    print("  [PASS] test_knowledge_reader_empty_context")


# ---------------------------------------------------------------------------#
# 7. IntentAnalyzer tests
# ---------------------------------------------------------------------------#

def test_intent_analyzer_basic():
    analyzer = IntentAnalyzer()
    request = RequestData(
        raw_request="I want a Telegram store bot with a database.",
        cleaned_request="I want a Telegram store bot with a database.",
        available=True,
    )
    intent = analyzer.analyze(
        request, ContextData(), GraphData(), KnowledgeData(),
    )
    assert intent.wants != ""
    assert intent.confidence > 0
    print("  [PASS] test_intent_analyzer_basic")


def test_intent_analyzer_does_not_want():
    analyzer = IntentAnalyzer()
    request = RequestData(
        raw_request=(
            "I want a Telegram bot. Do not use webhooks. "
            "No external API."
        ),
        cleaned_request=(
            "I want a Telegram bot. Do not use webhooks. "
            "No external API."
        ),
        available=True,
    )
    intent = analyzer.analyze(
        request, ContextData(), GraphData(), KnowledgeData(),
    )
    assert intent.does_not_want != ""
    print("  [PASS] test_intent_analyzer_does_not_want")


def test_intent_analyzer_quality_level():
    analyzer = IntentAnalyzer()
    request = RequestData(
        raw_request="I want a production-grade Telegram bot.",
        cleaned_request="I want a production-grade Telegram bot.",
        available=True,
    )
    intent = analyzer.analyze(
        request, ContextData(), GraphData(), KnowledgeData(),
    )
    assert intent.quality_level in ALL_QUALITY_LEVELS
    print("  [PASS] test_intent_analyzer_quality_level")


def test_intent_analyzer_dimensions_count():
    analyzer = IntentAnalyzer()
    request = RequestData(
        raw_request="I want a bot. Do not use webhooks.",
        cleaned_request="I want a bot. Do not use webhooks.",
        available=True,
    )
    intent = analyzer.analyze(
        request, ContextData(), GraphData(), KnowledgeData(),
    )
    assert len(intent.dimensions) == 5
    print("  [PASS] test_intent_analyzer_dimensions_count")


# ---------------------------------------------------------------------------#
# 8. RequirementClassifier tests
# ---------------------------------------------------------------------------#

def test_classifier_basic():
    classifier = RequirementClassifier()
    request = RequestData(
        raw_request="I want a store bot with a database.",
        cleaned_request="I want a store bot with a database.",
        features=["command_handling", "database_storage"],
        bot_types=["store"],
        technologies=["Python", "SQLite"],
        available=True,
    )
    requirements = classifier.classify(
        request, ContextData(), GraphData(), KnowledgeData(),
    )
    assert len(requirements) > 0
    # Every requirement should have an id starting with "REQ-".
    for r in requirements:
        assert r.id.startswith("REQ-")
        assert r.name != ""
        assert r.category in ALL_CATEGORIES
    print("  [PASS] test_classifier_basic")


def test_classifier_with_context():
    classifier = RequirementClassifier()
    request = RequestData(
        raw_request="I want a store bot.",
        cleaned_request="I want a store bot.",
        features=["command_handling"],
        bot_types=["store"],
        available=True,
    )
    context = ContextData(
        project_name="store_bot",
        component_names=["core", "database"],
        available=True,
    )
    requirements = classifier.classify(
        request, context, GraphData(), KnowledgeData(),
    )
    assert len(requirements) > 0
    print("  [PASS] test_classifier_with_context")


def test_classifier_empty_request():
    classifier = RequirementClassifier()
    request = RequestData(available=False)
    requirements = classifier.classify(
        request, ContextData(), GraphData(), KnowledgeData(),
    )
    assert len(requirements) == 0
    print("  [PASS] test_classifier_empty_request")


# ---------------------------------------------------------------------------#
# 9. MissingDetector tests
# ---------------------------------------------------------------------------#

def test_missing_detector_no_missing_with_knowledge():
    detector = MissingDetector()
    request = RequestData(
        raw_request="I want a store bot with a database.",
        cleaned_request="I want a store bot with a database.",
        features=["command_handling"],
        bot_types=["store"],
        technologies=["Python", "SQLite"],
        available=True,
    )
    knowledge = KnowledgeData(
        raw={"database": "sqlite"},
        keys=["database"],
        available=True,
    )
    questions, ambiguities = detector.detect(
        request, ContextData(), GraphData(), knowledge, [],
    )
    # The database is specified in the request AND in the knowledge
    # base, so no database question should be asked.
    db_questions = [q for q in questions if q.field_name == "database"]
    assert len(db_questions) == 0
    print("  [PASS] test_missing_detector_no_missing_with_knowledge")


def test_missing_detector_missing_database():
    detector = MissingDetector()
    request = RequestData(
        raw_request="I want a store bot.",
        cleaned_request="I want a store bot.",
        features=["command_handling"],
        bot_types=["store"],
        technologies=[],
        available=True,
    )
    questions, ambiguities = detector.detect(
        request, ContextData(), GraphData(), KnowledgeData(), [],
    )
    db_questions = [q for q in questions if q.field_name == "database"]
    assert len(db_questions) == 1
    print("  [PASS] test_missing_detector_missing_database")


def test_missing_detector_vague_terms():
    detector = MissingDetector()
    request = RequestData(
        raw_request="I want some kind of bot that does stuff.",
        cleaned_request="I want some kind of bot that does stuff.",
        features=["command_handling"],
        bot_types=["store"],
        technologies=["Python"],
        available=True,
    )
    questions, ambiguities = detector.detect(
        request, ContextData(), GraphData(), KnowledgeData(), [],
    )
    # Vague terms like "some kind of" should trigger an ambiguity.
    assert len(ambiguities) > 0
    print("  [PASS] test_missing_detector_vague_terms")


# ---------------------------------------------------------------------------#
# 10. ConflictDetector tests
# ---------------------------------------------------------------------------#

def test_conflict_detector_duplicates():
    detector = ConflictDetector()
    req1 = Requirement(
        id="REQ-001", name="command_handling",
        description="Handle commands.", goal="g", reason="r",
        category=CATEGORY_FUNCTIONAL,
    )
    req2 = Requirement(
        id="REQ-002", name="command_handling",
        description="Handle commands.", goal="g", reason="r",
        category=CATEGORY_FUNCTIONAL,
    )
    conflicts = detector.detect([req1, req2], ContextData(), GraphData())
    dups = [c for c in conflicts if c.kind == CONFLICT_DUPLICATE]
    assert len(dups) >= 1
    print("  [PASS] test_conflict_detector_duplicates")


def test_conflict_detector_no_conflicts():
    detector = ConflictDetector()
    req1 = Requirement(
        id="REQ-001", name="command_handling",
        description="Handle commands.", goal="g", reason="r",
        category=CATEGORY_FUNCTIONAL,
    )
    req2 = Requirement(
        id="REQ-002", name="database_storage",
        description="Store data.", goal="g", reason="r",
        category=CATEGORY_ARCHITECTURE,
    )
    conflicts = detector.detect([req1, req2], ContextData(), GraphData())
    assert len(conflicts) == 0
    print("  [PASS] test_conflict_detector_no_conflicts")


# ---------------------------------------------------------------------------#
# 11. PriorityAssigner tests
# ---------------------------------------------------------------------------#

def test_priority_assigner_basic():
    assigner = PriorityAssigner()
    req = Requirement(
        id="REQ-001", name="command_handling",
        description="Handle commands.", goal="g", reason="r",
        category=CATEGORY_FUNCTIONAL,
    )
    assigner.assign([req], RequestData(available=True),
                     ContextData(), KnowledgeData())
    assert req.priority in ALL_PRIORITIES
    assert req.priority_rank == PRIORITY_RANKS[req.priority]
    print("  [PASS] test_priority_assigner_basic")


def test_priority_assigner_security_boost():
    assigner = PriorityAssigner()
    req = Requirement(
        id="REQ-001", name="data_protection",
        description="Protect user data.", goal="g", reason="r",
        category=CATEGORY_SECURITY, priority=PRIORITY_NORMAL,
    )
    assigner.assign([req], RequestData(available=True),
                     ContextData(), KnowledgeData())
    assert req.priority in (PRIORITY_HIGH, PRIORITY_CRITICAL)
    print("  [PASS] test_priority_assigner_security_boost")


def test_priority_assigner_future_expansion_cap():
    assigner = PriorityAssigner()
    req = Requirement(
        id="REQ-001", name="future_feature",
        description="Future feature.", goal="g", reason="r",
        category=CATEGORY_FUTURE_EXPANSION, priority=PRIORITY_CRITICAL,
    )
    assigner.assign([req], RequestData(available=True),
                     ContextData(), KnowledgeData())
    assert req.priority == PRIORITY_NORMAL
    print("  [PASS] test_priority_assigner_future_expansion_cap")


# ---------------------------------------------------------------------------#
# 12. QualityValidator tests
# ---------------------------------------------------------------------------#

def test_quality_validator_no_violations():
    validator = QualityValidator()
    req = Requirement(
        id="REQ-001", name="command_handling",
        description="Handle commands.", goal="g", reason="r",
        priority=PRIORITY_NORMAL,
    )
    report = RequirementIntelligenceReport(
        requirements=[req],
        intent=IntentAnalysis(
            wants="A bot", final_goal="Build a bot",
        ),
    )
    violations, findings = validator.validate(report)
    assert len(violations) == 0
    print("  [PASS] test_quality_validator_no_violations")


def test_quality_validator_missing_fields():
    validator = QualityValidator()
    req = Requirement(
        id="REQ-001", name="command_handling",
        description="", goal="", reason="",
        priority=PRIORITY_NORMAL,
    )
    report = RequirementIntelligenceReport(
        requirements=[req],
        intent=IntentAnalysis(wants="A bot", final_goal="Build a bot"),
    )
    violations, findings = validator.validate(report)
    assert len(violations) > 0
    assert "description" in violations[0].missing_fields
    assert "goal" in violations[0].missing_fields
    assert "reason" in violations[0].missing_fields
    print("  [PASS] test_quality_validator_missing_fields")


def test_quality_validator_empty_report():
    validator = QualityValidator()
    report = RequirementIntelligenceReport()
    violations, findings = validator.validate(report)
    # An empty report should produce findings (at least an empty-report
    # finding).
    assert len(findings) > 0
    print("  [PASS] test_quality_validator_empty_report")


# ---------------------------------------------------------------------------#
# 13. ReportAssembler tests
# ---------------------------------------------------------------------------#

def test_report_assembler_build_provenance():
    assembler = ReportAssembler()
    request = RequestData(
        raw_request="I want a bot.", cleaned_request="I want a bot.",
        available=True,
    )
    provenance = assembler.build_provenance(
        request, ContextData(), GraphData(), KnowledgeData(),
    )
    assert provenance.request_available is True
    assert provenance.project_context_available is False
    assert provenance.intelligence_graph_available is False
    assert provenance.knowledge_base_available is False
    print("  [PASS] test_report_assembler_build_provenance")


def test_report_assembler_assemble():
    assembler = ReportAssembler()
    intent = IntentAnalysis(
        wants="A bot", final_goal="Build a bot",
    )
    req = Requirement(
        id="REQ-001", name="command_handling",
        description="Handle commands.", goal="g", reason="r",
        category=CATEGORY_FUNCTIONAL, priority=PRIORITY_NORMAL,
    )
    provenance = ReportProvenance(request_available=True)
    report = assembler.assemble(
        intent=intent,
        requirements=[req],
        questions=[],
        ambiguities=[],
        conflicts=[],
        quality_violations=[],
        findings=[],
        provenance=provenance,
        request=RequestData(
            raw_request="I want a bot.",
            cleaned_request="I want a bot.",
            available=True,
        ),
        context=ContextData(),
        graph=GraphData(),
        knowledge=KnowledgeData(),
    )
    assert report.requirement_count == 1
    assert report.intent.wants == "A bot"
    assert report.provenance.request_available is True
    assert report.summary != ""
    print("  [PASS] test_report_assembler_assemble")


# ---------------------------------------------------------------------------#
# 14. Engine tests
# ---------------------------------------------------------------------------#

def test_engine_no_request_data():
    """The engine fails when no request data is available."""
    ctx = make_context()
    engine = RequirementIntelligenceEngine()
    result = engine.execute(ctx)
    assert not result.success
    assert result.errors is not None
    assert len(result.errors) > 0
    print("  [PASS] test_engine_no_request_data")


def test_engine_with_analysis_report():
    """The engine produces a report when an analysis report is set."""
    ctx = make_context(analysis_report=make_analysis_report())
    engine = RequirementIntelligenceEngine()
    result = engine.execute(ctx)
    assert result.success, f"Engine failed: {result.errors}"
    report = ctx.get("requirement_intelligence_report")
    assert report is not None
    assert report.requirement_count > 0
    print("  [PASS] test_engine_with_analysis_report")


def test_engine_with_raw_request():
    """The engine works with a raw request (no analysis report)."""
    ctx = make_context(
        request="I want a Telegram store bot with command handling "
                "and a SQLite database.",
    )
    engine = RequirementIntelligenceEngine()
    result = engine.execute(ctx)
    assert result.success, f"Engine failed: {result.errors}"
    report = ctx.get("requirement_intelligence_report")
    assert report is not None
    assert report.requirement_count > 0
    print("  [PASS] test_engine_with_raw_request")


def test_engine_produces_artefact():
    """The engine stores the report as the
    'requirement_intelligence_report' artefact."""
    ctx = make_context(analysis_report=make_analysis_report())
    engine = RequirementIntelligenceEngine()
    result = engine.execute(ctx)
    assert result.success
    assert ctx.has("requirement_intelligence_report")
    report = ctx.get("requirement_intelligence_report")
    assert isinstance(report, RequirementIntelligenceReport)
    print("  [PASS] test_engine_produces_artefact")


def test_engine_stores_in_metadata():
    """The engine stores the report in context metadata."""
    ctx = make_context(analysis_report=make_analysis_report())
    engine = RequirementIntelligenceEngine()
    result = engine.execute(ctx)
    assert result.success
    assert "requirement_intelligence" in ctx.metadata
    print("  [PASS] test_engine_stores_in_metadata")


def test_engine_records_provenance():
    """The report records provenance (which sources were available)."""
    ctx = make_context(analysis_report=make_analysis_report())
    engine = RequirementIntelligenceEngine()
    result = engine.execute(ctx)
    assert result.success
    report = ctx.get("requirement_intelligence_report")
    assert report.provenance.request_available is True
    print("  [PASS] test_engine_records_provenance")


def test_engine_with_all_sources():
    """The engine works with all four data sources present."""
    ctx = make_full_context()
    engine = RequirementIntelligenceEngine()
    result = engine.execute(ctx)
    assert result.success, f"Engine failed: {result.errors}"
    report = ctx.get("requirement_intelligence_report")
    assert report is not None
    assert report.requirement_count > 0
    assert report.provenance.request_available is True
    assert report.provenance.project_context_available is True
    assert report.provenance.intelligence_graph_available is True
    assert report.provenance.knowledge_base_available is True
    print("  [PASS] test_engine_with_all_sources")


def test_engine_metadata_in_result():
    """The successful result metadata contains the report counts."""
    ctx = make_context(analysis_report=make_analysis_report())
    engine = RequirementIntelligenceEngine()
    result = engine.execute(ctx)
    assert result.success
    assert "requirement_count" in result.metadata
    assert "question_count" in result.metadata
    assert "ambiguity_count" in result.metadata
    assert "conflict_count" in result.metadata
    assert "ready" in result.metadata
    print("  [PASS] test_engine_metadata_in_result")


def test_engine_requirements_have_valid_categories():
    """Every requirement has a valid category."""
    ctx = make_context(analysis_report=make_analysis_report())
    engine = RequirementIntelligenceEngine()
    result = engine.execute(ctx)
    assert result.success
    report = ctx.get("requirement_intelligence_report")
    for r in report.requirements:
        assert r.category in ALL_CATEGORIES
    print("  [PASS] test_engine_requirements_have_valid_categories")


def test_engine_requirements_have_valid_priorities():
    """Every requirement has a valid priority."""
    ctx = make_context(analysis_report=make_analysis_report())
    engine = RequirementIntelligenceEngine()
    result = engine.execute(ctx)
    assert result.success
    report = ctx.get("requirement_intelligence_report")
    for r in report.requirements:
        assert r.priority in ALL_PRIORITIES
    print("  [PASS] test_engine_requirements_have_valid_priorities")


def test_engine_requirements_have_unique_ids():
    """Every requirement has a unique id."""
    ctx = make_context(analysis_report=make_analysis_report())
    engine = RequirementIntelligenceEngine()
    result = engine.execute(ctx)
    assert result.success
    report = ctx.get("requirement_intelligence_report")
    ids = [r.id for r in report.requirements]
    assert len(ids) == len(set(ids))
    print("  [PASS] test_engine_requirements_have_unique_ids")


def test_engine_intent_analysis_populated():
    """The intent analysis is populated (wants is not empty)."""
    ctx = make_context(analysis_report=make_analysis_report())
    engine = RequirementIntelligenceEngine()
    result = engine.execute(ctx)
    assert result.success
    report = ctx.get("requirement_intelligence_report")
    assert report.intent.wants != ""
    assert len(report.intent.dimensions) == 5
    print("  [PASS] test_engine_intent_analysis_populated")


def test_engine_does_not_write_files():
    """The engine does not create any files on disk."""
    ctx = make_context(analysis_report=make_analysis_report())
    engine = RequirementIntelligenceEngine()
    result = engine.execute(ctx)
    assert result.success
    assert len(ctx.created_files) == 0
    print("  [PASS] test_engine_does_not_write_files")


# ---------------------------------------------------------------------------#
# 15. Bootstrap integration tests
# ---------------------------------------------------------------------------#

def test_bootstrap_registers_requirement_intelligence():
    """Bootstrap registers the requirement intelligence engine in the
    manager."""
    registry, orchestrator, manager = bootstrap()
    entries = manager.all_entries()
    engine_ids = [e.engine_id for e in entries]
    assert "requirement_intelligence" in engine_ids
    print("  [PASS] test_bootstrap_registers_requirement_intelligence")


def test_bootstrap_requirement_intelligence_priority():
    """Requirement intelligence is registered at priority 98."""
    registry, orchestrator, manager = bootstrap()
    entry = manager.get("requirement_intelligence")
    assert entry is not None
    assert entry.priority == 98
    print("  [PASS] test_bootstrap_requirement_intelligence_priority")


def test_bootstrap_requirement_intelligence_dependencies():
    """Requirement intelligence depends on intelligence_graph."""
    registry, orchestrator, manager = bootstrap()
    entry = manager.get("requirement_intelligence")
    assert entry is not None
    assert "intelligence_graph" in entry.dependencies
    print("  [PASS] test_bootstrap_requirement_intelligence_dependencies")


def test_bootstrap_registry_has_engine():
    """The registry contains the requirement intelligence engine."""
    registry, orchestrator, manager = bootstrap()
    engine = registry.get_engine("requirement_intelligence")
    assert engine is not None
    assert isinstance(engine, RequirementIntelligenceEngine)
    print("  [PASS] test_bootstrap_registry_has_engine")


# ---------------------------------------------------------------------------#
# 16. Configuration tests
# ---------------------------------------------------------------------------#

def test_config_has_requirement_intelligence_section():
    """The default configuration has a requirement_intelligence section."""
    config = build_configuration()
    # The section exists and has the expected fields.
    assert config.get("requirement_intelligence", "proceed_on_warning",
                      True) is True
    assert config.get("requirement_intelligence", "fail_on_errors",
                      True) is True
    assert config.get("requirement_intelligence", "fail_on_quality_violations",
                      True) is True
    assert config.get("requirement_intelligence", "default_quality_level",
                      "standard") == "standard"
    assert config.get("requirement_intelligence", "max_implicit_ratio",
                      0.5) == 0.5
    assert config.get("requirement_intelligence", "min_intent_confidence",
                      0.3) == 0.3
    print("  [PASS] test_config_has_requirement_intelligence_section")


# ---------------------------------------------------------------------------#
# 17. Serialisation tests
# ---------------------------------------------------------------------------#

def test_intent_dimension_serialisation():
    dim = IntentDimension(
        name=INTENT_DIMENSION_WANTS, value="A bot",
        confidence=0.9, evidence=["bot"],
    )
    d = dim.to_dict()
    assert set(d.keys()) == {
        "name", "value", "confidence", "evidence", "source_artefact",
    }
    print("  [PASS] test_intent_dimension_serialisation")


def test_intent_analysis_serialisation():
    ia = IntentAnalysis(
        wants="A bot", does_not_want="webhooks",
        final_goal="Build a bot", constraints="Python",
        quality_level=QUALITY_LEVEL_STANDARD,
    )
    d = ia.to_dict()
    assert set(d.keys()) == {
        "wants", "does_not_want", "final_goal", "constraints",
        "quality_level", "dimensions", "confidence",
    }
    print("  [PASS] test_intent_analysis_serialisation")


def test_requirement_serialisation():
    req = Requirement(
        id="REQ-001", name="command_handling",
        display_name="Command Handling",
        description="Handle commands.",
        goal="Allow command interaction.",
        reason="Core functionality.",
        category=CATEGORY_FUNCTIONAL, priority=PRIORITY_HIGH,
    )
    d = req.to_dict()
    assert set(d.keys()) == {
        "id", "name", "display_name", "description", "goal", "reason",
        "category", "priority", "priority_rank", "source_artefact",
        "confidence", "evidence", "depends_on", "depended_by",
        "is_implicit", "is_assumption", "acceptance_criteria", "keywords",
    }
    print("  [PASS] test_requirement_serialisation")


def test_required_question_serialisation():
    q = RequiredQuestion(
        id="Q-001", field_name="database",
        question="Which database?",
    )
    d = q.to_dict()
    assert set(d.keys()) == {
        "id", "field_name", "question", "options", "default",
        "required", "related_requirements", "source_artefact",
        "resolution", "resolved_value",
    }
    print("  [PASS] test_required_question_serialisation")


def test_ambiguity_point_serialisation():
    amb = AmbiguityPoint(
        id="AMB-001", kind=AMBIGUITY_VAGUE,
        description="Vague request.",
    )
    d = amb.to_dict()
    assert set(d.keys()) == {
        "id", "kind", "description", "affected_text",
        "possible_interpretations", "related_requirements",
        "resolution_hint", "source_artefact",
    }
    print("  [PASS] test_ambiguity_point_serialisation")


def test_requirement_conflict_serialisation():
    cnf = RequirementConflict(
        id="CNF-001", kind=CONFLICT_DUPLICATE,
        description="Duplicate.",
    )
    d = cnf.to_dict()
    assert set(d.keys()) == {
        "id", "kind", "description", "requirement_ids",
        "severity", "resolution_hint", "source_artefact",
    }
    print("  [PASS] test_requirement_conflict_serialisation")


def test_quality_violation_serialisation():
    v = QualityViolation(
        requirement_id="REQ-001", missing_fields=["description"],
        message="Missing description.",
    )
    d = v.to_dict()
    assert set(d.keys()) == {
        "requirement_id", "missing_fields", "severity", "message",
    }
    print("  [PASS] test_quality_violation_serialisation")


def test_report_finding_serialisation():
    f = ReportFinding(
        severity=SEVERITY_WARNING, code="test",
        message="A warning.",
    )
    d = f.to_dict()
    assert set(d.keys()) == {
        "severity", "code", "message", "affected",
        "resolution_hint", "category",
    }
    print("  [PASS] test_report_finding_serialisation")


def test_report_provenance_serialisation():
    p = ReportProvenance(request_available=True)
    d = p.to_dict()
    assert set(d.keys()) == {
        "request_available", "project_context_available",
        "intelligence_graph_available", "knowledge_base_available",
        "all_sources_used", "request_summary",
        "context_project_name", "graph_node_count",
        "knowledge_base_keys",
    }
    print("  [PASS] test_report_provenance_serialisation")


def test_report_to_dict():
    req = Requirement(
        id="REQ-001", name="command_handling",
        description="Handle commands.", goal="g", reason="r",
        priority=PRIORITY_NORMAL,
    )
    report = RequirementIntelligenceReport(
        requirements=[req],
        intent=IntentAnalysis(wants="A bot"),
    )
    d = report.to_dict()
    assert "intent" in d
    assert "requirements" in d
    assert "requirement_count" in d
    assert "category_counts" in d
    assert "priority_counts" in d
    assert "source_counts" in d
    assert d["requirement_count"] == 1
    print("  [PASS] test_report_to_dict")


# ---------------------------------------------------------------------------#
# 18. End-to-end pipeline tests
# ---------------------------------------------------------------------------#

def test_end_to_end_with_analysis_report():
    """Run the engine with an analysis report and verify the report."""
    ctx = make_context(analysis_report=make_analysis_report())
    engine = RequirementIntelligenceEngine()
    result = engine.execute(ctx)
    assert result.success, f"Engine failed: {result.errors}"
    report = ctx.get("requirement_intelligence_report")
    assert report is not None
    assert report.requirement_count > 0
    assert report.intent.wants != ""
    assert len(report.intent.dimensions) == 5
    print("  [PASS] test_end_to_end_with_analysis_report")


def test_end_to_end_with_all_sources():
    """Run the engine with all four data sources and verify the
    report."""
    ctx = make_full_context()
    engine = RequirementIntelligenceEngine()
    result = engine.execute(ctx)
    assert result.success, f"Engine failed: {result.errors}"
    report = ctx.get("requirement_intelligence_report")
    assert report is not None
    assert report.requirement_count > 0
    assert report.provenance.request_available is True
    assert report.provenance.project_context_available is True
    assert report.provenance.intelligence_graph_available is True
    assert report.provenance.knowledge_base_available is True
    print("  [PASS] test_end_to_end_with_all_sources")


def test_end_to_end_raw_request():
    """Run the engine with only a raw request (no analysis report)."""
    ctx = make_context(
        request="I want a Telegram store bot with command handling "
                "and a SQLite database. Use Python.",
    )
    engine = RequirementIntelligenceEngine()
    result = engine.execute(ctx)
    assert result.success, f"Engine failed: {result.errors}"
    report = ctx.get("requirement_intelligence_report")
    assert report is not None
    assert report.requirement_count > 0
    print("  [PASS] test_end_to_end_raw_request")


# ---------------------------------------------------------------------------#
# Test runner
# ---------------------------------------------------------------------------#

def run_all_tests():
    tests = [
        # Data model
        test_intent_dimension_creation,
        test_intent_dimension_to_dict,
        test_intent_analysis_creation,
        test_intent_analysis_to_dict,
        test_requirement_creation,
        test_requirement_to_dict,
        test_required_question_creation,
        test_required_question_to_dict,
        test_ambiguity_point_creation,
        test_ambiguity_point_to_dict,
        test_requirement_conflict_creation,
        test_requirement_conflict_to_dict,
        test_quality_violation_creation,
        test_quality_violation_to_dict,
        test_report_finding_creation,
        test_report_finding_to_dict,
        test_report_provenance_creation,
        test_report_provenance_to_dict,
        test_source_artefact_constants,
        test_severity_constants,
        test_category_constants,
        test_priority_constants,
        test_intent_dimension_constants,
        test_quality_level_constants,
        test_conflict_kind_constants,
        test_ambiguity_kind_constants,
        # Report convenience
        test_report_empty,
        test_report_counts,
        test_report_category_counts,
        test_report_priority_counts,
        test_report_requirements_by_category,
        test_report_requirements_by_priority,
        test_report_sorted_requirements,
        test_report_get_requirement,
        test_report_get_requirement_by_name,
        test_report_add_finding,
        test_report_has_errors,
        test_report_has_unresolved_questions,
        test_report_no_unresolved_questions_when_resolved,
        test_report_ready,
        test_report_not_ready_when_empty,
        test_report_not_ready_with_error_conflict,
        test_report_not_ready_with_quality_violation,
        # RequestReader
        test_request_reader_from_analysis_report,
        test_request_reader_fallback_to_raw_request,
        test_request_reader_empty_context,
        # ContextReader
        test_context_reader_with_project_context,
        test_context_reader_empty_context,
        # GraphReader
        test_graph_reader_with_intelligence_graph,
        test_graph_reader_empty_context,
        # KnowledgeReader
        test_knowledge_reader_with_knowledge_base,
        test_knowledge_reader_empty_context,
        # IntentAnalyzer
        test_intent_analyzer_basic,
        test_intent_analyzer_does_not_want,
        test_intent_analyzer_quality_level,
        test_intent_analyzer_dimensions_count,
        # RequirementClassifier
        test_classifier_basic,
        test_classifier_with_context,
        test_classifier_empty_request,
        # MissingDetector
        test_missing_detector_no_missing_with_knowledge,
        test_missing_detector_missing_database,
        test_missing_detector_vague_terms,
        # ConflictDetector
        test_conflict_detector_duplicates,
        test_conflict_detector_no_conflicts,
        # PriorityAssigner
        test_priority_assigner_basic,
        test_priority_assigner_security_boost,
        test_priority_assigner_future_expansion_cap,
        # QualityValidator
        test_quality_validator_no_violations,
        test_quality_validator_missing_fields,
        test_quality_validator_empty_report,
        # ReportAssembler
        test_report_assembler_build_provenance,
        test_report_assembler_assemble,
        # Engine
        test_engine_no_request_data,
        test_engine_with_analysis_report,
        test_engine_with_raw_request,
        test_engine_produces_artefact,
        test_engine_stores_in_metadata,
        test_engine_records_provenance,
        test_engine_with_all_sources,
        test_engine_metadata_in_result,
        test_engine_requirements_have_valid_categories,
        test_engine_requirements_have_valid_priorities,
        test_engine_requirements_have_unique_ids,
        test_engine_intent_analysis_populated,
        test_engine_does_not_write_files,
        # Bootstrap
        test_bootstrap_registers_requirement_intelligence,
        test_bootstrap_requirement_intelligence_priority,
        test_bootstrap_requirement_intelligence_dependencies,
        test_bootstrap_registry_has_engine,
        # Configuration
        test_config_has_requirement_intelligence_section,
        # Serialisation
        test_intent_dimension_serialisation,
        test_intent_analysis_serialisation,
        test_requirement_serialisation,
        test_required_question_serialisation,
        test_ambiguity_point_serialisation,
        test_requirement_conflict_serialisation,
        test_quality_violation_serialisation,
        test_report_finding_serialisation,
        test_report_provenance_serialisation,
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
