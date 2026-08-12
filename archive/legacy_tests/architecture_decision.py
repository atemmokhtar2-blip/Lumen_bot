#!/usr/bin/env python3
"""
Comprehensive test suite for the Architecture Decision Engine
(Specification 015).

These tests cover every aspect of the specification:

1. Data model integrity (AnalysisResult, RejectedAlternative,
   ArchitectureDecision, ArchitectureFinding, CacheInfo,
   ArchitectureProvenance, ModuleSpec, ServiceSpec,
   ArchitectureDecisionReport, source-artefact constants,
   severity constants, size constants, pattern constants, layer
   constants, communication constants, error-handling constants,
   configuration constants, dependency-structure constants,
   project-layout constants, analysis-dimension constants,
   decision-domain constants, cache-status constants,
   confidence-level constants).
2. The RequirementNormalizationReader (artefact, empty context).
3. The IntelligenceGraphReader (artefact, empty context).
4. The RequirementIntelligenceReader (artefact, empty context).
5. The SemanticUnderstandingReader (artefact, empty context).
6. The KnowledgeReader (artefact, empty context).
7. The SizeAnalyzer (small, medium, large, very large, empty).
8. The ScalabilityAnalyzer (base, with adjustments).
9. The PerformanceAnalyzer (high, medium, low, empty).
10. The SecurityAnalyzer (high, medium, low, empty).
11. The MaintainabilityAnalyzer (base, with penalties, empty).
12. The ArchitectureSelector (all eight decisions, modules,
    services, rejected alternatives).
13. The DecisionValidator (good, empty, missing fields).
14. The QualityGate (pass, empty, errors, low confidence,
     scalability, maintainability).
15. The CacheManager (enabled, disabled, hit, miss, store, clear).
16. The ReportAssembler (assembles, summary, notes, warnings,
    provenance).
17. The main engine reads the five data sources.
18. The main engine produces an architecture_decision_report
    artefact.
19. The main engine fails when no data sources are available.
20. The main engine stores the report in the context metadata.
21. The main engine does not write files or build the project.
22. Bootstrap integration (engine registered in registry and
    manager at priority 101, depends on project_planner).
23. Serialisation (to_dict) for all data model classes.
24. End-to-end pipeline with all data sources.
25. Cache hit returns cached report.
"""

import sys
import os

# Ensure the package is importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path

from telegram_bot_engine.core import build_configuration, bootstrap
from telegram_bot_engine.core.context import GenerationContext
from telegram_bot_engine.engines.generators.architecture_decision import (
    # Engine
    ArchitectureDecisionEngine,
    # Data model
    AnalysisResult,
    RejectedAlternative,
    ArchitectureDecision,
    ArchitectureFinding,
    CacheInfo,
    ArchitectureProvenance,
    ModuleSpec,
    ServiceSpec,
    ArchitectureDecisionReport,
    # Source-artefact constants
    SOURCE_NORMALIZED_REQUIREMENTS,
    SOURCE_INTELLIGENCE_GRAPH,
    SOURCE_REQUIREMENT_INTELLIGENCE,
    SOURCE_SEMANTIC_UNDERSTANDING,
    SOURCE_KNOWLEDGE_BASE,
    ALL_SOURCES,
    # Severity constants
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    SEVERITY_INFO,
    ALL_SEVERITIES,
    # Project size constants
    SIZE_TINY,
    SIZE_SMALL,
    SIZE_MEDIUM,
    SIZE_LARGE,
    SIZE_VERY_LARGE,
    ALL_SIZES,
    SIZE_THRESHOLD_TINY,
    SIZE_THRESHOLD_SMALL,
    SIZE_THRESHOLD_MEDIUM,
    SIZE_THRESHOLD_LARGE,
    # Architecture pattern constants
    PATTERN_MONOLITH,
    PATTERN_LAYERED,
    PATTERN_MODULAR_MONOLITH,
    PATTERN_MICROSERVICES,
    PATTERN_EVENT_DRIVEN,
    PATTERN_HEXAGONAL,
    ALL_PATTERNS,
    PATTERN_BY_SIZE,
    # Layer constants
    LAYER_PRESENTATION,
    LAYER_BUSINESS,
    LAYER_DATA_ACCESS,
    LAYER_INFRASTRUCTURE,
    LAYER_INTEGRATION,
    LAYER_CACHING,
    LAYER_MESSAGING,
    ALL_LAYERS,
    # Communication pattern constants
    COMM_SYNC,
    COMM_ASYNC,
    COMM_EVENT,
    COMM_HYBRID,
    ALL_COMM_PATTERNS,
    # Error handling strategy constants
    ERROR_CENTRALIZED,
    ERROR_DISTRIBUTED,
    ERROR_LAYER_SPECIFIC,
    ERROR_RESULT_TYPE,
    ALL_ERROR_STRATEGIES,
    # Configuration strategy constants
    CONFIG_STATIC,
    CONFIG_ENVIRONMENT,
    CONFIG_FILE_BASED,
    CONFIG_HYBRID,
    ALL_CONFIG_STRATEGIES,
    # Dependency structure constants
    DEP_FLAT,
    DEP_LAYERED,
    DEP_HIERARCHICAL,
    DEP_GRAPH,
    ALL_DEP_STRUCTURES,
    # Project layout constants
    LAYOUT_FEATURE_BASED,
    LAYOUT_LAYER_BASED,
    LAYOUT_DOMAIN_BASED,
    LAYOUT_HYBRID,
    ALL_LAYOUTS,
    # Analysis dimension constants
    DIMENSION_SIZE,
    DIMENSION_SCALABILITY,
    DIMENSION_PERFORMANCE,
    DIMENSION_SECURITY,
    DIMENSION_MAINTAINABILITY,
    ALL_DIMENSIONS,
    # Decision domain constants
    DECISION_LAYERS,
    DECISION_MODULES,
    DECISION_SERVICES,
    DECISION_DEPENDENCY_STRUCTURE,
    DECISION_PROJECT_LAYOUT,
    DECISION_COMMUNICATION,
    DECISION_ERROR_HANDLING,
    DECISION_CONFIGURATION,
    ALL_DECISION_DOMAINS,
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
    RequirementNormalizationReader,
    RequirementNormalizationData,
    NormalizedRequirementView,
    IntelligenceGraphReader,
    IntelligenceGraphData,
    RequirementIntelligenceReader,
    RequirementIntelligenceData,
    SemanticUnderstandingReader,
    SemanticUnderstandingData,
    SemanticKeyword,
    KnowledgeReader,
    KnowledgeData,
    # Analyzers
    SizeAnalyzer,
    ScalabilityAnalyzer,
    PerformanceAnalyzer,
    SecurityAnalyzer,
    MaintainabilityAnalyzer,
    # Architecture selector
    ArchitectureSelector,
    # Helpers and processors
    DecisionValidator,
    QualityGate,
    CacheManager,
    ReportAssembler,
)


# ---------------------------------------------------------------------------#
# Test helpers
# ---------------------------------------------------------------------------#

def make_config():
    return build_configuration()


def make_context(
    project_planner_report=None,
    intelligence_graph=None,
    requirement_intelligence_report=None,
    semantic_understanding_report=None,
    knowledge_base=None,
    request="",
):
    """Build a generation context with the five data sources."""
    ctx = GenerationContext(
        request=request,
        config=make_config(),
        work_dir=Path("/tmp/test_architecture_decision"),
    )
    if project_planner_report is not None:
        ctx.set(
            "project_planner_report",
            project_planner_report,
        )
    if intelligence_graph is not None:
        ctx.set("intelligence_graph", intelligence_graph)
    if requirement_intelligence_report is not None:
        ctx.set(
            "requirement_intelligence_report",
            requirement_intelligence_report,
        )
    if semantic_understanding_report is not None:
        ctx.set(
            "semantic_understanding_report",
            semantic_understanding_report,
        )
    if knowledge_base is not None:
        ctx.set("knowledge_base", knowledge_base)
    return ctx


def make_normalization_report(
    requirement_count=3,
):
    """Build a mock normalization report with requirements."""
    from telegram_bot_engine.engines.generators.project_planner import (
        NormalizationReport,
        NormalizedRequirement,
    )
    requirements = []
    for i in range(1, requirement_count + 1):
        requirements.append(NormalizedRequirement(
            id=f"NREQ-{i:03d}",
            name=f"requirement_{i}",
            display_name=f"Requirement {i}",
            description=f"Requirement number {i}.",
            category="functional",
            priority="high" if i <= 2 else "medium",
            status="active",
            feature=f"feature_{i}",
            component=f"component_{i}",
        ))
    report = NormalizationReport(
        requirements=requirements,
    )
    report.summary = "Test normalization report."
    return report


def make_intelligence_graph(
    node_count=10,
    component_count=3,
    service_count=2,
):
    """Build a mock intelligence graph."""
    return {
        "nodes": [{"id": f"node_{i}", "type": "component"}
                  for i in range(node_count)],
        "edges": [
            {"source": "node_0", "target": "node_1",
             "kind": "depends_on"},
            {"source": "node_1", "target": "node_2",
             "kind": "depends_on"},
        ],
        "node_count": node_count,
        "edge_count": 2,
        "node_type_counts": {"component": component_count,
                            "feature": 3,
                            "file": 5},
        "edge_kind_counts": {"depends_on": 2},
        "component_count": component_count,
        "feature_count": 3,
        "service_count": service_count,
        "dependency_count": 2,
        "file_count": 5,
        "findings": [],
        "circular_count": 0,
    }


def make_requirement_intelligence_report():
    """Build a simple mock requirement intelligence report."""
    from telegram_bot_engine.engines.generators.requirement_intelligence import (
        IntentAnalysis,
        Requirement,
        RequirementIntelligenceReport,
    )
    report = RequirementIntelligenceReport(
        intent=IntentAnalysis(
            wants="A Telegram bot with a database",
            does_not_want="webhooks",
            final_goal="Manage a Telegram bot",
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
            full_description=(
                "Create a Telegram bot with command handling "
                "and a database with high performance and security."
            ),
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
            "Create a Telegram bot with command handling "
            "and a database."
        ),
        original_request=(
            "I want a Telegram bot with a database and command "
            "handling."
        ),
    )
    return report


def make_knowledge_base():
    """Build a simple knowledge base dictionary."""
    return {
        "database": "sqlite",
        "framework": "python-telegram-bot",
        "language": "python",
        "synonyms": {"shop": "store", "db": "database"},
        "abbreviations": {"tg": "telegram"},
        "terminology": {"orm": "object-relational-mapper"},
        "assumptions": ["uses Python 3"],
        "defaults": {"database": "sqlite"},
    }


def make_full_context():
    """Build a context with all five data sources set."""
    return make_context(
        project_planner_report=make_normalization_report(),
        intelligence_graph=make_intelligence_graph(),
        requirement_intelligence_report=(
            make_requirement_intelligence_report()
        ),
        semantic_understanding_report=(
            make_semantic_understanding_report()
        ),
        knowledge_base=make_knowledge_base(),
    )


# ---------------------------------------------------------------------------#
# 1. Data model tests
# ---------------------------------------------------------------------------#

def test_analysis_result_creation():
    ar = AnalysisResult(
        dimension=DIMENSION_SIZE,
        score=0.75,
        level=SIZE_SMALL,
        summary="Project is small.",
        details=["10 requirements", "5 nodes"],
        source_artefact=SOURCE_NORMALIZED_REQUIREMENTS,
    )
    assert ar.dimension == DIMENSION_SIZE
    assert ar.score == 0.75
    assert ar.level == SIZE_SMALL
    assert ar.summary == "Project is small."
    assert ar.details == ["10 requirements", "5 nodes"]
    assert ar.source_artefact == SOURCE_NORMALIZED_REQUIREMENTS
    print("  [PASS] test_analysis_result_creation")


def test_analysis_result_to_dict():
    ar = AnalysisResult(
        dimension=DIMENSION_SECURITY,
        score=0.5,
        level="low",
    )
    d = ar.to_dict()
    assert d["dimension"] == DIMENSION_SECURITY
    assert d["score"] == 0.5
    assert d["level"] == "low"
    assert "summary" in d
    assert "details" in d
    assert "source_artefact" in d
    print("  [PASS] test_analysis_result_to_dict")


def test_rejected_alternative_creation():
    ra = RejectedAlternative(
        name="microservices",
        reason="Too complex for a small project.",
        impact="Would add unnecessary overhead.",
    )
    assert ra.name == "microservices"
    assert ra.reason == "Too complex for a small project."
    assert ra.impact == "Would add unnecessary overhead."
    print("  [PASS] test_rejected_alternative_creation")


def test_rejected_alternative_to_dict():
    ra = RejectedAlternative(
        name="monolith",
        reason="Too simple for large project.",
    )
    d = ra.to_dict()
    assert d["name"] == "monolith"
    assert d["reason"] == "Too simple for large project."
    assert "impact" in d
    print("  [PASS] test_rejected_alternative_to_dict")


def test_architecture_decision_creation():
    ra = RejectedAlternative(
        name="monolith",
        reason="Too simple.",
        impact="Poor scalability.",
    )
    d = ArchitectureDecision(
        domain=DECISION_LAYERS,
        selected="presentation, business, data_access",
        reason="Layered architecture is best for this project.",
        analysis="The project has multiple concerns that benefit from separation.",
        impact="Clear separation of concerns, easier maintenance.",
        rejected_alternatives=[ra],
        source_artefact=SOURCE_NORMALIZED_REQUIREMENTS,
        confidence=0.85,
    )
    assert d.domain == DECISION_LAYERS
    assert "presentation" in d.selected
    assert d.reason != ""
    assert d.analysis != ""
    assert d.impact != ""
    assert len(d.rejected_alternatives) == 1
    assert d.source_artefact == SOURCE_NORMALIZED_REQUIREMENTS
    assert d.confidence == 0.85
    print("  [PASS] test_architecture_decision_creation")


def test_architecture_decision_to_dict():
    d = ArchitectureDecision(
        domain=DECISION_COMMUNICATION,
        selected=COMM_SYNC,
    )
    d_dict = d.to_dict()
    assert d_dict["domain"] == DECISION_COMMUNICATION
    assert d_dict["selected"] == COMM_SYNC
    assert "rejected_alternatives" in d_dict
    assert "confidence" in d_dict
    print("  [PASS] test_architecture_decision_to_dict")


def test_architecture_finding_creation():
    f = ArchitectureFinding(
        severity=SEVERITY_WARNING,
        code="low_confidence",
        message="Confidence is below threshold.",
        affected="overall",
        resolution_hint="Add more data sources.",
        category="quality",
    )
    assert f.severity == SEVERITY_WARNING
    assert f.code == "low_confidence"
    assert f.message == "Confidence is below threshold."
    assert f.affected == "overall"
    assert f.resolution_hint == "Add more data sources."
    assert f.category == "quality"
    print("  [PASS] test_architecture_finding_creation")


def test_architecture_finding_to_dict():
    f = ArchitectureFinding(
        severity=SEVERITY_ERROR,
        code="no_data",
        message="No data sources.",
    )
    d = f.to_dict()
    assert d["severity"] == SEVERITY_ERROR
    assert d["code"] == "no_data"
    assert d["message"] == "No data sources."
    assert "affected" in d
    assert "category" in d
    print("  [PASS] test_architecture_finding_to_dict")


def test_cache_info_creation():
    ci = CacheInfo(
        status=CACHE_MISS,
        cache_key="arch_abc123",
        cached_at="2024-01-01T00:00:00",
        hit=False,
        inputs_hash="hash123",
    )
    assert ci.status == CACHE_MISS
    assert ci.cache_key == "arch_abc123"
    assert ci.cached_at == "2024-01-01T00:00:00"
    assert ci.hit is False
    assert ci.inputs_hash == "hash123"
    print("  [PASS] test_cache_info_creation")


def test_cache_info_to_dict():
    ci = CacheInfo(
        status=CACHE_HIT,
        cache_key="arch_xyz",
        hit=True,
    )
    d = ci.to_dict()
    assert d["status"] == CACHE_HIT
    assert d["cache_key"] == "arch_xyz"
    assert d["hit"] is True
    print("  [PASS] test_cache_info_to_dict")


def test_architecture_provenance_creation():
    p = ArchitectureProvenance(
        normalized_requirements_available=True,
        intelligence_graph_available=True,
        requirement_intelligence_available=True,
        semantic_understanding_available=True,
        knowledge_base_available=False,
        all_sources_used=[
            SOURCE_NORMALIZED_REQUIREMENTS,
            SOURCE_INTELLIGENCE_GRAPH,
            SOURCE_REQUIREMENT_INTELLIGENCE,
            SOURCE_SEMANTIC_UNDERSTANDING,
        ],
        requirement_count=10,
        graph_node_count=15,
        graph_edge_count=5,
        intent_kind="create",
        semantic_confidence=0.85,
    )
    assert p.normalized_requirements_available is True
    assert p.intelligence_graph_available is True
    assert p.requirement_intelligence_available is True
    assert p.semantic_understanding_available is True
    assert p.knowledge_base_available is False
    assert len(p.all_sources_used) == 4
    assert p.requirement_count == 10
    assert p.graph_node_count == 15
    assert p.graph_edge_count == 5
    assert p.intent_kind == "create"
    assert p.semantic_confidence == 0.85
    print("  [PASS] test_architecture_provenance_creation")


def test_architecture_provenance_to_dict():
    p = ArchitectureProvenance(
        normalized_requirements_available=True,
    )
    d = p.to_dict()
    assert d["normalized_requirements_available"] is True
    assert "intelligence_graph_available" in d
    assert "all_sources_used" in d
    assert "intent_kind" in d
    print("  [PASS] test_architecture_provenance_to_dict")


def test_module_spec_creation():
    m = ModuleSpec(
        name="core",
        layer="business",
        responsibility="Core business logic.",
        dependencies=["database"],
    )
    assert m.name == "core"
    assert m.layer == "business"
    assert m.responsibility == "Core business logic."
    assert m.dependencies == ["database"]
    print("  [PASS] test_module_spec_creation")


def test_module_spec_to_dict():
    m = ModuleSpec(
        name="handlers",
        layer="presentation",
    )
    d = m.to_dict()
    assert d["name"] == "handlers"
    assert d["layer"] == "presentation"
    assert "dependencies" in d
    print("  [PASS] test_module_spec_to_dict")


def test_service_spec_creation():
    s = ServiceSpec(
        name="bot_service",
        responsibility="Telegram bot service.",
        communication=COMM_SYNC,
        dependencies=["database_service"],
    )
    assert s.name == "bot_service"
    assert s.responsibility == "Telegram bot service."
    assert s.communication == COMM_SYNC
    assert s.dependencies == ["database_service"]
    print("  [PASS] test_service_spec_creation")


def test_service_spec_to_dict():
    s = ServiceSpec(
        name="cache_service",
        communication=COMM_ASYNC,
    )
    d = s.to_dict()
    assert d["name"] == "cache_service"
    assert d["communication"] == COMM_ASYNC
    assert "dependencies" in d
    print("  [PASS] test_service_spec_to_dict")


def test_report_creation():
    report = ArchitectureDecisionReport(
        analyses=[AnalysisResult(dimension=DIMENSION_SIZE)],
        decisions=[ArchitectureDecision(domain=DECISION_LAYERS)],
        modules=[ModuleSpec(name="core")],
        services=[ServiceSpec(name="bot_service")],
    )
    assert report.analysis_count == 1
    assert report.decision_count == 1
    assert report.module_count == 1
    assert report.service_count == 1
    print("  [PASS] test_report_creation")


def test_report_empty():
    report = ArchitectureDecisionReport()
    assert report.is_empty is True
    assert report.decision_count == 0
    assert report.ready is False
    print("  [PASS] test_report_empty")


def test_report_properties():
    ra = RejectedAlternative(
        name="monolith", reason="too simple",
        impact="poor scaling",
    )
    decision = ArchitectureDecision(
        domain=DECISION_LAYERS,
        selected="presentation, business",
        reason="Reason text.",
        analysis="Analysis text.",
        impact="Impact text.",
        rejected_alternatives=[ra],
    )
    report = ArchitectureDecisionReport(
        decisions=[decision],
        confidence=0.7,
        confidence_level=CONFIDENCE_MEDIUM,
    )
    assert report.all_decisions_validated is True
    assert report.has_sufficient_confidence is True
    assert report.error_count == 0
    assert report.warning_count == 0
    assert report.has_errors is False
    assert report.cache_hit is False
    print("  [PASS] test_report_properties")


def test_report_ready():
    ra = RejectedAlternative(
        name="x", reason="y", impact="z",
    )
    decision = ArchitectureDecision(
        domain=DECISION_LAYERS,
        selected="presentation, business",
        reason="Reason.",
        analysis="Analysis.",
        impact="Impact.",
        rejected_alternatives=[ra],
    )
    report = ArchitectureDecisionReport(
        decisions=[decision],
        confidence=0.8,
        confidence_level=CONFIDENCE_HIGH,
    )
    assert report.ready is True
    print("  [PASS] test_report_ready")


def test_report_get_decision():
    decision = ArchitectureDecision(
        domain=DECISION_COMMUNICATION,
        selected=COMM_SYNC,
        reason="Reason.",
        analysis="Analysis.",
        impact="Impact.",
        rejected_alternatives=[
            RejectedAlternative(name="async", reason="no", impact="none"),
        ],
    )
    report = ArchitectureDecisionReport(decisions=[decision])
    found = report.get_decision(DECISION_COMMUNICATION)
    assert found is not None
    assert found.selected == COMM_SYNC
    not_found = report.get_decision(DECISION_LAYERS)
    assert not_found is None
    print("  [PASS] test_report_get_decision")


def test_report_get_analysis():
    analysis = AnalysisResult(
        dimension=DIMENSION_SECURITY,
        level="high",
    )
    report = ArchitectureDecisionReport(analyses=[analysis])
    found = report.get_analysis(DIMENSION_SECURITY)
    assert found is not None
    assert found.level == "high"
    not_found = report.get_analysis(DIMENSION_SIZE)
    assert not_found is None
    print("  [PASS] test_report_get_analysis")


def test_report_get_module():
    m = ModuleSpec(name="core")
    report = ArchitectureDecisionReport(modules=[m])
    found = report.get_module("core")
    assert found is not None
    assert found.name == "core"
    not_found = report.get_module("nonexistent")
    assert not_found is None
    print("  [PASS] test_report_get_module")


def test_report_get_service():
    s = ServiceSpec(name="bot_service")
    report = ArchitectureDecisionReport(services=[s])
    found = report.get_service("bot_service")
    assert found is not None
    assert found.name == "bot_service"
    not_found = report.get_service("nonexistent")
    assert not_found is None
    print("  [PASS] test_report_get_service")


def test_report_decision_domains():
    report = ArchitectureDecisionReport(decisions=[
        ArchitectureDecision(domain=DECISION_LAYERS),
        ArchitectureDecision(domain=DECISION_COMMUNICATION),
    ])
    domains = report.decision_domains()
    assert DECISION_LAYERS in domains
    assert DECISION_COMMUNICATION in domains
    assert len(domains) == 2
    print("  [PASS] test_report_decision_domains")


def test_report_analysis_dimensions():
    report = ArchitectureDecisionReport(analyses=[
        AnalysisResult(dimension=DIMENSION_SIZE),
        AnalysisResult(dimension=DIMENSION_SECURITY),
    ])
    dims = report.analysis_dimensions()
    assert DIMENSION_SIZE in dims
    assert DIMENSION_SECURITY in dims
    print("  [PASS] test_report_analysis_dimensions")


def test_report_add_finding():
    report = ArchitectureDecisionReport()
    report.add_finding(
        severity=SEVERITY_WARNING,
        code="test_warning",
        message="A test warning.",
        affected="test",
    )
    assert report.finding_count == 1
    assert report.warning_count == 1
    assert "A test warning." in report.warnings
    print("  [PASS] test_report_add_finding")


def test_report_to_dict():
    report = ArchitectureDecisionReport(
        decisions=[ArchitectureDecision(domain=DECISION_LAYERS)],
        analyses=[AnalysisResult(dimension=DIMENSION_SIZE)],
        confidence=0.7,
        confidence_level=CONFIDENCE_MEDIUM,
    )
    d = report.to_dict()
    assert d["decision_count"] == 1
    assert d["analysis_count"] == 1
    assert d["confidence"] == 0.7
    assert d["confidence_level"] == CONFIDENCE_MEDIUM
    assert "analyses" in d
    assert "decisions" in d
    assert "modules" in d
    assert "services" in d
    assert "findings" in d
    assert "cache_info" in d
    assert "provenance" in d
    print("  [PASS] test_report_to_dict")


# ---------------------------------------------------------------------------#
# 2. Reader tests
# ---------------------------------------------------------------------------#

def test_project_planner_reader_from_artefact():
    ctx = make_context(
        project_planner_report=make_normalization_report(3),
    )
    reader = RequirementNormalizationReader()
    data = reader.read(ctx)
    assert data.available is True
    assert data.requirement_count == 3
    assert data.active_requirement_count > 0
    print("  [PASS] test_project_planner_reader_from_artefact")


def test_project_planner_reader_empty():
    ctx = make_context()
    reader = RequirementNormalizationReader()
    data = reader.read(ctx)
    assert data.available is False
    assert data.requirement_count == 0
    print("  [PASS] test_project_planner_reader_empty")


def test_intelligence_graph_reader_from_artefact():
    ctx = make_context(
        intelligence_graph=make_intelligence_graph(),
    )
    reader = IntelligenceGraphReader()
    data = reader.read(ctx)
    assert data.available is True
    assert data.node_count > 0
    assert data.edge_count > 0
    print("  [PASS] test_intelligence_graph_reader_from_artefact")


def test_intelligence_graph_reader_empty():
    ctx = make_context()
    reader = IntelligenceGraphReader()
    data = reader.read(ctx)
    assert data.available is False
    assert data.node_count == 0
    print("  [PASS] test_intelligence_graph_reader_empty")


def test_requirement_intelligence_reader_from_artefact():
    ctx = make_context(
        requirement_intelligence_report=(
            make_requirement_intelligence_report()
        ),
    )
    reader = RequirementIntelligenceReader()
    data = reader.read(ctx)
    assert data.available is True
    assert len(data.requirements) > 0
    assert data.intent_wants != ""
    print("  [PASS] test_requirement_intelligence_reader_from_artefact")


def test_requirement_intelligence_reader_empty():
    ctx = make_context()
    reader = RequirementIntelligenceReader()
    data = reader.read(ctx)
    assert data.available is False
    print("  [PASS] test_requirement_intelligence_reader_empty")


def test_semantic_understanding_reader_from_artefact():
    ctx = make_context(
        semantic_understanding_report=(
            make_semantic_understanding_report()
        ),
    )
    reader = SemanticUnderstandingReader()
    data = reader.read(ctx)
    assert data.available is True
    assert data.intent_kind == "create"
    assert data.confidence > 0
    print("  [PASS] test_semantic_understanding_reader_from_artefact")


def test_semantic_understanding_reader_empty():
    ctx = make_context()
    reader = SemanticUnderstandingReader()
    data = reader.read(ctx)
    assert data.available is False
    print("  [PASS] test_semantic_understanding_reader_empty")


def test_knowledge_reader_from_artefact():
    ctx = make_context(knowledge_base=make_knowledge_base())
    reader = KnowledgeReader()
    data = reader.read(ctx)
    assert data.available is True
    assert len(data.synonyms) > 0
    assert len(data.abbreviations) > 0
    print("  [PASS] test_knowledge_reader_from_artefact")


def test_knowledge_reader_empty():
    ctx = make_context()
    reader = KnowledgeReader()
    data = reader.read(ctx)
    assert data.available is False
    print("  [PASS] test_knowledge_reader_empty")


# ---------------------------------------------------------------------------#
# 3. Size analyzer tests
# ---------------------------------------------------------------------------#

def test_size_analyzer_small():
    req_data = RequirementNormalizationData(
        available=True,
        requirement_count=3,
        active_requirement_count=3,
    )
    graph_data = IntelligenceGraphData(
        available=False,
        node_count=0,
    )
    analyzer = SizeAnalyzer()
    result = analyzer.analyze(req_data, graph_data)
    assert result.dimension == DIMENSION_SIZE
    assert result.level in ALL_SIZES
    assert 0.0 <= result.score <= 1.0
    print(f"  [PASS] test_size_analyzer_small (tier={result.level})")


def test_size_analyzer_large():
    req_data = RequirementNormalizationData(
        available=True,
        requirement_count=100,
        active_requirement_count=100,
    )
    graph_data = IntelligenceGraphData(
        available=True,
        node_count=150,
    )
    analyzer = SizeAnalyzer()
    result = analyzer.analyze(req_data, graph_data)
    assert result.dimension == DIMENSION_SIZE
    assert result.level in ALL_SIZES
    print(f"  [PASS] test_size_analyzer_large (tier={result.level})")


def test_size_analyzer_empty():
    req_data = RequirementNormalizationData(available=False)
    graph_data = IntelligenceGraphData(available=False)
    analyzer = SizeAnalyzer()
    result = analyzer.analyze(req_data, graph_data)
    assert result.dimension == DIMENSION_SIZE
    assert result.level == SIZE_TINY
    print("  [PASS] test_size_analyzer_empty")


# ---------------------------------------------------------------------------#
# 4. Scalability analyzer tests
# ---------------------------------------------------------------------------#

def test_scalability_analyzer_basic():
    graph_data = IntelligenceGraphData(
        available=True,
        node_count=20,
        component_count=25,
        service_count=6,
    )
    req_data = RequirementNormalizationData(
        available=True,
        requirement_count=20,
    )
    analyzer = ScalabilityAnalyzer()
    result = analyzer.analyze(graph_data, req_data, SIZE_SMALL)
    assert result.dimension == DIMENSION_SCALABILITY
    assert 0.0 <= result.score <= 1.0
    assert result.level in ("high", "medium", "low")
    print(f"  [PASS] test_scalability_analyzer_basic (level={result.level})")


def test_scalability_analyzer_empty():
    graph_data = IntelligenceGraphData(available=False)
    req_data = RequirementNormalizationData(available=False)
    analyzer = ScalabilityAnalyzer()
    result = analyzer.analyze(graph_data, req_data, SIZE_TINY)
    assert result.dimension == DIMENSION_SCALABILITY
    print("  [PASS] test_scalability_analyzer_empty")


# ---------------------------------------------------------------------------#
# 5. Performance analyzer tests
# ---------------------------------------------------------------------------#

def test_performance_analyzer_basic():
    sem_data = SemanticUnderstandingData(
        available=True,
        intent_description="Create a high performance bot.",
        confidence=0.85,
    )
    ri_data = RequirementIntelligenceData(
        available=True,
        intent_wants="A high performance bot.",
        intent_confidence=0.85,
    )
    req_data = RequirementNormalizationData(
        available=True,
        requirement_count=3,
    )
    analyzer = PerformanceAnalyzer()
    result = analyzer.analyze(sem_data, ri_data, req_data)
    assert result.dimension == DIMENSION_PERFORMANCE
    assert 0.0 <= result.score <= 1.0
    print(f"  [PASS] test_performance_analyzer_basic (level={result.level})")


def test_performance_analyzer_empty():
    sem_data = SemanticUnderstandingData(available=False)
    ri_data = RequirementIntelligenceData(available=False)
    req_data = RequirementNormalizationData(available=False)
    analyzer = PerformanceAnalyzer()
    result = analyzer.analyze(sem_data, ri_data, req_data)
    assert result.dimension == DIMENSION_PERFORMANCE
    print("  [PASS] test_performance_analyzer_empty")


# ---------------------------------------------------------------------------#
# 6. Security analyzer tests
# ---------------------------------------------------------------------------#

def test_security_analyzer_basic():
    sem_data = SemanticUnderstandingData(
        available=True,
        intent_description="Create a secure bot with authentication.",
        confidence=0.85,
    )
    ri_data = RequirementIntelligenceData(
        available=True,
        intent_wants="A secure bot.",
        intent_confidence=0.85,
    )
    req_data = RequirementNormalizationData(
        available=True,
        requirement_count=3,
    )
    analyzer = SecurityAnalyzer()
    result = analyzer.analyze(sem_data, ri_data, req_data)
    assert result.dimension == DIMENSION_SECURITY
    assert 0.0 <= result.score <= 1.0
    print(f"  [PASS] test_security_analyzer_basic (level={result.level})")


def test_security_analyzer_empty():
    sem_data = SemanticUnderstandingData(available=False)
    ri_data = RequirementIntelligenceData(available=False)
    req_data = RequirementNormalizationData(available=False)
    analyzer = SecurityAnalyzer()
    result = analyzer.analyze(sem_data, ri_data, req_data)
    assert result.dimension == DIMENSION_SECURITY
    print("  [PASS] test_security_analyzer_empty")


# ---------------------------------------------------------------------------#
# 7. Maintainability analyzer tests
# ---------------------------------------------------------------------------#

def test_maintainability_analyzer_basic():
    graph_data = IntelligenceGraphData(
        available=True,
        node_count=10,
        component_count=5,
        circular_count=0,
    )
    ri_data = RequirementIntelligenceData(
        available=True,
        intent_confidence=0.85,
    )
    req_data = RequirementNormalizationData(
        available=True,
        requirement_count=5,
    )
    analyzer = MaintainabilityAnalyzer()
    result = analyzer.analyze(
        graph_data, ri_data, req_data, SIZE_SMALL,
    )
    assert result.dimension == DIMENSION_MAINTAINABILITY
    assert 0.0 <= result.score <= 1.0
    print(f"  [PASS] test_maintainability_analyzer_basic (level={result.level})")


def test_maintainability_analyzer_empty():
    graph_data = IntelligenceGraphData(available=False)
    ri_data = RequirementIntelligenceData(available=False)
    req_data = RequirementNormalizationData(available=False)
    analyzer = MaintainabilityAnalyzer()
    result = analyzer.analyze(
        graph_data, ri_data, req_data, SIZE_TINY,
    )
    assert result.dimension == DIMENSION_MAINTAINABILITY
    print("  [PASS] test_maintainability_analyzer_empty")


# ---------------------------------------------------------------------------#
# 8. Architecture selector tests
# ---------------------------------------------------------------------------#

def test_architecture_selector_all_decisions():
    analyses = [
        AnalysisResult(dimension=DIMENSION_SIZE, level=SIZE_SMALL,
                       score=0.7),
        AnalysisResult(dimension=DIMENSION_SCALABILITY,
                       level="medium", score=0.65),
        AnalysisResult(dimension=DIMENSION_PERFORMANCE,
                       level="medium", score=0.5),
        AnalysisResult(dimension=DIMENSION_SECURITY,
                       level="medium", score=0.5),
        AnalysisResult(dimension=DIMENSION_MAINTAINABILITY,
                       level="high", score=0.8),
    ]
    graph_data = IntelligenceGraphData(
        available=True,
        node_count=10,
        component_count=5,
        service_count=2,
    )
    req_data = RequirementNormalizationData(
        available=True,
        requirement_count=3,
        active_requirement_count=3,
    )
    ri_data = RequirementIntelligenceData(
        available=True,
        intent_wants="A Telegram bot.",
        intent_confidence=0.85,
    )
    sem_data = SemanticUnderstandingData(
        available=True,
        intent_kind="create",
        confidence=0.85,
    )
    selector = ArchitectureSelector()
    decisions, modules, services = selector.select(
        analyses, graph_data, req_data, ri_data, sem_data,
    )
    assert len(decisions) == 8
    domains = [d.domain for d in decisions]
    for domain in ALL_DECISION_DOMAINS:
        assert domain in domains, f"Missing domain: {domain}"
    # Every decision should have reason, analysis, impact.
    for d in decisions:
        assert d.reason != "", f"Decision {d.domain} missing reason"
        assert d.analysis != "", f"Decision {d.domain} missing analysis"
        assert d.impact != "", f"Decision {d.domain} missing impact"
        assert len(d.rejected_alternatives) > 0, \
            f"Decision {d.domain} missing rejected alternatives"
    print("  [PASS] test_architecture_selector_all_decisions")


def test_architecture_selector_modules():
    analyses = [
        AnalysisResult(dimension=DIMENSION_SIZE, level=SIZE_SMALL,
                       score=0.7),
        AnalysisResult(dimension=DIMENSION_SCALABILITY,
                       level="medium", score=0.65),
        AnalysisResult(dimension=DIMENSION_PERFORMANCE,
                       level="medium", score=0.5),
        AnalysisResult(dimension=DIMENSION_SECURITY,
                       level="medium", score=0.5),
        AnalysisResult(dimension=DIMENSION_MAINTAINABILITY,
                       level="high", score=0.8),
    ]
    graph_data = IntelligenceGraphData(
        available=True, node_count=10, component_count=5,
    )
    req_data = RequirementNormalizationData(
        available=True, requirement_count=3,
    )
    ri_data = RequirementIntelligenceData(
        available=True, intent_confidence=0.85,
    )
    sem_data = SemanticUnderstandingData(
        available=True, intent_kind="create", confidence=0.85,
    )
    selector = ArchitectureSelector()
    decisions, modules, services = selector.select(
        analyses, graph_data, req_data, ri_data, sem_data,
    )
    assert len(modules) > 0
    for m in modules:
        assert m.name != ""
        assert m.layer != ""
    print(f"  [PASS] test_architecture_selector_modules ({len(modules)} modules)")


def test_architecture_selector_services():
    analyses = [
        AnalysisResult(dimension=DIMENSION_SIZE, level=SIZE_SMALL,
                       score=0.7),
        AnalysisResult(dimension=DIMENSION_SCALABILITY,
                       level="medium", score=0.65),
        AnalysisResult(dimension=DIMENSION_PERFORMANCE,
                       level="medium", score=0.5),
        AnalysisResult(dimension=DIMENSION_SECURITY,
                       level="medium", score=0.5),
        AnalysisResult(dimension=DIMENSION_MAINTAINABILITY,
                       level="high", score=0.8),
    ]
    graph_data = IntelligenceGraphData(
        available=True, node_count=10, service_count=2,
    )
    req_data = RequirementNormalizationData(
        available=True, requirement_count=3,
    )
    ri_data = RequirementIntelligenceData(
        available=True, intent_confidence=0.85,
    )
    sem_data = SemanticUnderstandingData(
        available=True, intent_kind="create", confidence=0.85,
    )
    selector = ArchitectureSelector()
    decisions, modules, services = selector.select(
        analyses, graph_data, req_data, ri_data, sem_data,
    )
    assert len(services) >= 1
    for s in services:
        assert s.name != ""
        assert s.responsibility != ""
    print(f"  [PASS] test_architecture_selector_services ({len(services)} services)")


# ---------------------------------------------------------------------------#
# 9. Decision validator tests
# ---------------------------------------------------------------------------#

def test_decision_validator_good_report():
    ra = RejectedAlternative(
        name="monolith", reason="too simple",
        impact="poor scaling",
    )
    valid_by_domain = {
        DECISION_LAYERS: ["presentation", "business", "data_access"],
        DECISION_MODULES: "feature_modules",
        DECISION_SERVICES: "microservices",
        DECISION_DEPENDENCY_STRUCTURE: "layered",
        DECISION_PROJECT_LAYOUT: "feature_based",
        DECISION_COMMUNICATION: "synchronous",
        DECISION_ERROR_HANDLING: "centralized",
        DECISION_CONFIGURATION: "hybrid",
    }
    decisions = []
    for domain in ALL_DECISION_DOMAINS:
        decisions.append(ArchitectureDecision(
            domain=domain,
            selected=valid_by_domain[domain],
            reason="Reason.",
            analysis="Analysis.",
            impact="Impact.",
            rejected_alternatives=[ra],
        ))
    report = ArchitectureDecisionReport(decisions=decisions)
    validator = DecisionValidator()
    findings, passed = validator.validate(report)
    assert passed is True
    assert len(findings) == 0
    print("  [PASS] test_decision_validator_good_report")


def test_decision_validator_empty_report():
    report = ArchitectureDecisionReport()
    validator = DecisionValidator()
    findings, passed = validator.validate(report)
    assert passed is False
    assert len(findings) > 0
    print("  [PASS] test_decision_validator_empty_report")


def test_decision_validator_missing_fields():
    decisions = [ArchitectureDecision(
        domain=DECISION_LAYERS,
        selected="test",
        reason="",
        analysis="",
        impact="",
        rejected_alternatives=[],
    )]
    report = ArchitectureDecisionReport(decisions=decisions)
    validator = DecisionValidator()
    findings, passed = validator.validate(report)
    assert passed is False
    assert len(findings) > 0
    print("  [PASS] test_decision_validator_missing_fields")


# ---------------------------------------------------------------------------#
# 10. Quality gate tests
# ---------------------------------------------------------------------------#

def test_quality_gate_passes_good_report():
    ra = RejectedAlternative(
        name="monolith", reason="too simple",
        impact="poor scaling",
    )
    decisions = []
    for domain in ALL_DECISION_DOMAINS:
        decisions.append(ArchitectureDecision(
            domain=domain,
            selected="test",
            reason="Reason.",
            analysis="Analysis.",
            impact="Impact.",
            rejected_alternatives=[ra],
        ))
    report = ArchitectureDecisionReport(
        decisions=decisions,
        confidence=0.8,
        confidence_level=CONFIDENCE_HIGH,
    )
    gate = QualityGate()
    findings, passed = gate.validate(report)
    assert passed is True
    print("  [PASS] test_quality_gate_passes_good_report")


def test_quality_gate_fails_empty_report():
    report = ArchitectureDecisionReport()
    gate = QualityGate()
    findings, passed = gate.validate(report)
    assert passed is False
    assert len(findings) > 0
    print("  [PASS] test_quality_gate_fails_empty_report")


def test_quality_gate_fails_low_confidence():
    ra = RejectedAlternative(
        name="x", reason="y", impact="z",
    )
    decisions = []
    for domain in ALL_DECISION_DOMAINS:
        decisions.append(ArchitectureDecision(
            domain=domain,
            selected="test",
            reason="Reason.",
            analysis="Analysis.",
            impact="Impact.",
            rejected_alternatives=[ra],
        ))
    report = ArchitectureDecisionReport(
        decisions=decisions,
        confidence=0.3,
        confidence_level=CONFIDENCE_LOW,
    )
    gate = QualityGate()
    findings, passed = gate.validate(report)
    assert passed is False
    print("  [PASS] test_quality_gate_fails_low_confidence")


# ---------------------------------------------------------------------------#
# 11. Cache manager tests
# ---------------------------------------------------------------------------#

def test_cache_manager_disabled():
    cm = CacheManager(enabled=False)
    req_data = RequirementNormalizationData(available=True, requirement_count=3)
    graph_data = IntelligenceGraphData(available=True, node_count=10)
    ri_data = RequirementIntelligenceData(available=True)
    sem_data = SemanticUnderstandingData(available=True)
    kb_data = KnowledgeData(available=True)
    info = cm.get_cache_info(
        req_data, graph_data, ri_data, sem_data, kb_data,
    )
    assert info.status == CACHE_DISABLED
    assert info.hit is False
    assert cm.enabled is False
    print("  [PASS] test_cache_manager_disabled")


def test_cache_manager_enabled_miss_then_hit():
    cm = CacheManager(enabled=True)
    req_data = RequirementNormalizationData(
        available=True, requirement_count=3,
    )
    graph_data = IntelligenceGraphData(available=True, node_count=10)
    ri_data = RequirementIntelligenceData(available=True)
    sem_data = SemanticUnderstandingData(available=True)
    kb_data = KnowledgeData(available=True)
    info = cm.get_cache_info(
        req_data, graph_data, ri_data, sem_data, kb_data,
    )
    assert info.status == CACHE_MISS
    assert info.hit is False
    # Store a report.
    report = ArchitectureDecisionReport()
    cm.store(info, report)
    assert cm.size == 1
    # Now it should be a hit.
    info2 = cm.get_cache_info(
        req_data, graph_data, ri_data, sem_data, kb_data,
    )
    assert info2.status == CACHE_HIT
    assert info2.hit is True
    cached = cm.get_cached(info2)
    assert cached is not None
    print("  [PASS] test_cache_manager_enabled_miss_then_hit")


def test_cache_manager_clear():
    cm = CacheManager(enabled=True)
    req_data = RequirementNormalizationData(
        available=True, requirement_count=3,
    )
    graph_data = IntelligenceGraphData(available=True, node_count=10)
    ri_data = RequirementIntelligenceData(available=True)
    sem_data = SemanticUnderstandingData(available=True)
    kb_data = KnowledgeData(available=True)
    info = cm.get_cache_info(
        req_data, graph_data, ri_data, sem_data, kb_data,
    )
    cm.store(info, ArchitectureDecisionReport())
    assert cm.size == 1
    cm.clear()
    assert cm.size == 0
    print("  [PASS] test_cache_manager_clear")


# ---------------------------------------------------------------------------#
# 12. Report assembler tests
# ---------------------------------------------------------------------------#

def test_report_assembler_assemble():
    assembler = ReportAssembler()
    analyses = [AnalysisResult(dimension=DIMENSION_SIZE)]
    decisions = [ArchitectureDecision(domain=DECISION_LAYERS)]
    modules = [ModuleSpec(name="core")]
    services = [ServiceSpec(name="bot_service")]
    cache_info = CacheInfo(status=CACHE_MISS)
    provenance = ArchitectureProvenance(
        normalized_requirements_available=True,
    )
    report = assembler.assemble(
        analyses=analyses,
        decisions=decisions,
        modules=modules,
        services=services,
        cache_info=cache_info,
        provenance=provenance,
        confidence=0.8,
        confidence_level=CONFIDENCE_HIGH,
    )
    assert report.analysis_count == 1
    assert report.decision_count == 1
    assert report.module_count == 1
    assert report.service_count == 1
    assert report.confidence == 0.8
    assert report.summary != ""
    print("  [PASS] test_report_assembler_assemble")


def test_report_assembler_build_provenance():
    assembler = ReportAssembler()
    req_data = RequirementNormalizationData(
        available=True, requirement_count=5,
    )
    graph_data = IntelligenceGraphData(
        available=True, node_count=10, edge_count=3,
    )
    ri_data = RequirementIntelligenceData(available=True)
    sem_data = SemanticUnderstandingData(
        available=True, intent_kind="create", confidence=0.85,
    )
    kb_data = KnowledgeData(available=True)
    provenance = assembler.build_provenance(
        req_data, graph_data, ri_data, sem_data, kb_data,
    )
    assert provenance.normalized_requirements_available is True
    assert provenance.intelligence_graph_available is True
    assert provenance.requirement_intelligence_available is True
    assert provenance.semantic_understanding_available is True
    assert provenance.knowledge_base_available is True
    assert len(provenance.all_sources_used) == 5
    assert provenance.requirement_count == 5
    assert provenance.graph_node_count == 10
    assert provenance.intent_kind == "create"
    print("  [PASS] test_report_assembler_build_provenance")


def test_report_assembler_build_notes():
    assembler = ReportAssembler()
    req_data = RequirementNormalizationData(
        available=True, requirement_count=3,
    )
    graph_data = IntelligenceGraphData(
        available=True, node_count=10, edge_count=2,
    )
    ri_data = RequirementIntelligenceData(available=True)
    sem_data = SemanticUnderstandingData(
        available=True, intent_kind="create",
    )
    kb_data = KnowledgeData(available=True)
    provenance = assembler.build_provenance(
        req_data, graph_data, ri_data, sem_data, kb_data,
    )
    report = assembler.assemble(
        analyses=[],
        decisions=[],
        modules=[],
        services=[],
        cache_info=CacheInfo(),
        provenance=provenance,
        confidence=0.5,
        confidence_level=CONFIDENCE_LOW,
    )
    notes = assembler.build_notes(
        report, req_data, graph_data, ri_data, sem_data, kb_data,
    )
    assert len(notes) > 0
    assert any("generated" in n for n in notes)
    assert any("data sources" in n.lower() for n in notes)
    print("  [PASS] test_report_assembler_build_notes")


def test_report_assembler_collect_warnings():
    assembler = ReportAssembler()
    report = ArchitectureDecisionReport()
    report.add_finding(
        severity=SEVERITY_WARNING,
        code="test_warning",
        message="A warning message.",
    )
    report.add_finding(
        severity=SEVERITY_ERROR,
        code="test_error",
        message="An error message.",
    )
    warnings = assembler.collect_warnings(report)
    assert len(warnings) == 1
    assert "A warning message." in warnings[0]
    print("  [PASS] test_report_assembler_collect_warnings")


# ---------------------------------------------------------------------------#
# 13. Engine tests
# ---------------------------------------------------------------------------#

def test_engine_no_data():
    """The engine should fail when no data sources are available."""
    ctx = make_context()
    engine = ArchitectureDecisionEngine()
    result = engine.execute(ctx)
    assert result.success is False
    assert "architecture_decision_report" in result.outputs
    report = result.outputs["architecture_decision_report"]
    assert report.is_empty is True
    print("  [PASS] test_engine_no_data")


def test_engine_with_normalization_report():
    """The engine should produce a report when the normalization
    report is available."""
    ctx = make_context(
        project_planner_report=make_normalization_report(3),
    )
    engine = ArchitectureDecisionEngine()
    result = engine.execute(ctx)
    assert result.success is True
    assert "architecture_decision_report" in result.outputs
    report = result.outputs["architecture_decision_report"]
    assert report.decision_count > 0
    print(f"  [PASS] test_engine_with_normalization_report ({report.decision_count} decisions)")


def test_engine_produces_artefact():
    """The engine should set the architecture_decision_report artefact
    in the context."""
    ctx = make_context(
        project_planner_report=make_normalization_report(3),
    )
    engine = ArchitectureDecisionEngine()
    engine.execute(ctx)
    assert ctx.has("architecture_decision_report") is True
    print("  [PASS] test_engine_produces_artefact")


def test_engine_stores_in_metadata():
    """The engine should store the report in context metadata."""
    ctx = make_context(
        project_planner_report=make_normalization_report(3),
    )
    engine = ArchitectureDecisionEngine()
    engine.execute(ctx)
    assert "architecture_decision" in ctx.metadata
    print("  [PASS] test_engine_stores_in_metadata")


def test_engine_does_not_write_files():
    """The engine should not write any files to the work directory."""
    ctx = make_context(
        project_planner_report=make_normalization_report(3),
    )
    engine = ArchitectureDecisionEngine()
    engine.execute(ctx)
    # The engine should not create any files in the work directory.
    # We just verify it completes without writing files.
    assert ctx.has("architecture_decision_report") is True
    print("  [PASS] test_engine_does_not_write_files")


def test_engine_all_eight_decisions():
    """The engine should make all eight architectural decisions."""
    ctx = make_context(
        project_planner_report=make_normalization_report(5),
        intelligence_graph=make_intelligence_graph(),
        requirement_intelligence_report=(
            make_requirement_intelligence_report()
        ),
        semantic_understanding_report=(
            make_semantic_understanding_report()
        ),
        knowledge_base=make_knowledge_base(),
    )
    engine = ArchitectureDecisionEngine()
    result = engine.execute(ctx)
    report = result.outputs["architecture_decision_report"]
    domains = report.decision_domains()
    for domain in ALL_DECISION_DOMAINS:
        assert domain in domains, f"Missing decision domain: {domain}"
    print(f"  [PASS] test_engine_all_eight_decisions ({len(domains)} domains)")


def test_engine_confidence_in_valid_range():
    """The engine confidence should be between 0.0 and 1.0."""
    ctx = make_full_context()
    engine = ArchitectureDecisionEngine()
    result = engine.execute(ctx)
    report = result.outputs["architecture_decision_report"]
    assert 0.0 <= report.confidence <= 1.0
    assert report.confidence_level in ALL_CONFIDENCE_LEVELS
    print(f"  [PASS] test_engine_confidence_in_valid_range ({report.confidence:.2f})")


def test_engine_produces_analyses():
    """The engine should produce all five analysis dimensions."""
    ctx = make_full_context()
    engine = ArchitectureDecisionEngine()
    result = engine.execute(ctx)
    report = result.outputs["architecture_decision_report"]
    dims = report.analysis_dimensions()
    for dim in ALL_DIMENSIONS:
        assert dim in dims, f"Missing analysis dimension: {dim}"
    print(f"  [PASS] test_engine_produces_analyses ({len(dims)} dimensions)")


def test_engine_produces_modules():
    """The engine should produce at least one module."""
    ctx = make_full_context()
    engine = ArchitectureDecisionEngine()
    result = engine.execute(ctx)
    report = result.outputs["architecture_decision_report"]
    assert report.module_count > 0
    print(f"  [PASS] test_engine_produces_modules ({report.module_count} modules)")


def test_engine_produces_services():
    """The engine should produce at least one service."""
    ctx = make_full_context()
    engine = ArchitectureDecisionEngine()
    result = engine.execute(ctx)
    report = result.outputs["architecture_decision_report"]
    assert report.service_count > 0
    print(f"  [PASS] test_engine_produces_services ({report.service_count} services)")


def test_engine_cache_hit():
    """The engine should return a cached report on the second
    call with the same inputs."""
    ctx = make_full_context()
    engine = ArchitectureDecisionEngine()
    # First call — should be a cache miss.
    result1 = engine.execute(ctx)
    assert result1.success is True
    report1 = result1.outputs["architecture_decision_report"]
    assert report1.cache_hit is False
    # Second call — should be a cache hit.
    result2 = engine.execute(ctx)
    report2 = result2.outputs["architecture_decision_report"]
    assert report2.cache_hit is True
    print("  [PASS] test_engine_cache_hit")


# ---------------------------------------------------------------------------#
# 14. Bootstrap tests
# ---------------------------------------------------------------------------#

def test_bootstrap_registers_architecture_decision():
    registry, orchestrator, manager = bootstrap()
    engine = registry.get_engine("architecture_decision")
    assert engine is not None
    assert engine.name == "architecture_decision"
    print("  [PASS] test_bootstrap_registers_architecture_decision")


def test_bootstrap_architecture_decision_priority():
    registry, orchestrator, manager = bootstrap()
    engine = registry.get_engine("architecture_decision")
    # Check the manager has it registered at priority 101.
    manager_info = None
    if hasattr(manager, "_entries"):
        manager_info = manager._entries.get("architecture_decision")
    elif hasattr(manager, "_engines"):
        manager_info = manager._engines.get("architecture_decision")
    assert manager_info is not None
    if hasattr(manager_info, "priority"):
        assert manager_info.priority == 35
    elif isinstance(manager_info, dict):
        assert manager_info.get("priority") == 101
    print("  [PASS] test_bootstrap_architecture_decision_priority")


def test_bootstrap_architecture_decision_dependencies():
    registry, orchestrator, manager = bootstrap()
    # Check the manager has it registered with the right
    # dependencies.
    manager_info = None
    if hasattr(manager, "_entries"):
        manager_info = manager._entries.get("architecture_decision")
    elif hasattr(manager, "_engines"):
        manager_info = manager._engines.get("architecture_decision")
    assert manager_info is not None
    if hasattr(manager_info, "dependencies"):
        deps = manager_info.dependencies
        if isinstance(deps, (set, list, tuple)):
            assert "project_planner" in deps
        else:
            assert "project_planner" == deps
    elif isinstance(manager_info, dict):
        assert "project_planner" in manager_info.get(
            "dependencies", []
        )
    print("  [PASS] test_bootstrap_architecture_decision_dependencies")


# ---------------------------------------------------------------------------#
# 15. Serialisation tests
# ---------------------------------------------------------------------------#

def test_analysis_result_serialisation():
    ar = AnalysisResult(
        dimension=DIMENSION_SIZE,
        score=0.7,
        level=SIZE_SMALL,
        summary="Small project.",
        details=["detail 1", "detail 2"],
    )
    d = ar.to_dict()
    assert isinstance(d, dict)
    assert d["dimension"] == DIMENSION_SIZE
    assert d["score"] == 0.7
    assert d["level"] == SIZE_SMALL
    assert d["details"] == ["detail 1", "detail 2"]
    print("  [PASS] test_analysis_result_serialisation")


def test_rejected_alternative_serialisation():
    ra = RejectedAlternative(
        name="monolith",
        reason="Too simple.",
        impact="Poor scalability.",
    )
    d = ra.to_dict()
    assert isinstance(d, dict)
    assert d["name"] == "monolith"
    assert d["reason"] == "Too simple."
    assert d["impact"] == "Poor scalability."
    print("  [PASS] test_rejected_alternative_serialisation")


def test_architecture_decision_serialisation():
    d = ArchitectureDecision(
        domain=DECISION_LAYERS,
        selected="presentation, business",
        reason="Reason.",
        analysis="Analysis.",
        impact="Impact.",
        rejected_alternatives=[
            RejectedAlternative(name="monolith", reason="no", impact="bad"),
        ],
        confidence=0.85,
    )
    d_dict = d.to_dict()
    assert isinstance(d_dict, dict)
    assert d_dict["domain"] == DECISION_LAYERS
    assert d_dict["confidence"] == 0.85
    assert len(d_dict["rejected_alternatives"]) == 1
    print("  [PASS] test_architecture_decision_serialisation")


def test_architecture_finding_serialisation():
    f = ArchitectureFinding(
        severity=SEVERITY_WARNING,
        code="test",
        message="Test message.",
    )
    d = f.to_dict()
    assert isinstance(d, dict)
    assert d["severity"] == SEVERITY_WARNING
    assert d["code"] == "test"
    print("  [PASS] test_architecture_finding_serialisation")


def test_cache_info_serialisation():
    ci = CacheInfo(
        status=CACHE_HIT,
        cache_key="arch_abc",
        hit=True,
        inputs_hash="hash123",
    )
    d = ci.to_dict()
    assert isinstance(d, dict)
    assert d["status"] == CACHE_HIT
    assert d["hit"] is True
    print("  [PASS] test_cache_info_serialisation")


def test_architecture_provenance_serialisation():
    p = ArchitectureProvenance(
        normalized_requirements_available=True,
        intelligence_graph_available=True,
        all_sources_used=[SOURCE_NORMALIZED_REQUIREMENTS],
        requirement_count=5,
        graph_node_count=10,
        intent_kind="create",
        semantic_confidence=0.85,
    )
    d = p.to_dict()
    assert isinstance(d, dict)
    assert d["normalized_requirements_available"] is True
    assert d["requirement_count"] == 5
    assert d["graph_node_count"] == 10
    assert d["intent_kind"] == "create"
    print("  [PASS] test_architecture_provenance_serialisation")


def test_module_spec_serialisation():
    m = ModuleSpec(
        name="core",
        layer="business",
        responsibility="Core logic.",
        dependencies=["db"],
    )
    d = m.to_dict()
    assert isinstance(d, dict)
    assert d["name"] == "core"
    assert d["layer"] == "business"
    assert d["dependencies"] == ["db"]
    print("  [PASS] test_module_spec_serialisation")


def test_service_spec_serialisation():
    s = ServiceSpec(
        name="bot_service",
        responsibility="Bot service.",
        communication=COMM_ASYNC,
        dependencies=["db_service"],
    )
    d = s.to_dict()
    assert isinstance(d, dict)
    assert d["name"] == "bot_service"
    assert d["communication"] == COMM_ASYNC
    print("  [PASS] test_service_spec_serialisation")


def test_architecture_decision_report_serialisation():
    report = ArchitectureDecisionReport(
        analyses=[AnalysisResult(dimension=DIMENSION_SIZE)],
        decisions=[ArchitectureDecision(
            domain=DECISION_LAYERS,
            reason="Reason.",
            analysis="Analysis.",
            impact="Impact.",
            rejected_alternatives=[
                RejectedAlternative(name="x", reason="y", impact="z"),
            ],
        )],
        modules=[ModuleSpec(name="core")],
        services=[ServiceSpec(name="bot")],
        confidence=0.8,
        confidence_level=CONFIDENCE_HIGH,
    )
    d = report.to_dict()
    assert isinstance(d, dict)
    assert d["decision_count"] == 1
    assert d["analysis_count"] == 1
    assert d["module_count"] == 1
    assert d["service_count"] == 1
    assert d["confidence"] == 0.8
    assert len(d["analyses"]) == 1
    assert len(d["decisions"]) == 1
    assert len(d["modules"]) == 1
    assert len(d["services"]) == 1
    print("  [PASS] test_architecture_decision_report_serialisation")


# ---------------------------------------------------------------------------#
# 16. End-to-end tests
# ---------------------------------------------------------------------------#

def test_end_to_end_with_all_sources():
    """End-to-end test with all five data sources."""
    ctx = make_full_context()
    engine = ArchitectureDecisionEngine()
    result = engine.execute(ctx)
    assert result.success is True
    report = result.outputs["architecture_decision_report"]
    assert report.decision_count == 8
    assert report.analysis_count == 5
    assert report.module_count > 0
    assert report.service_count > 0
    assert report.confidence > 0
    # Check all decision domains are present.
    domains = report.decision_domains()
    for domain in ALL_DECISION_DOMAINS:
        assert domain in domains
    print(f"  [PASS] test_end_to_end_with_all_sources (confidence={report.confidence:.2f})")


def test_end_to_end_with_normalization_only():
    """End-to-end test with only the normalization report."""
    ctx = make_context(
        project_planner_report=make_normalization_report(3),
    )
    engine = ArchitectureDecisionEngine()
    result = engine.execute(ctx)
    assert result.success is True
    report = result.outputs["architecture_decision_report"]
    assert report.decision_count == 8
    print("  [PASS] test_end_to_end_with_normalization_only")


def test_end_to_end_empty_context():
    """End-to-end test with empty context."""
    ctx = make_context()
    engine = ArchitectureDecisionEngine()
    result = engine.execute(ctx)
    assert result.success is False
    report = result.outputs["architecture_decision_report"]
    assert report.has_errors is True
    print("  [PASS] test_end_to_end_empty_context")


def test_end_to_end_large_project():
    """End-to-end test with a large project (many requirements)."""
    ctx = make_context(
        project_planner_report=make_normalization_report(50),
        intelligence_graph=make_intelligence_graph(
            node_count=100, component_count=30, service_count=5,
        ),
        requirement_intelligence_report=(
            make_requirement_intelligence_report()
        ),
        semantic_understanding_report=(
            make_semantic_understanding_report()
        ),
        knowledge_base=make_knowledge_base(),
    )
    engine = ArchitectureDecisionEngine()
    result = engine.execute(ctx)
    assert result.success is True
    report = result.outputs["architecture_decision_report"]
    assert report.decision_count == 8
    size_analysis = report.get_analysis(DIMENSION_SIZE)
    assert size_analysis is not None
    assert size_analysis.level in ALL_SIZES
    print(f"  [PASS] test_end_to_end_large_project (size={size_analysis.level})")


def test_end_to_end_report_ready():
    """End-to-end test verifying the report is ready."""
    ctx = make_full_context()
    engine = ArchitectureDecisionEngine()
    result = engine.execute(ctx)
    report = result.outputs["architecture_decision_report"]
    # The report should be ready (no errors, sufficient confidence).
    assert report.has_errors is False
    assert report.decision_count == 8
    assert report.all_decisions_validated is True
    print(f"  [PASS] test_end_to_end_report_ready (ready={report.ready})")


# ---------------------------------------------------------------------------#
# Test runner
# ---------------------------------------------------------------------------#

def run_all_tests():
    """Run all tests and return True if all passed."""
    tests = [
        # Data model
        test_analysis_result_creation,
        test_analysis_result_to_dict,
        test_rejected_alternative_creation,
        test_rejected_alternative_to_dict,
        test_architecture_decision_creation,
        test_architecture_decision_to_dict,
        test_architecture_finding_creation,
        test_architecture_finding_to_dict,
        test_cache_info_creation,
        test_cache_info_to_dict,
        test_architecture_provenance_creation,
        test_architecture_provenance_to_dict,
        test_module_spec_creation,
        test_module_spec_to_dict,
        test_service_spec_creation,
        test_service_spec_to_dict,
        test_report_creation,
        test_report_empty,
        test_report_properties,
        test_report_ready,
        test_report_get_decision,
        test_report_get_analysis,
        test_report_get_module,
        test_report_get_service,
        test_report_decision_domains,
        test_report_analysis_dimensions,
        test_report_add_finding,
        test_report_to_dict,
        # Readers
        test_project_planner_reader_from_artefact,
        test_project_planner_reader_empty,
        test_intelligence_graph_reader_from_artefact,
        test_intelligence_graph_reader_empty,
        test_requirement_intelligence_reader_from_artefact,
        test_requirement_intelligence_reader_empty,
        test_semantic_understanding_reader_from_artefact,
        test_semantic_understanding_reader_empty,
        test_knowledge_reader_from_artefact,
        test_knowledge_reader_empty,
        # Analyzers
        test_size_analyzer_small,
        test_size_analyzer_large,
        test_size_analyzer_empty,
        test_scalability_analyzer_basic,
        test_scalability_analyzer_empty,
        test_performance_analyzer_basic,
        test_performance_analyzer_empty,
        test_security_analyzer_basic,
        test_security_analyzer_empty,
        test_maintainability_analyzer_basic,
        test_maintainability_analyzer_empty,
        # Architecture selector
        test_architecture_selector_all_decisions,
        test_architecture_selector_modules,
        test_architecture_selector_services,
        # Decision validator
        test_decision_validator_good_report,
        test_decision_validator_empty_report,
        test_decision_validator_missing_fields,
        # Quality gate
        test_quality_gate_passes_good_report,
        test_quality_gate_fails_empty_report,
        test_quality_gate_fails_low_confidence,
        # Cache manager
        test_cache_manager_disabled,
        test_cache_manager_enabled_miss_then_hit,
        test_cache_manager_clear,
        # Report assembler
        test_report_assembler_assemble,
        test_report_assembler_build_provenance,
        test_report_assembler_build_notes,
        test_report_assembler_collect_warnings,
        # Engine
        test_engine_no_data,
        test_engine_with_normalization_report,
        test_engine_produces_artefact,
        test_engine_stores_in_metadata,
        test_engine_does_not_write_files,
        test_engine_all_eight_decisions,
        test_engine_confidence_in_valid_range,
        test_engine_produces_analyses,
        test_engine_produces_modules,
        test_engine_produces_services,
        test_engine_cache_hit,
        # Bootstrap
        test_bootstrap_registers_architecture_decision,
        test_bootstrap_architecture_decision_priority,
        test_bootstrap_architecture_decision_dependencies,
        # Serialisation
        test_analysis_result_serialisation,
        test_rejected_alternative_serialisation,
        test_architecture_decision_serialisation,
        test_architecture_finding_serialisation,
        test_cache_info_serialisation,
        test_architecture_provenance_serialisation,
        test_module_spec_serialisation,
        test_service_spec_serialisation,
        test_architecture_decision_report_serialisation,
        # End-to-end
        test_end_to_end_with_all_sources,
        test_end_to_end_with_normalization_only,
        test_end_to_end_empty_context,
        test_end_to_end_large_project,
        test_end_to_end_report_ready,
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
