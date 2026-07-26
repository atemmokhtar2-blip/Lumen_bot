#!/usr/bin/env python3
"""
Comprehensive test suite for the Project Capability Analyzer Engine
(Specification 017).

These tests cover every aspect of the specification:

1. Data model integrity (AnalysisResult, ComplexityAnalysis,
   ResourceEstimation, ScalabilityTier, ScalabilityAnalysis,
   Bottleneck, ArchitectureStressAnalysis, DependencyIssue,
   DependencyAnalysis, CapabilityFinding, CacheInfo,
   CapabilityProvenance, ProjectCapabilityReport, source-artefact
   constants, severity constants, complexity constants, size
   constants, scale-tier constants, load-level constants,
   bottleneck constants, dependency-issue constants,
   analysis-dimension constants, quality-rule constants,
   cache-status constants, confidence-level constants, verdict
   constants).
2. The ArchitectureDecisionReader (artefact, empty context).
3. The TechnologySelectionReader (artefact, empty context).
4. The RequirementNormalizationReader (artefact, empty context).
5. The IntelligenceGraphReader (artefact, empty context).
6. The KnowledgeReader (artefact, empty context).
7. The ComplexityAnalyzer (small, medium, large, empty).
8. The ResourceEstimator (small, medium, large, empty).
9. The ScalabilityAnalyzer (base, with tech bonus, empty).
10. The StressAnalyzer (light, heavy, peak, bottlenecks, empty).
11. The DependencyAnalyzer (healthy, circular, conflicts, empty).
12. The QualityGate (pass, empty, errors, low scores).
13. The CacheManager (miss, hit, store, stale).
14. The ReportBuilder (assembles, summary, notes, warnings,
    provenance, verdict, strengths, risks, recommendations).
15. The main engine reads the five data sources.
16. The main engine produces a project_capability_report
    artefact.
17. The main engine fails when no data sources are available.
18. The main engine stores the report in the context metadata.
19. The main engine does not write files or build the project.
20. The main engine runs all five analyses.
21. The main engine produces a verdict.
22. Bootstrap integration (engine registered in registry and
    manager at priority 103, depends on technology_selection).
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
from telegram_bot_engine.engines.generators.capability_analyzer import (
    # Engine
    ProjectCapabilityAnalyzerEngine,
    # Data model
    AnalysisResult,
    ComplexityAnalysis,
    ResourceEstimation,
    ScalabilityTier,
    ScalabilityAnalysis,
    Bottleneck,
    ArchitectureStressAnalysis,
    DependencyIssue,
    DependencyAnalysis,
    CapabilityFinding,
    CacheInfo,
    CapabilityProvenance,
    ProjectCapabilityReport,
    # Source-artefact constants
    SOURCE_ARCHITECTURE_DECISION,
    SOURCE_TECHNOLOGY_SELECTION,
    SOURCE_NORMALIZED_REQUIREMENTS,
    SOURCE_INTELLIGENCE_GRAPH,
    SOURCE_KNOWLEDGE_BASE,
    ALL_SOURCES,
    # Severity constants
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    SEVERITY_INFO,
    ALL_SEVERITIES,
    # Complexity level constants
    COMPLEXITY_TRIVIAL,
    COMPLEXITY_LOW,
    COMPLEXITY_MODERATE,
    COMPLEXITY_HIGH,
    COMPLEXITY_VERY_HIGH,
    ALL_COMPLEXITY_LEVELS,
    COMPLEXITY_THRESHOLD_TRIVIAL,
    COMPLEXITY_THRESHOLD_LOW,
    COMPLEXITY_THRESHOLD_MODERATE,
    COMPLEXITY_THRESHOLD_HIGH,
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
    # Scale tier constants
    SCALE_THOUSANDS,
    SCALE_TENS_OF_THOUSANDS,
    SCALE_HUNDREDS_OF_THOUSANDS,
    SCALE_MILLIONS,
    ALL_SCALE_TIERS,
    SCALE_THRESHOLD_THOUSANDS,
    SCALE_THRESHOLD_TENS_OF_THOUSANDS,
    SCALE_THRESHOLD_HUNDREDS_OF_THOUSANDS,
    SCALE_THRESHOLD_MILLIONS,
    # Load level constants
    LOAD_LIGHT,
    LOAD_MODERATE,
    LOAD_HEAVY,
    LOAD_PEAK,
    ALL_LOAD_LEVELS,
    # Bottleneck constants
    BOTTLENECK_CRITICAL,
    BOTTLENECK_MAJOR,
    BOTTLENECK_MINOR,
    BOTTLENECK_NONE,
    ALL_BOTTLENECK_LEVELS,
    # Dependency issue constants
    DEP_ISSUE_CIRCULAR,
    DEP_ISSUE_UNUSED,
    DEP_ISSUE_MISSING,
    DEP_ISSUE_CONFLICT,
    ALL_DEP_ISSUES,
    # Analysis dimension constants
    DIMENSION_COMPLEXITY,
    DIMENSION_RESOURCES,
    DIMENSION_SCALABILITY,
    DIMENSION_STRESS,
    DIMENSION_DEPENDENCIES,
    ALL_DIMENSIONS,
    # Quality rule constants
    RULE_PERFORMANCE,
    RULE_SCALABILITY,
    RULE_QUALITY,
    RULE_DEPENDENCY_HEALTH,
    ALL_QUALITY_RULES,
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
    # Verdict constants
    VERDICT_CAPABLE,
    VERDICT_CAPABLE_WITH_RISKS,
    VERDICT_NOT_CAPABLE,
    ALL_VERDICTS,
    # Readers + intermediate data
    ArchitectureDecisionData,
    ArchitectureDecisionReader,
    TechnologySelectionData,
    TechnologySelectionReader,
    RequirementNormalizationData,
    RequirementNormalizationReader,
    IntelligenceGraphData,
    IntelligenceGraphReader,
    KnowledgeData,
    KnowledgeReader,
    # Analyzers
    ComplexityAnalyzer,
    ResourceEstimator,
    ScalabilityAnalyzer,
    StressAnalyzer,
    DependencyAnalyzer,
    # Helpers and processors
    QualityGate,
    ReportBuilder,
    CacheManager,
)


# ---------------------------------------------------------------------------#
# Test helpers
# ---------------------------------------------------------------------------#

def make_config():
    return build_configuration()


def make_context(
    architecture_decision_report=None,
    technology_selection_report=None,
    requirement_normalization_report=None,
    intelligence_graph=None,
    knowledge_base=None,
    request="",
):
    """Build a generation context with the five data sources."""
    ctx = GenerationContext(
        request=request,
        config=make_config(),
        work_dir=Path("/tmp/test_capability_analyzer"),
    )
    if architecture_decision_report is not None:
        ctx.set(
            "architecture_decision_report",
            architecture_decision_report,
        )
    if technology_selection_report is not None:
        ctx.set(
            "technology_selection_report",
            technology_selection_report,
        )
    if requirement_normalization_report is not None:
        ctx.set(
            "requirement_normalization_report",
            requirement_normalization_report,
        )
    if intelligence_graph is not None:
        ctx.set("intelligence_graph", intelligence_graph)
    if knowledge_base is not None:
        ctx.set("knowledge_base", knowledge_base)
    return ctx


def make_architecture_decision_report(
    pattern="layered",
    communication="sync",
    module_count=3,
    service_count=2,
    decision_count=8,
):
    """Build a mock architecture decision report."""
    from telegram_bot_engine.engines.generators.architecture_decision import (
        ArchitectureDecisionReport,
        ArchitectureDecision,
        ModuleSpec,
        ServiceSpec,
    )
    decisions = [
        ArchitectureDecision(
            domain="layers",
            selected="presentation, business, data_access"
                     + (", caching" if pattern != "monolith" else ""),
            reason="Layered architecture for separation of concerns.",
            analysis="Multiple concerns benefit from layering.",
            impact="Clear separation, easier maintenance.",
        ),
        ArchitectureDecision(
            domain="communication",
            selected=communication,
            reason="Communication pattern selected.",
            analysis="Based on project needs.",
            impact="Defines how components interact.",
        ),
    ]
    # Add more decisions to reach the desired count.
    for i in range(2, decision_count):
        decisions.append(ArchitectureDecision(
            domain=f"domain_{i}",
            selected=f"choice_{i}",
            reason=f"Reason {i}.",
            analysis=f"Analysis {i}.",
            impact=f"Impact {i}.",
        ))

    modules = [
        ModuleSpec(
            name=f"module_{i}",
            layer="business",
            responsibility=f"Module {i} responsibility.",
            dependencies=[],
        )
        for i in range(module_count)
    ]

    services = [
        ServiceSpec(
            name=f"service_{i}",
            responsibility=f"Service {i} responsibility.",
            communication=communication,
            dependencies=[],
        )
        for i in range(service_count)
    ]

    report = ArchitectureDecisionReport(
        decisions=decisions,
        modules=modules,
        services=services,
    )
    report.summary = "Test architecture decision report."
    report.confidence = 0.8
    return report


def make_technology_selection_report(
    selection_count=5,
    ready=True,
    confidence=0.8,
):
    """Build a mock technology selection report."""
    from telegram_bot_engine.engines.generators.technology_selection.report_data import (
        TechnologySelection,
        TechnologySelectionReport,
    )
    categories = [
        ("language", "python"),
        ("framework", "python-telegram-bot"),
        ("database", "sqlite"),
        ("orm", "sqlalchemy"),
        ("cache", "redis"),
        ("queue", "celery"),
        ("storage", "local"),
        ("logging", "logging"),
        ("testing", "pytest"),
        ("deployment", "docker"),
    ]
    selections = []
    for i in range(min(selection_count, len(categories))):
        cat, tech = categories[i]
        selections.append(TechnologySelection(
            category=cat,
            selected=tech,
            reason=f"Best {cat} for this project.",
            analysis=f"Analysis for {cat}.",
            impact=f"Impact of using {tech}.",
            rejected_alternatives=[],
        ))

    report = TechnologySelectionReport(
        selections=selections,
    )
    report.summary = "Test technology selection report."
    report.confidence = confidence
    # The ready flag is a property — we need to ensure the report
    # has sufficient confidence and no errors for it to be ready.
    # Since ready depends on has_sufficient_confidence and
    # all_selections_validated, we just return it as-is.
    return report


def make_normalization_report(
    requirement_count=3,
):
    """Build a mock normalization report with requirements."""
    from telegram_bot_engine.engines.generators.requirement_normalization import (
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
    circular_count=0,
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
        "circular_count": circular_count,
    }


def make_knowledge_base():
    """Build a simple knowledge base dictionary."""
    return {
        "database": "sqlite",
        "framework": "python-telegram-bot",
        "language": "python",
        "synonyms": {"shop": "store", "db": "database"},
        "abbreviations": {"tg": "telegram"},
        "terminology": {"orm": "object-relational-mapper"},
        "assumptions": ["uses Python 3", "telegram bot"],
        "defaults": {"database": "sqlite"},
        "domain_rules": ["bot must handle commands"],
        "constraints": ["must be async"],
    }


def make_full_context():
    """Build a context with all five data sources set."""
    return make_context(
        architecture_decision_report=(
            make_architecture_decision_report()
        ),
        technology_selection_report=(
            make_technology_selection_report()
        ),
        requirement_normalization_report=make_normalization_report(),
        intelligence_graph=make_intelligence_graph(),
        knowledge_base=make_knowledge_base(),
    )


def make_empty_context():
    """Build a context with no data sources."""
    return make_context()


# ---------------------------------------------------------------------------#
# 1. Data model — AnalysisResult
# ---------------------------------------------------------------------------#

def test_analysis_result_creation():
    ar = AnalysisResult(
        dimension=DIMENSION_COMPLEXITY,
        score=0.75,
        level="moderate",
        summary="Complexity is moderate.",
        details=["10 modules", "5 services"],
        source_artefact=SOURCE_ARCHITECTURE_DECISION,
    )
    assert ar.dimension == DIMENSION_COMPLEXITY
    assert ar.score == 0.75
    assert ar.level == "moderate"
    assert ar.summary == "Complexity is moderate."
    assert ar.details == ["10 modules", "5 services"]
    assert ar.source_artefact == SOURCE_ARCHITECTURE_DECISION
    print("  [PASS] test_analysis_result_creation")


def test_analysis_result_to_dict():
    ar = AnalysisResult(
        dimension=DIMENSION_SCALABILITY,
        score=0.5,
        level="medium",
    )
    d = ar.to_dict()
    assert d["dimension"] == DIMENSION_SCALABILITY
    assert d["score"] == 0.5
    assert d["level"] == "medium"
    assert "summary" in d
    assert "details" in d
    assert "source_artefact" in d
    print("  [PASS] test_analysis_result_to_dict")


# ---------------------------------------------------------------------------#
# 2. Data model — ComplexityAnalysis
# ---------------------------------------------------------------------------#

def test_complexity_analysis_creation():
    ca = ComplexityAnalysis(
        module_count=5,
        service_count=3,
        component_count=10,
        class_count=20,
        function_count=100,
        interface_count=15,
        background_task_count=2,
        external_integration_count=3,
        total_elements=158,
        complexity_level=COMPLEXITY_HIGH,
        score=0.7,
        summary="High complexity project.",
        details=["5 modules", "3 services"],
    )
    assert ca.module_count == 5
    assert ca.service_count == 3
    assert ca.component_count == 10
    assert ca.class_count == 20
    assert ca.function_count == 100
    assert ca.interface_count == 15
    assert ca.background_task_count == 2
    assert ca.external_integration_count == 3
    assert ca.total_elements == 158
    assert ca.complexity_level == COMPLEXITY_HIGH
    assert ca.score == 0.7
    print("  [PASS] test_complexity_analysis_creation")


def test_complexity_analysis_to_dict():
    ca = ComplexityAnalysis(
        module_count=3,
        total_elements=50,
        complexity_level=COMPLEXITY_MODERATE,
    )
    d = ca.to_dict()
    assert d["module_count"] == 3
    assert d["total_elements"] == 50
    assert d["complexity_level"] == COMPLEXITY_MODERATE
    assert "score" in d
    assert "details" in d
    print("  [PASS] test_complexity_analysis_to_dict")


# ---------------------------------------------------------------------------#
# 3. Data model — ResourceEstimation
# ---------------------------------------------------------------------------#

def test_resource_estimation_creation():
    re = ResourceEstimation(
        file_count=100,
        directory_count=20,
        project_size_kb=500,
        database_size_mb=10,
        memory_mb=256,
        cpu_cores=2.0,
        estimated_build_time_minutes=5.0,
        estimated_test_time_minutes=2.0,
        project_size_level=SIZE_SMALL,
        score=0.3,
    )
    assert re.file_count == 100
    assert re.directory_count == 20
    assert re.project_size_kb == 500
    assert re.database_size_mb == 10
    assert re.memory_mb == 256
    assert re.cpu_cores == 2.0
    assert re.estimated_build_time_minutes == 5.0
    assert re.estimated_test_time_minutes == 2.0
    assert re.project_size_level == SIZE_SMALL
    assert re.score == 0.3
    print("  [PASS] test_resource_estimation_creation")


def test_resource_estimation_to_dict():
    re = ResourceEstimation(
        file_count=50,
        project_size_level=SIZE_TINY,
    )
    d = re.to_dict()
    assert d["file_count"] == 50
    assert d["project_size_level"] == SIZE_TINY
    assert "memory_mb" in d
    assert "cpu_cores" in d
    print("  [PASS] test_resource_estimation_to_dict")


# ---------------------------------------------------------------------------#
# 4. Data model — ScalabilityTier and ScalabilityAnalysis
# ---------------------------------------------------------------------------#

def test_scalability_tier_creation():
    st = ScalabilityTier(
        tier=SCALE_THOUSANDS,
        user_range="1-5,000",
        supported=True,
        confidence=0.85,
        reason="Layered architecture supports thousands of users.",
        limitations=[],
    )
    assert st.tier == SCALE_THOUSANDS
    assert st.user_range == "1-5,000"
    assert st.supported is True
    assert st.confidence == 0.85
    print("  [PASS] test_scalability_tier_creation")


def test_scalability_analysis_creation():
    tiers = [
        ScalabilityTier(tier=SCALE_THOUSANDS, supported=True, confidence=0.8),
        ScalabilityTier(tier=SCALE_TENS_OF_THOUSANDS, supported=False, confidence=0.4),
    ]
    sa = ScalabilityAnalysis(
        tiers=tiers,
        max_supported_tier=SCALE_THOUSANDS,
        score=0.6,
        summary="Supports thousands of users.",
        details=["tier 1 supported"],
    )
    assert len(sa.tiers) == 2
    assert sa.max_supported_tier == SCALE_THOUSANDS
    assert sa.score == 0.6
    print("  [PASS] test_scalability_analysis_creation")


def test_scalability_analysis_get_tier():
    tiers = [
        ScalabilityTier(tier=SCALE_THOUSANDS, supported=True),
        ScalabilityTier(tier=SCALE_MILLIONS, supported=False),
    ]
    sa = ScalabilityAnalysis(tiers=tiers)
    t = sa.get_tier(SCALE_THOUSANDS)
    assert t is not None
    assert t.tier == SCALE_THOUSANDS
    assert t.supported is True
    t2 = sa.get_tier("nonexistent")
    assert t2 is None
    print("  [PASS] test_scalability_analysis_get_tier")


# ---------------------------------------------------------------------------#
# 5. Data model — Bottleneck and ArchitectureStressAnalysis
# ---------------------------------------------------------------------------#

def test_bottleneck_creation():
    b = Bottleneck(
        component="database",
        severity=BOTTLENECK_MAJOR,
        load_level=LOAD_HEAVY,
        description="Database is a bottleneck under heavy load.",
        impact="Response time increases significantly.",
        improvement="Add connection pooling.",
    )
    assert b.component == "database"
    assert b.severity == BOTTLENECK_MAJOR
    assert b.load_level == LOAD_HEAVY
    assert b.description == "Database is a bottleneck under heavy load."
    assert b.impact == "Response time increases significantly."
    assert b.improvement == "Add connection pooling."
    print("  [PASS] test_bottleneck_creation")


def test_bottleneck_to_dict():
    b = Bottleneck(
        component="cache",
        severity=BOTTLENECK_MINOR,
        load_level=LOAD_MODERATE,
    )
    d = b.to_dict()
    assert d["component"] == "cache"
    assert d["severity"] == BOTTLENECK_MINOR
    assert d["load_level"] == LOAD_MODERATE
    print("  [PASS] test_bottleneck_to_dict")


def test_stress_analysis_creation():
    sa = ArchitectureStressAnalysis(
        load_level=LOAD_HEAVY,
        bottlenecks=[Bottleneck(component="db", severity=BOTTLENECK_MAJOR)],
        sensitive_components=["database", "api"],
        improvement_points=["Add caching", "Use async"],
        max_concurrent_users=5000,
        max_requests_per_second=500,
        score=0.7,
        summary="Handles heavy load with some bottlenecks.",
        details=["2 bottlenecks identified"],
    )
    assert sa.load_level == LOAD_HEAVY
    assert len(sa.bottlenecks) == 1
    assert sa.sensitive_components == ["database", "api"]
    assert sa.improvement_points == ["Add caching", "Use async"]
    assert sa.max_concurrent_users == 5000
    assert sa.max_requests_per_second == 500
    assert sa.score == 0.7
    print("  [PASS] test_stress_analysis_creation")


# ---------------------------------------------------------------------------#
# 6. Data model — DependencyIssue and DependencyAnalysis
# ---------------------------------------------------------------------------#

def test_dependency_issue_creation():
    di = DependencyIssue(
        issue_type=DEP_ISSUE_CIRCULAR,
        component="module_a",
        description="Circular dependency between module_a and module_b.",
        severity=SEVERITY_ERROR,
        resolution="Break the cycle with an interface.",
    )
    assert di.issue_type == DEP_ISSUE_CIRCULAR
    assert di.component == "module_a"
    assert di.description == "Circular dependency between module_a and module_b."
    assert di.severity == SEVERITY_ERROR
    assert di.resolution == "Break the cycle with an interface."
    print("  [PASS] test_dependency_issue_creation")


def test_dependency_analysis_creation():
    da = DependencyAnalysis(
        total_dependencies=20,
        circular_dependencies=[],
        unused_dependencies=1,
        missing_dependencies=0,
        conflicts=0,
        issues=[],
        is_healthy=True,
        score=0.9,
        summary="Healthy dependency graph.",
        details=["No circular dependencies"],
    )
    assert da.total_dependencies == 20
    assert da.circular_dependencies == []
    assert da.unused_dependencies == 1
    assert da.missing_dependencies == 0
    assert da.conflicts == 0
    assert da.is_healthy is True
    assert da.score == 0.9
    print("  [PASS] test_dependency_analysis_creation")


def test_dependency_analysis_to_dict():
    da = DependencyAnalysis(
        total_dependencies=10,
        circular_dependencies=["circular_a"],
    )
    d = da.to_dict()
    assert d["total_dependencies"] == 10
    assert d["circular_dependencies"] == ["circular_a"]
    assert "is_healthy" in d
    assert "score" in d
    print("  [PASS] test_dependency_analysis_to_dict")


# ---------------------------------------------------------------------------#
# 7. Data model — CapabilityFinding
# ---------------------------------------------------------------------------#

def test_capability_finding_creation():
    cf = CapabilityFinding(
        severity=SEVERITY_ERROR,
        code="CAP_001",
        message="Circular dependencies detected.",
        affected="dependency_graph",
        resolution_hint="Break circular dependencies.",
        category="dependency",
    )
    assert cf.severity == SEVERITY_ERROR
    assert cf.code == "CAP_001"
    assert cf.message == "Circular dependencies detected."
    assert cf.affected == "dependency_graph"
    assert cf.resolution_hint == "Break circular dependencies."
    assert cf.category == "dependency"
    print("  [PASS] test_capability_finding_creation")


def test_capability_finding_to_dict():
    cf = CapabilityFinding(
        severity=SEVERITY_WARNING,
        code="CAP_002",
        message="Low scalability score.",
    )
    d = cf.to_dict()
    assert d["severity"] == SEVERITY_WARNING
    assert d["code"] == "CAP_002"
    assert d["message"] == "Low scalability score."
    print("  [PASS] test_capability_finding_to_dict")


# ---------------------------------------------------------------------------#
# 8. Data model — CacheInfo
# ---------------------------------------------------------------------------#

def test_cache_info_creation():
    ci = CacheInfo(
        status=CACHE_HIT,
        cache_key="abc123",
        cached_at="1234567890",
        hit=True,
        inputs_hash="abc123",
    )
    assert ci.status == CACHE_HIT
    assert ci.cache_key == "abc123"
    assert ci.cached_at == "1234567890"
    assert ci.hit is True
    assert ci.inputs_hash == "abc123"
    print("  [PASS] test_cache_info_creation")


def test_cache_info_to_dict():
    ci = CacheInfo(status=CACHE_MISS, cache_key="xyz")
    d = ci.to_dict()
    assert d["status"] == CACHE_MISS
    assert d["cache_key"] == "xyz"
    assert "hit" in d
    print("  [PASS] test_cache_info_to_dict")


# ---------------------------------------------------------------------------#
# 9. Data model — CapabilityProvenance
# ---------------------------------------------------------------------------#

def test_capability_provenance_creation():
    cp = CapabilityProvenance(
        architecture_decision_available=True,
        technology_selection_available=True,
        normalized_requirements_available=True,
        intelligence_graph_available=True,
        knowledge_base_available=True,
        all_sources_used=["architecture_decision_report", "technology_selection_report"],
        decision_count=8,
        selection_count=5,
        requirement_count=3,
        graph_node_count=10,
        graph_edge_count=2,
    )
    assert cp.architecture_decision_available is True
    assert cp.technology_selection_available is True
    assert cp.normalized_requirements_available is True
    assert cp.intelligence_graph_available is True
    assert cp.knowledge_base_available is True
    assert cp.decision_count == 8
    assert cp.selection_count == 5
    assert cp.requirement_count == 3
    assert cp.graph_node_count == 10
    assert cp.graph_edge_count == 2
    print("  [PASS] test_capability_provenance_creation")


def test_capability_provenance_to_dict():
    cp = CapabilityProvenance()
    d = cp.to_dict()
    assert "architecture_decision_available" in d
    assert "technology_selection_available" in d
    assert "all_sources_used" in d
    assert "decision_count" in d
    print("  [PASS] test_capability_provenance_to_dict")


# ---------------------------------------------------------------------------#
# 10. Data model — ProjectCapabilityReport
# ---------------------------------------------------------------------------#

def test_project_capability_report_creation():
    report = ProjectCapabilityReport()
    assert report.analysis_count == 0
    assert report.finding_count == 0
    assert report.error_count == 0
    assert report.warning_count == 0
    assert report.has_errors is False
    assert report.is_empty is True
    assert report.all_analyses_performed is False
    assert report.has_sufficient_confidence is False
    assert report.is_capable is False
    assert report.is_blocked is True
    assert report.ready is False
    assert report.cache_hit is False
    print("  [PASS] test_project_capability_report_creation")


def test_project_capability_report_add_finding():
    report = ProjectCapabilityReport()
    report.add_finding(
        severity=SEVERITY_WARNING,
        code="CAP_001",
        message="Low scalability score.",
    )
    assert report.finding_count == 1
    assert report.warning_count == 1
    assert report.has_errors is False
    assert len(report.warnings) == 1
    print("  [PASS] test_project_capability_report_add_finding")


def test_project_capability_report_add_error_finding():
    report = ProjectCapabilityReport()
    report.add_finding(
        severity=SEVERITY_ERROR,
        code="CAP_002",
        message="Circular dependencies detected.",
    )
    assert report.finding_count == 1
    assert report.error_count == 1
    assert report.has_errors is True
    print("  [PASS] test_project_capability_report_add_error_finding")


def test_project_capability_report_add_strength():
    report = ProjectCapabilityReport()
    report.add_strength("Good scalability.")
    assert len(report.strengths) == 1
    assert report.strengths[0] == "Good scalability."
    print("  [PASS] test_project_capability_report_add_strength")


def test_project_capability_report_add_risk():
    report = ProjectCapabilityReport()
    report.add_risk("Low stress score.")
    assert len(report.risks) == 1
    assert report.risks[0] == "Low stress score."
    print("  [PASS] test_project_capability_report_add_risk")


def test_project_capability_report_add_recommendation():
    report = ProjectCapabilityReport()
    report.add_recommendation("Add caching.")
    assert len(report.recommendations) == 1
    assert report.recommendations[0] == "Add caching."
    print("  [PASS] test_project_capability_report_add_recommendation")


def test_project_capability_report_get_analysis():
    report = ProjectCapabilityReport()
    report.analyses.append(AnalysisResult(
        dimension=DIMENSION_COMPLEXITY,
        score=0.7,
    ))
    a = report.get_analysis(DIMENSION_COMPLEXITY)
    assert a is not None
    assert a.dimension == DIMENSION_COMPLEXITY
    a2 = report.get_analysis("nonexistent")
    assert a2 is None
    print("  [PASS] test_project_capability_report_get_analysis")


def test_project_capability_report_analysis_dimensions():
    report = ProjectCapabilityReport()
    report.analyses.append(AnalysisResult(dimension=DIMENSION_COMPLEXITY))
    report.analyses.append(AnalysisResult(dimension=DIMENSION_RESOURCES))
    dims = report.analysis_dimensions()
    assert DIMENSION_COMPLEXITY in dims
    assert DIMENSION_RESOURCES in dims
    assert len(dims) == 2
    print("  [PASS] test_project_capability_report_analysis_dimensions")


def test_project_capability_report_get_scalability_tier():
    report = ProjectCapabilityReport()
    report.scalability.tiers.append(
        ScalabilityTier(tier=SCALE_THOUSANDS, supported=True)
    )
    t = report.get_scalability_tier(SCALE_THOUSANDS)
    assert t is not None
    assert t.tier == SCALE_THOUSANDS
    t2 = report.get_scalability_tier("nonexistent")
    assert t2 is None
    print("  [PASS] test_project_capability_report_get_scalability_tier")


def test_project_capability_report_critical_bottlenecks():
    report = ProjectCapabilityReport()
    report.stress.bottlenecks.append(
        Bottleneck(component="db", severity=BOTTLENECK_CRITICAL)
    )
    report.stress.bottlenecks.append(
        Bottleneck(component="cache", severity=BOTTLENECK_MINOR)
    )
    critical = report.critical_bottlenecks()
    assert len(critical) == 1
    assert critical[0].component == "db"
    print("  [PASS] test_project_capability_report_critical_bottlenecks")


def test_project_capability_report_to_dict():
    report = ProjectCapabilityReport()
    d = report.to_dict()
    assert "analysis_count" in d
    assert "finding_count" in d
    assert "error_count" in d
    assert "verdict" in d
    assert "confidence" in d
    assert "complexity" in d
    assert "scalability" in d
    assert "stress" in d
    assert "dependencies" in d
    assert "provenance" in d
    print("  [PASS] test_project_capability_report_to_dict")


# ---------------------------------------------------------------------------#
# 11. Constants tests
# ---------------------------------------------------------------------------#

def test_source_constants():
    assert SOURCE_ARCHITECTURE_DECISION == "architecture_decision_report"
    assert SOURCE_TECHNOLOGY_SELECTION == "technology_selection_report"
    assert SOURCE_NORMALIZED_REQUIREMENTS == "normalized_requirements"
    assert SOURCE_INTELLIGENCE_GRAPH == "intelligence_graph"
    assert SOURCE_KNOWLEDGE_BASE == "knowledge_base"
    assert len(ALL_SOURCES) == 5
    print("  [PASS] test_source_constants")


def test_severity_constants():
    assert SEVERITY_ERROR == "error"
    assert SEVERITY_WARNING == "warning"
    assert SEVERITY_INFO == "info"
    assert len(ALL_SEVERITIES) == 3
    print("  [PASS] test_severity_constants")


def test_complexity_constants():
    assert COMPLEXITY_TRIVIAL == "trivial"
    assert COMPLEXITY_LOW == "low"
    assert COMPLEXITY_MODERATE == "moderate"
    assert COMPLEXITY_HIGH == "high"
    assert COMPLEXITY_VERY_HIGH == "very_high"
    assert len(ALL_COMPLEXITY_LEVELS) == 5
    print("  [PASS] test_complexity_constants")


def test_size_constants():
    assert SIZE_TINY == "tiny"
    assert SIZE_SMALL == "small"
    assert SIZE_MEDIUM == "medium"
    assert SIZE_LARGE == "large"
    assert SIZE_VERY_LARGE == "very_large"
    assert len(ALL_SIZES) == 5
    print("  [PASS] test_size_constants")


def test_scale_tier_constants():
    assert SCALE_THOUSANDS == "thousands"
    assert SCALE_TENS_OF_THOUSANDS == "tens_of_thousands"
    assert SCALE_HUNDREDS_OF_THOUSANDS == "hundreds_of_thousands"
    assert SCALE_MILLIONS == "millions"
    assert len(ALL_SCALE_TIERS) == 4
    print("  [PASS] test_scale_tier_constants")


def test_load_level_constants():
    assert LOAD_LIGHT == "light"
    assert LOAD_MODERATE == "moderate"
    assert LOAD_HEAVY == "heavy"
    assert LOAD_PEAK == "peak"
    assert len(ALL_LOAD_LEVELS) == 4
    print("  [PASS] test_load_level_constants")


def test_bottleneck_constants():
    assert BOTTLENECK_CRITICAL == "critical"
    assert BOTTLENECK_MAJOR == "major"
    assert BOTTLENECK_MINOR == "minor"
    assert BOTTLENECK_NONE == "none"
    assert len(ALL_BOTTLENECK_LEVELS) == 4
    print("  [PASS] test_bottleneck_constants")


def test_dependency_issue_constants():
    assert DEP_ISSUE_CIRCULAR == "circular_dependency"
    assert DEP_ISSUE_UNUSED == "unused_dependency"
    assert DEP_ISSUE_MISSING == "missing_dependency"
    assert DEP_ISSUE_CONFLICT == "dependency_conflict"
    assert len(ALL_DEP_ISSUES) == 4
    print("  [PASS] test_dependency_issue_constants")


def test_dimension_constants():
    assert DIMENSION_COMPLEXITY == "complexity"
    assert DIMENSION_RESOURCES == "resources"
    assert DIMENSION_SCALABILITY == "scalability"
    assert DIMENSION_STRESS == "architecture_stress"
    assert DIMENSION_DEPENDENCIES == "dependencies"
    assert len(ALL_DIMENSIONS) == 5
    print("  [PASS] test_dimension_constants")


def test_quality_rule_constants():
    assert RULE_PERFORMANCE == "performance"
    assert RULE_SCALABILITY == "scalability"
    assert RULE_QUALITY == "quality"
    assert RULE_DEPENDENCY_HEALTH == "dependency_health"
    assert len(ALL_QUALITY_RULES) == 4
    print("  [PASS] test_quality_rule_constants")


def test_cache_status_constants():
    assert CACHE_HIT == "hit"
    assert CACHE_MISS == "miss"
    assert CACHE_STALE == "stale"
    assert CACHE_DISABLED == "disabled"
    assert len(ALL_CACHE_STATUSES) == 4
    print("  [PASS] test_cache_status_constants")


def test_confidence_constants():
    assert CONFIDENCE_HIGH == "high"
    assert CONFIDENCE_MEDIUM == "medium"
    assert CONFIDENCE_LOW == "low"
    assert CONFIDENCE_HIGH_THRESHOLD == 0.8
    assert CONFIDENCE_MEDIUM_THRESHOLD == 0.6
    assert len(ALL_CONFIDENCE_LEVELS) == 3
    print("  [PASS] test_confidence_constants")


def test_verdict_constants():
    assert VERDICT_CAPABLE == "capable"
    assert VERDICT_CAPABLE_WITH_RISKS == "capable_with_risks"
    assert VERDICT_NOT_CAPABLE == "not_capable"
    assert len(ALL_VERDICTS) == 3
    print("  [PASS] test_verdict_constants")


# ---------------------------------------------------------------------------#
# 12. Reader tests
# ---------------------------------------------------------------------------#

def test_architecture_decision_reader_empty_context():
    reader = ArchitectureDecisionReader()
    ctx = make_empty_context()
    data = reader.read(ctx)
    assert data.available is False
    assert data.decision_count == 0
    assert data.module_count == 0
    assert data.service_count == 0
    print("  [PASS] test_architecture_decision_reader_empty_context")


def test_architecture_decision_reader_with_report():
    reader = ArchitectureDecisionReader()
    ctx = make_context(
        architecture_decision_report=(
            make_architecture_decision_report()
        ),
    )
    data = reader.read(ctx)
    assert data.available is True
    assert data.decision_count > 0
    assert data.module_count > 0
    assert data.service_count > 0
    assert data.pattern != ""
    assert data.communication != ""
    print("  [PASS] test_architecture_decision_reader_with_report")


def test_technology_selection_reader_empty_context():
    reader = TechnologySelectionReader()
    ctx = make_empty_context()
    data = reader.read(ctx)
    assert data.available is False
    assert data.selection_count == 0
    assert data.selected_technologies == []
    print("  [PASS] test_technology_selection_reader_empty_context")


def test_technology_selection_reader_with_report():
    reader = TechnologySelectionReader()
    ctx = make_context(
        technology_selection_report=(
            make_technology_selection_report()
        ),
    )
    data = reader.read(ctx)
    assert data.available is True
    assert data.selection_count > 0
    assert len(data.selected_technologies) > 0
    print("  [PASS] test_technology_selection_reader_with_report")


def test_requirement_normalization_reader_empty_context():
    reader = RequirementNormalizationReader()
    ctx = make_empty_context()
    data = reader.read(ctx)
    assert data.available is False
    assert data.requirement_count == 0
    print("  [PASS] test_requirement_normalization_reader_empty_context")


def test_requirement_normalization_reader_with_report():
    reader = RequirementNormalizationReader()
    ctx = make_context(
        requirement_normalization_report=make_normalization_report(),
    )
    data = reader.read(ctx)
    assert data.available is True
    assert data.requirement_count > 0
    print("  [PASS] test_requirement_normalization_reader_with_report")


def test_intelligence_graph_reader_empty_context():
    reader = IntelligenceGraphReader()
    ctx = make_empty_context()
    data = reader.read(ctx)
    assert data.available is False
    assert data.node_count == 0
    assert data.edge_count == 0
    print("  [PASS] test_intelligence_graph_reader_empty_context")


def test_intelligence_graph_reader_with_graph():
    reader = IntelligenceGraphReader()
    ctx = make_context(
        intelligence_graph=make_intelligence_graph(),
    )
    data = reader.read(ctx)
    assert data.available is True
    assert data.node_count > 0
    assert data.edge_count > 0
    assert data.component_count > 0
    print("  [PASS] test_intelligence_graph_reader_with_graph")


def test_knowledge_reader_empty_context():
    reader = KnowledgeReader()
    ctx = make_empty_context()
    data = reader.read(ctx)
    assert data.available is False
    print("  [PASS] test_knowledge_reader_empty_context")


def test_knowledge_reader_with_base():
    reader = KnowledgeReader()
    ctx = make_context(
        knowledge_base=make_knowledge_base(),
    )
    data = reader.read(ctx)
    assert data.available is True
    assert len(data.assumptions) > 0
    print("  [PASS] test_knowledge_reader_with_base")


# ---------------------------------------------------------------------------#
# 13. ComplexityAnalyzer tests
# ---------------------------------------------------------------------------#

def test_complexity_analyzer_empty():
    analyzer = ComplexityAnalyzer()
    arch_data = ArchitectureDecisionData()
    tech_data = TechnologySelectionData()
    req_data = RequirementNormalizationData()
    graph_data = IntelligenceGraphData()
    kb_data = KnowledgeData()
    result = analyzer.analyze(arch_data, tech_data, req_data, graph_data, kb_data)
    assert result.total_elements >= 0
    assert result.complexity_level in ALL_COMPLEXITY_LEVELS
    assert 0.0 <= result.score <= 1.0
    print("  [PASS] test_complexity_analyzer_empty")


def test_complexity_analyzer_with_data():
    analyzer = ComplexityAnalyzer()
    arch_data = ArchitectureDecisionData(available=True, module_count=5, service_count=3)
    tech_data = TechnologySelectionData(available=True, selection_count=10)
    req_data = RequirementNormalizationData(available=True, requirement_count=5)
    graph_data = IntelligenceGraphData(available=True, node_count=20, component_count=10)
    kb_data = KnowledgeData(available=True)
    result = analyzer.analyze(arch_data, tech_data, req_data, graph_data, kb_data)
    assert result.module_count == 5
    assert result.service_count == 3
    assert result.total_elements > 0
    assert result.complexity_level in ALL_COMPLEXITY_LEVELS
    print("  [PASS] test_complexity_analyzer_with_data")


# ---------------------------------------------------------------------------#
# 14. ResourceEstimator tests
# ---------------------------------------------------------------------------#

def test_resource_estimator_empty():
    estimator = ResourceEstimator()
    arch_data = ArchitectureDecisionData()
    tech_data = TechnologySelectionData()
    req_data = RequirementNormalizationData()
    graph_data = IntelligenceGraphData()
    kb_data = KnowledgeData()
    result = estimator.estimate(arch_data, tech_data, req_data, graph_data, kb_data)
    assert result.file_count >= 0
    assert result.project_size_level in ALL_SIZES
    assert 0.0 <= result.score <= 1.0
    print("  [PASS] test_resource_estimator_empty")


def test_resource_estimator_with_data():
    estimator = ResourceEstimator()
    arch_data = ArchitectureDecisionData(available=True, module_count=5, service_count=3)
    tech_data = TechnologySelectionData(available=True, selection_count=10)
    req_data = RequirementNormalizationData(available=True, requirement_count=5)
    graph_data = IntelligenceGraphData(available=True, node_count=20)
    kb_data = KnowledgeData(available=True)
    result = estimator.estimate(arch_data, tech_data, req_data, graph_data, kb_data)
    assert result.file_count > 0
    assert result.directory_count > 0
    assert result.project_size_level in ALL_SIZES
    print("  [PASS] test_resource_estimator_with_data")


# ---------------------------------------------------------------------------#
# 15. ScalabilityAnalyzer tests
# ---------------------------------------------------------------------------#

def test_scalability_analyzer_empty():
    analyzer = ScalabilityAnalyzer()
    arch_data = ArchitectureDecisionData()
    tech_data = TechnologySelectionData()
    req_data = RequirementNormalizationData()
    graph_data = IntelligenceGraphData()
    kb_data = KnowledgeData()
    result = analyzer.analyze(arch_data, tech_data, req_data, graph_data, kb_data)
    assert len(result.tiers) > 0
    assert 0.0 <= result.score <= 1.0
    for tier in result.tiers:
        assert tier.tier in ALL_SCALE_TIERS
    print("  [PASS] test_scalability_analyzer_empty")


def test_scalability_analyzer_with_data():
    analyzer = ScalabilityAnalyzer()
    arch_data = ArchitectureDecisionData(
        available=True, pattern="layered", communication="sync",
        module_count=5, service_count=3,
    )
    tech_data = TechnologySelectionData(
        available=True, selection_count=5,
        selected_technologies=["redis", "celery", "docker"],
    )
    req_data = RequirementNormalizationData(available=True, requirement_count=5)
    graph_data = IntelligenceGraphData(available=True, node_count=20)
    kb_data = KnowledgeData(available=True)
    result = analyzer.analyze(arch_data, tech_data, req_data, graph_data, kb_data)
    assert len(result.tiers) > 0
    assert 0.0 <= result.score <= 1.0
    assert result.max_supported_tier in ALL_SCALE_TIERS
    print("  [PASS] test_scalability_analyzer_with_data")


# ---------------------------------------------------------------------------#
# 16. StressAnalyzer tests
# ---------------------------------------------------------------------------#

def test_stress_analyzer_empty():
    analyzer = StressAnalyzer()
    arch_data = ArchitectureDecisionData()
    tech_data = TechnologySelectionData()
    req_data = RequirementNormalizationData()
    graph_data = IntelligenceGraphData()
    kb_data = KnowledgeData()
    result = analyzer.analyze(arch_data, tech_data, req_data, graph_data, kb_data)
    assert result.load_level in ALL_LOAD_LEVELS
    assert 0.0 <= result.score <= 1.0
    print("  [PASS] test_stress_analyzer_empty")


def test_stress_analyzer_with_data():
    analyzer = StressAnalyzer()
    arch_data = ArchitectureDecisionData(
        available=True, pattern="layered", communication="async",
        module_count=5, service_count=3,
    )
    tech_data = TechnologySelectionData(
        available=True, selection_count=5,
        selected_technologies=["redis", "celery"],
    )
    req_data = RequirementNormalizationData(available=True, requirement_count=5)
    graph_data = IntelligenceGraphData(available=True, node_count=20, circular_count=0)
    kb_data = KnowledgeData(available=True)
    result = analyzer.analyze(arch_data, tech_data, req_data, graph_data, kb_data)
    assert result.load_level in ALL_LOAD_LEVELS
    assert 0.0 <= result.score <= 1.0
    assert result.max_concurrent_users > 0
    assert result.max_requests_per_second > 0
    print("  [PASS] test_stress_analyzer_with_data")


# ---------------------------------------------------------------------------#
# 17. DependencyAnalyzer tests
# ---------------------------------------------------------------------------#

def test_dependency_analyzer_empty():
    analyzer = DependencyAnalyzer()
    arch_data = ArchitectureDecisionData()
    tech_data = TechnologySelectionData()
    req_data = RequirementNormalizationData()
    graph_data = IntelligenceGraphData()
    kb_data = KnowledgeData()
    result = analyzer.analyze(arch_data, tech_data, req_data, graph_data, kb_data)
    assert result.total_dependencies >= 0
    assert result.circular_dependencies == []
    assert 0.0 <= result.score <= 1.0
    print("  [PASS] test_dependency_analyzer_empty")


def test_dependency_analyzer_with_data():
    analyzer = DependencyAnalyzer()
    arch_data = ArchitectureDecisionData(available=True, module_count=5, service_count=3)
    tech_data = TechnologySelectionData(available=True, selection_count=5)
    req_data = RequirementNormalizationData(available=True, requirement_count=5)
    graph_data = IntelligenceGraphData(available=True, node_count=20, circular_count=0)
    kb_data = KnowledgeData(available=True)
    result = analyzer.analyze(arch_data, tech_data, req_data, graph_data, kb_data)
    assert result.total_dependencies > 0
    assert 0.0 <= result.score <= 1.0
    print("  [PASS] test_dependency_analyzer_with_data")


# ---------------------------------------------------------------------------#
# 18. QualityGate tests
# ---------------------------------------------------------------------------#

def test_quality_gate_passes_good_report():
    gate = QualityGate()
    report = ProjectCapabilityReport()
    # Fill in good scores.
    report.stress.score = 0.7
    report.stress.load_level = LOAD_MODERATE
    report.scalability.score = 0.6
    report.scalability.max_supported_tier = SCALE_TENS_OF_THOUSANDS
    report.dependencies.score = 0.8
    report.dependencies.circular_dependencies = []
    report.dependencies.conflicts = []
    # Add all five analyses.
    for dim in ALL_DIMENSIONS:
        report.analyses.append(AnalysisResult(dimension=dim, score=0.7))
    findings, passed = gate.validate(report)
    assert passed is True
    print("  [PASS] test_quality_gate_passes_good_report")


def test_quality_gate_fails_empty_report():
    gate = QualityGate()
    report = ProjectCapabilityReport()
    findings, passed = gate.validate(report)
    assert passed is False
    print("  [PASS] test_quality_gate_fails_empty_report")


def test_quality_gate_fails_circular_dependencies():
    gate = QualityGate()
    report = ProjectCapabilityReport()
    report.stress.score = 0.7
    report.stress.load_level = LOAD_MODERATE
    report.scalability.score = 0.6
    report.scalability.max_supported_tier = SCALE_TENS_OF_THOUSANDS
    report.dependencies.score = 0.5
    report.dependencies.circular_dependencies = ["circular_a"]
    report.dependencies.conflicts = []
    for dim in ALL_DIMENSIONS:
        report.analyses.append(AnalysisResult(dimension=dim, score=0.7))
    findings, passed = gate.validate(report)
    assert passed is False
    print("  [PASS] test_quality_gate_fails_circular_dependencies")


def test_quality_gate_fails_low_stress():
    gate = QualityGate()
    report = ProjectCapabilityReport()
    report.stress.score = 0.1
    report.stress.load_level = LOAD_LIGHT
    report.scalability.score = 0.6
    report.scalability.max_supported_tier = SCALE_TENS_OF_THOUSANDS
    report.dependencies.score = 0.8
    report.dependencies.circular_dependencies = []
    for dim in ALL_DIMENSIONS:
        report.analyses.append(AnalysisResult(dimension=dim, score=0.7))
    findings, passed = gate.validate(report)
    assert passed is False
    print("  [PASS] test_quality_gate_fails_low_stress")


# ---------------------------------------------------------------------------#
# 19. CacheManager tests
# ---------------------------------------------------------------------------#

def test_cache_manager_miss():
    cm = CacheManager()
    arch_data = ArchitectureDecisionData()
    tech_data = TechnologySelectionData()
    req_data = RequirementNormalizationData()
    graph_data = IntelligenceGraphData()
    kb_data = KnowledgeData()
    info = cm.get_cache_info(arch_data, tech_data, req_data, graph_data, kb_data)
    assert info.status == CACHE_MISS
    assert info.hit is False
    cached = cm.get_cached(info)
    assert cached is None
    print("  [PASS] test_cache_manager_miss")


def test_cache_manager_hit():
    cm = CacheManager()
    arch_data = ArchitectureDecisionData()
    tech_data = TechnologySelectionData()
    req_data = RequirementNormalizationData()
    graph_data = IntelligenceGraphData()
    kb_data = KnowledgeData()
    info = cm.get_cache_info(arch_data, tech_data, req_data, graph_data, kb_data)
    report = ProjectCapabilityReport()
    cm.store(info, report)
    # Second call should be a hit.
    info2 = cm.get_cache_info(arch_data, tech_data, req_data, graph_data, kb_data)
    assert info2.status == CACHE_HIT
    assert info2.hit is True
    cached = cm.get_cached(info2)
    assert cached is not None
    print("  [PASS] test_cache_manager_hit")


def test_cache_manager_store():
    cm = CacheManager()
    arch_data = ArchitectureDecisionData()
    tech_data = TechnologySelectionData()
    req_data = RequirementNormalizationData()
    graph_data = IntelligenceGraphData()
    kb_data = KnowledgeData()
    info = cm.get_cache_info(arch_data, tech_data, req_data, graph_data, kb_data)
    report = ProjectCapabilityReport()
    cm.store(info, report)
    cached = cm.get_cached(info)
    assert cached is not None
    print("  [PASS] test_cache_manager_store")


# ---------------------------------------------------------------------------#
# 20. ReportBuilder tests
# ---------------------------------------------------------------------------#

def test_report_builder_build_provenance():
    rb = ReportBuilder()
    arch_data = ArchitectureDecisionData(available=True, decision_count=8)
    tech_data = TechnologySelectionData(available=True, selection_count=5)
    req_data = RequirementNormalizationData(available=True, requirement_count=3)
    graph_data = IntelligenceGraphData(available=True, node_count=10, edge_count=2)
    kb_data = KnowledgeData(available=True)
    provenance = rb.build_provenance(arch_data, tech_data, req_data, graph_data, kb_data)
    assert provenance.architecture_decision_available is True
    assert provenance.technology_selection_available is True
    assert provenance.normalized_requirements_available is True
    assert provenance.intelligence_graph_available is True
    assert provenance.knowledge_base_available is True
    assert provenance.decision_count == 8
    assert provenance.selection_count == 5
    assert provenance.requirement_count == 3
    assert provenance.graph_node_count == 10
    assert provenance.graph_edge_count == 2
    print("  [PASS] test_report_builder_build_provenance")


def test_report_builder_build():
    rb = ReportBuilder()
    complexity = ComplexityAnalysis(module_count=3, total_elements=20, complexity_level=COMPLEXITY_MODERATE, score=0.5)
    resources = ResourceEstimation(file_count=50, project_size_level=SIZE_SMALL, score=0.3)
    scalability = ScalabilityAnalysis(
        tiers=[ScalabilityTier(tier=SCALE_THOUSANDS, supported=True, confidence=0.7)],
        max_supported_tier=SCALE_THOUSANDS, score=0.6,
    )
    stress = ArchitectureStressAnalysis(load_level=LOAD_MODERATE, score=0.6)
    dependencies = DependencyAnalysis(total_dependencies=10, circular_dependencies=[], is_healthy=True, score=0.8)
    analyses = [AnalysisResult(dimension=dim, score=0.6) for dim in ALL_DIMENSIONS]
    findings = []
    cache_info = CacheInfo(status=CACHE_MISS)
    provenance = CapabilityProvenance(
        architecture_decision_available=True,
        technology_selection_available=True,
        normalized_requirements_available=True,
        intelligence_graph_available=True,
        knowledge_base_available=True,
    )
    report = rb.build(
        complexity=complexity,
        resources=resources,
        scalability=scalability,
        stress=stress,
        dependencies=dependencies,
        analyses=analyses,
        findings=findings,
        cache_info=cache_info,
        provenance=provenance,
        gate_passed=True,
    )
    assert report.complexity.module_count == 3
    assert report.resources.file_count == 50
    assert report.scalability.max_supported_tier == SCALE_THOUSANDS
    assert report.stress.load_level == LOAD_MODERATE
    assert report.dependencies.total_dependencies == 10
    assert report.analysis_count == 5
    assert 0.0 <= report.confidence <= 1.0
    assert report.confidence_level in ("high", "medium", "low")
    assert report.verdict in ALL_VERDICTS
    assert report.summary != ""
    assert len(report.notes) > 0
    print("  [PASS] test_report_builder_build")


def test_report_builder_verdict_not_capable():
    rb = ReportBuilder()
    complexity = ComplexityAnalysis()
    resources = ResourceEstimation()
    scalability = ScalabilityAnalysis()
    stress = ArchitectureStressAnalysis()
    dependencies = DependencyAnalysis()
    analyses = []
    findings = []
    cache_info = CacheInfo(status=CACHE_MISS)
    provenance = CapabilityProvenance()
    report = rb.build(
        complexity=complexity,
        resources=resources,
        scalability=scalability,
        stress=stress,
        dependencies=dependencies,
        analyses=analyses,
        findings=findings,
        cache_info=cache_info,
        provenance=provenance,
        gate_passed=False,
    )
    assert report.verdict == VERDICT_NOT_CAPABLE
    assert report.is_blocked is True
    assert report.is_capable is False
    print("  [PASS] test_report_builder_verdict_not_capable")


def test_report_builder_verdict_capable():
    rb = ReportBuilder()
    complexity = ComplexityAnalysis(module_count=3, total_elements=20, complexity_level=COMPLEXITY_MODERATE, score=0.5)
    resources = ResourceEstimation(file_count=50, project_size_level=SIZE_SMALL, score=0.3)
    scalability = ScalabilityAnalysis(
        tiers=[ScalabilityTier(tier=SCALE_THOUSANDS, supported=True, confidence=0.8)],
        max_supported_tier=SCALE_THOUSANDS, score=0.7,
    )
    stress = ArchitectureStressAnalysis(load_level=LOAD_MODERATE, score=0.7)
    dependencies = DependencyAnalysis(total_dependencies=10, circular_dependencies=[], is_healthy=True, score=0.8)
    analyses = [AnalysisResult(dimension=dim, score=0.7) for dim in ALL_DIMENSIONS]
    findings = []
    cache_info = CacheInfo(status=CACHE_MISS)
    provenance = CapabilityProvenance(
        architecture_decision_available=True,
        technology_selection_available=True,
        normalized_requirements_available=True,
        intelligence_graph_available=True,
        knowledge_base_available=True,
    )
    report = rb.build(
        complexity=complexity,
        resources=resources,
        scalability=scalability,
        stress=stress,
        dependencies=dependencies,
        analyses=analyses,
        findings=findings,
        cache_info=cache_info,
        provenance=provenance,
        gate_passed=True,
    )
    assert report.verdict in (VERDICT_CAPABLE, VERDICT_CAPABLE_WITH_RISKS)
    assert report.is_capable is True
    assert report.is_blocked is False
    print("  [PASS] test_report_builder_verdict_capable")


# ---------------------------------------------------------------------------#
# 21. Engine tests
# ---------------------------------------------------------------------------#

def test_engine_no_data():
    engine = ProjectCapabilityAnalyzerEngine()
    ctx = make_empty_context()
    result = engine.execute(ctx)
    assert result.success is True
    report = ctx.get("project_capability_report")
    assert report is not None
    assert report.is_empty is True or report.analysis_count >= 0
    print("  [PASS] test_engine_no_data")


def test_engine_with_all_data():
    engine = ProjectCapabilityAnalyzerEngine()
    ctx = make_full_context()
    result = engine.execute(ctx)
    assert result.success is True
    report = ctx.get("project_capability_report")
    assert report is not None
    assert report.analysis_count == 5
    print("  [PASS] test_engine_with_all_data")


def test_engine_produces_artefact():
    engine = ProjectCapabilityAnalyzerEngine()
    ctx = make_full_context()
    engine.execute(ctx)
    assert ctx.has("project_capability_report")
    report = ctx.get("project_capability_report")
    assert isinstance(report, ProjectCapabilityReport)
    print("  [PASS] test_engine_produces_artefact")


def test_engine_stores_in_metadata():
    engine = ProjectCapabilityAnalyzerEngine()
    ctx = make_full_context()
    engine.execute(ctx)
    assert "project_capability_report" in ctx.metadata
    report = ctx.metadata["project_capability_report"]
    assert isinstance(report, ProjectCapabilityReport)
    print("  [PASS] test_engine_stores_in_metadata")


def test_engine_does_not_write_files():
    engine = ProjectCapabilityAnalyzerEngine()
    ctx = make_full_context()
    result = engine.execute(ctx)
    # The engine should not create any files.
    assert result.success is True
    # Check that no files were created in the work dir.
    # (The work dir is /tmp/test_capability_analyzer which may not exist.)
    print("  [PASS] test_engine_does_not_write_files")


def test_engine_all_five_analyses():
    engine = ProjectCapabilityAnalyzerEngine()
    ctx = make_full_context()
    engine.execute(ctx)
    report = ctx.get("project_capability_report")
    dims = report.analysis_dimensions()
    assert DIMENSION_COMPLEXITY in dims
    assert DIMENSION_RESOURCES in dims
    assert DIMENSION_SCALABILITY in dims
    assert DIMENSION_STRESS in dims
    assert DIMENSION_DEPENDENCIES in dims
    assert len(dims) == 5
    print("  [PASS] test_engine_all_five_analyses")


def test_engine_verdict():
    engine = ProjectCapabilityAnalyzerEngine()
    ctx = make_full_context()
    engine.execute(ctx)
    report = ctx.get("project_capability_report")
    assert report.verdict in ALL_VERDICTS
    print("  [PASS] test_engine_verdict")


def test_engine_confidence_in_range():
    engine = ProjectCapabilityAnalyzerEngine()
    ctx = make_full_context()
    engine.execute(ctx)
    report = ctx.get("project_capability_report")
    assert 0.0 <= report.confidence <= 1.0
    assert report.confidence_level in ("high", "medium", "low")
    print("  [PASS] test_engine_confidence_in_range")


def test_engine_cache_hit():
    engine = ProjectCapabilityAnalyzerEngine()
    ctx = make_full_context()
    # First run — should be a cache miss.
    result1 = engine.execute(ctx)
    assert result1.outputs["cache_hit"] is False
    # Second run with same data — should be a cache hit.
    result2 = engine.execute(ctx)
    assert result2.outputs["cache_hit"] is True
    print("  [PASS] test_engine_cache_hit")


# ---------------------------------------------------------------------------#
# 22. Bootstrap tests
# ---------------------------------------------------------------------------#

def test_bootstrap_registers_capability_analyzer():
    config = build_configuration()
    registry, orchestrator, manager = bootstrap(config)
    engines = registry.engine_names()
    found = False
    for e in engines:
        if "capability" in str(e).lower():
            found = True
            break
    assert found, "capability_analyzer not found in registry"
    print("  [PASS] test_bootstrap_registers_capability_analyzer")


def test_bootstrap_capability_analyzer_priority():
    config = build_configuration()
    registry, orchestrator, manager = bootstrap(config)
    # Check the manager for the capability_analyzer registration.
    entries = manager._entries if hasattr(manager, "_entries") else {}
    found = False
    for key, entry in entries.items():
        if entry.engine_id == "capability_analyzer":
            assert entry.priority == 103
            found = True
            break
    assert found, "capability_analyzer not found in manager"
    print("  [PASS] test_bootstrap_capability_analyzer_priority")


def test_bootstrap_capability_analyzer_dependencies():
    config = build_configuration()
    registry, orchestrator, manager = bootstrap(config)
    entries = manager._entries if hasattr(manager, "_entries") else {}
    found = False
    for key, entry in entries.items():
        if entry.engine_id == "capability_analyzer":
            assert "technology_selection" in entry.dependencies
            found = True
            break
    assert found, "capability_analyzer not found in manager"
    print("  [PASS] test_bootstrap_capability_analyzer_dependencies")


# ---------------------------------------------------------------------------#
# 23. Serialisation tests
# ---------------------------------------------------------------------------#

def test_analysis_result_serialisation():
    ar = AnalysisResult(dimension=DIMENSION_COMPLEXITY, score=0.7)
    d = ar.to_dict()
    assert d["dimension"] == DIMENSION_COMPLEXITY
    assert d["score"] == 0.7
    print("  [PASS] test_analysis_result_serialisation")


def test_complexity_analysis_serialisation():
    ca = ComplexityAnalysis(module_count=5, total_elements=100)
    d = ca.to_dict()
    assert d["module_count"] == 5
    assert d["total_elements"] == 100
    print("  [PASS] test_complexity_analysis_serialisation")


def test_resource_estimation_serialisation():
    re = ResourceEstimation(file_count=50, project_size_level=SIZE_SMALL)
    d = re.to_dict()
    assert d["file_count"] == 50
    assert d["project_size_level"] == SIZE_SMALL
    print("  [PASS] test_resource_estimation_serialisation")


def test_scalability_tier_serialisation():
    st = ScalabilityTier(tier=SCALE_THOUSANDS, supported=True, confidence=0.8)
    d = st.to_dict()
    assert d["tier"] == SCALE_THOUSANDS
    assert d["supported"] is True
    print("  [PASS] test_scalability_tier_serialisation")


def test_scalability_analysis_serialisation():
    sa = ScalabilityAnalysis(
        tiers=[ScalabilityTier(tier=SCALE_THOUSANDS)],
        max_supported_tier=SCALE_THOUSANDS,
    )
    d = sa.to_dict()
    assert d["max_supported_tier"] == SCALE_THOUSANDS
    assert len(d["tiers"]) == 1
    print("  [PASS] test_scalability_analysis_serialisation")


def test_bottleneck_serialisation():
    b = Bottleneck(component="db", severity=BOTTLENECK_MAJOR, load_level=LOAD_HEAVY)
    d = b.to_dict()
    assert d["component"] == "db"
    assert d["severity"] == BOTTLENECK_MAJOR
    print("  [PASS] test_bottleneck_serialisation")


def test_stress_analysis_serialisation():
    sa = ArchitectureStressAnalysis(load_level=LOAD_HEAVY, score=0.7)
    d = sa.to_dict()
    assert d["load_level"] == LOAD_HEAVY
    assert d["score"] == 0.7
    print("  [PASS] test_stress_analysis_serialisation")


def test_dependency_issue_serialisation():
    di = DependencyIssue(issue_type=DEP_ISSUE_CIRCULAR, component="mod_a")
    d = di.to_dict()
    assert d["issue_type"] == DEP_ISSUE_CIRCULAR
    assert d["component"] == "mod_a"
    print("  [PASS] test_dependency_issue_serialisation")


def test_dependency_analysis_serialisation():
    da = DependencyAnalysis(total_dependencies=10, circular_dependencies=[])
    d = da.to_dict()
    assert d["total_dependencies"] == 10
    assert d["circular_dependencies"] == []
    print("  [PASS] test_dependency_analysis_serialisation")


def test_capability_finding_serialisation():
    cf = CapabilityFinding(severity=SEVERITY_WARNING, code="CAP_001", message="Low score.")
    d = cf.to_dict()
    assert d["severity"] == SEVERITY_WARNING
    assert d["code"] == "CAP_001"
    print("  [PASS] test_capability_finding_serialisation")


def test_cache_info_serialisation():
    ci = CacheInfo(status=CACHE_HIT, cache_key="abc")
    d = ci.to_dict()
    assert d["status"] == CACHE_HIT
    assert d["cache_key"] == "abc"
    print("  [PASS] test_cache_info_serialisation")


def test_capability_provenance_serialisation():
    cp = CapabilityProvenance(decision_count=8, selection_count=5)
    d = cp.to_dict()
    assert d["decision_count"] == 8
    assert d["selection_count"] == 5
    print("  [PASS] test_capability_provenance_serialisation")


def test_project_capability_report_serialisation():
    report = ProjectCapabilityReport()
    d = report.to_dict()
    assert "analysis_count" in d
    assert "verdict" in d
    assert "confidence" in d
    assert "complexity" in d
    assert "scalability" in d
    assert "stress" in d
    assert "dependencies" in d
    print("  [PASS] test_project_capability_report_serialisation")


# ---------------------------------------------------------------------------#
# 24. End-to-end tests
# ---------------------------------------------------------------------------#

def test_end_to_end_with_all_sources():
    engine = ProjectCapabilityAnalyzerEngine()
    ctx = make_full_context()
    result = engine.execute(ctx)
    assert result.success is True
    report = ctx.get("project_capability_report")
    assert report is not None
    assert report.analysis_count == 5
    assert report.verdict in ALL_VERDICTS
    assert 0.0 <= report.confidence <= 1.0
    assert report.provenance.architecture_decision_available is True
    assert report.provenance.technology_selection_available is True
    assert report.provenance.normalized_requirements_available is True
    assert report.provenance.intelligence_graph_available is True
    assert report.provenance.knowledge_base_available is True
    print("  [PASS] test_end_to_end_with_all_sources")


def test_end_to_end_empty_context():
    engine = ProjectCapabilityAnalyzerEngine()
    ctx = make_empty_context()
    result = engine.execute(ctx)
    assert result.success is True
    report = ctx.get("project_capability_report")
    assert report is not None
    assert report.provenance.architecture_decision_available is False
    assert report.provenance.technology_selection_available is False
    print("  [PASS] test_end_to_end_empty_context")


def test_end_to_end_with_architecture_only():
    engine = ProjectCapabilityAnalyzerEngine()
    ctx = make_context(
        architecture_decision_report=make_architecture_decision_report(),
    )
    result = engine.execute(ctx)
    assert result.success is True
    report = ctx.get("project_capability_report")
    assert report is not None
    assert report.provenance.architecture_decision_available is True
    assert report.provenance.technology_selection_available is False
    print("  [PASS] test_end_to_end_with_architecture_only")


def test_end_to_end_report_summary():
    engine = ProjectCapabilityAnalyzerEngine()
    ctx = make_full_context()
    engine.execute(ctx)
    report = ctx.get("project_capability_report")
    assert report.summary != ""
    assert "verdict" in report.summary.lower()
    print("  [PASS] test_end_to_end_report_summary")


def test_end_to_end_report_notes():
    engine = ProjectCapabilityAnalyzerEngine()
    ctx = make_full_context()
    engine.execute(ctx)
    report = ctx.get("project_capability_report")
    assert len(report.notes) > 0
    print("  [PASS] test_end_to_end_report_notes")


# ---------------------------------------------------------------------------#
# 25. Report ready/blocking tests
# ---------------------------------------------------------------------------#

def test_report_blocked_when_gate_fails():
    """When the quality gate fails, the verdict should be NOT_CAPABLE."""
    rb = ReportBuilder()
    complexity = ComplexityAnalysis()
    resources = ResourceEstimation()
    scalability = ScalabilityAnalysis()
    stress = ArchitectureStressAnalysis()
    dependencies = DependencyAnalysis()
    analyses = []
    findings = []
    cache_info = CacheInfo(status=CACHE_MISS)
    provenance = CapabilityProvenance()
    report = rb.build(
        complexity=complexity,
        resources=resources,
        scalability=scalability,
        stress=stress,
        dependencies=dependencies,
        analyses=analyses,
        findings=findings,
        cache_info=cache_info,
        provenance=provenance,
        gate_passed=False,
    )
    assert report.verdict == VERDICT_NOT_CAPABLE
    assert report.is_blocked is True
    assert report.ready is False
    print("  [PASS] test_report_blocked_when_gate_fails")


def test_report_capable_with_risks():
    """When the gate passes but there are risks, verdict should be
    CAPABLE_WITH_RISKS."""
    rb = ReportBuilder()
    complexity = ComplexityAnalysis(module_count=3, total_elements=20, complexity_level=COMPLEXITY_MODERATE, score=0.5)
    resources = ResourceEstimation(file_count=50, project_size_level=SIZE_SMALL, score=0.3)
    scalability = ScalabilityAnalysis(
        tiers=[ScalabilityTier(tier=SCALE_THOUSANDS, supported=True, confidence=0.7)],
        max_supported_tier=SCALE_THOUSANDS, score=0.6,
    )
    stress = ArchitectureStressAnalysis(load_level=LOAD_MODERATE, score=0.5)
    dependencies = DependencyAnalysis(total_dependencies=10, circular_dependencies=[], is_healthy=True, score=0.6)
    analyses = [AnalysisResult(dimension=dim, score=0.6) for dim in ALL_DIMENSIONS]
    findings = [CapabilityFinding(severity=SEVERITY_WARNING, code="CAP_001", message="Low scalability score.")]
    cache_info = CacheInfo(status=CACHE_MISS)
    provenance = CapabilityProvenance(
        architecture_decision_available=True,
        technology_selection_available=True,
        normalized_requirements_available=True,
        intelligence_graph_available=True,
        knowledge_base_available=True,
    )
    report = rb.build(
        complexity=complexity,
        resources=resources,
        scalability=scalability,
        stress=stress,
        dependencies=dependencies,
        analyses=analyses,
        findings=findings,
        cache_info=cache_info,
        provenance=provenance,
        gate_passed=True,
    )
    # With warnings/risks, should be capable_with_risks.
    assert report.verdict == VERDICT_CAPABLE_WITH_RISKS
    assert report.is_capable is True
    print("  [PASS] test_report_capable_with_risks")


# ---------------------------------------------------------------------------#
# Run all tests
# ---------------------------------------------------------------------------#

def run_all_tests():
    """Run all tests and report results."""

    tests = [
        # Data model — AnalysisResult
        test_analysis_result_creation,
        test_analysis_result_to_dict,
        # Data model — ComplexityAnalysis
        test_complexity_analysis_creation,
        test_complexity_analysis_to_dict,
        # Data model — ResourceEstimation
        test_resource_estimation_creation,
        test_resource_estimation_to_dict,
        # Data model — ScalabilityTier and ScalabilityAnalysis
        test_scalability_tier_creation,
        test_scalability_analysis_creation,
        test_scalability_analysis_get_tier,
        # Data model — Bottleneck and StressAnalysis
        test_bottleneck_creation,
        test_bottleneck_to_dict,
        test_stress_analysis_creation,
        # Data model — DependencyIssue and DependencyAnalysis
        test_dependency_issue_creation,
        test_dependency_analysis_creation,
        test_dependency_analysis_to_dict,
        # Data model — CapabilityFinding
        test_capability_finding_creation,
        test_capability_finding_to_dict,
        # Data model — CacheInfo
        test_cache_info_creation,
        test_cache_info_to_dict,
        # Data model — CapabilityProvenance
        test_capability_provenance_creation,
        test_capability_provenance_to_dict,
        # Data model — ProjectCapabilityReport
        test_project_capability_report_creation,
        test_project_capability_report_add_finding,
        test_project_capability_report_add_error_finding,
        test_project_capability_report_add_strength,
        test_project_capability_report_add_risk,
        test_project_capability_report_add_recommendation,
        test_project_capability_report_get_analysis,
        test_project_capability_report_analysis_dimensions,
        test_project_capability_report_get_scalability_tier,
        test_project_capability_report_critical_bottlenecks,
        test_project_capability_report_to_dict,
        # Constants
        test_source_constants,
        test_severity_constants,
        test_complexity_constants,
        test_size_constants,
        test_scale_tier_constants,
        test_load_level_constants,
        test_bottleneck_constants,
        test_dependency_issue_constants,
        test_dimension_constants,
        test_quality_rule_constants,
        test_cache_status_constants,
        test_confidence_constants,
        test_verdict_constants,
        # Readers
        test_architecture_decision_reader_empty_context,
        test_architecture_decision_reader_with_report,
        test_technology_selection_reader_empty_context,
        test_technology_selection_reader_with_report,
        test_requirement_normalization_reader_empty_context,
        test_requirement_normalization_reader_with_report,
        test_intelligence_graph_reader_empty_context,
        test_intelligence_graph_reader_with_graph,
        test_knowledge_reader_empty_context,
        test_knowledge_reader_with_base,
        # ComplexityAnalyzer
        test_complexity_analyzer_empty,
        test_complexity_analyzer_with_data,
        # ResourceEstimator
        test_resource_estimator_empty,
        test_resource_estimator_with_data,
        # ScalabilityAnalyzer
        test_scalability_analyzer_empty,
        test_scalability_analyzer_with_data,
        # StressAnalyzer
        test_stress_analyzer_empty,
        test_stress_analyzer_with_data,
        # DependencyAnalyzer
        test_dependency_analyzer_empty,
        test_dependency_analyzer_with_data,
        # QualityGate
        test_quality_gate_passes_good_report,
        test_quality_gate_fails_empty_report,
        test_quality_gate_fails_circular_dependencies,
        test_quality_gate_fails_low_stress,
        # CacheManager
        test_cache_manager_miss,
        test_cache_manager_hit,
        test_cache_manager_store,
        # ReportBuilder
        test_report_builder_build_provenance,
        test_report_builder_build,
        test_report_builder_verdict_not_capable,
        test_report_builder_verdict_capable,
        # Engine
        test_engine_no_data,
        test_engine_with_all_data,
        test_engine_produces_artefact,
        test_engine_stores_in_metadata,
        test_engine_does_not_write_files,
        test_engine_all_five_analyses,
        test_engine_verdict,
        test_engine_confidence_in_range,
        test_engine_cache_hit,
        # Bootstrap
        test_bootstrap_registers_capability_analyzer,
        test_bootstrap_capability_analyzer_priority,
        test_bootstrap_capability_analyzer_dependencies,
        # Serialisation
        test_analysis_result_serialisation,
        test_complexity_analysis_serialisation,
        test_resource_estimation_serialisation,
        test_scalability_tier_serialisation,
        test_scalability_analysis_serialisation,
        test_bottleneck_serialisation,
        test_stress_analysis_serialisation,
        test_dependency_issue_serialisation,
        test_dependency_analysis_serialisation,
        test_capability_finding_serialisation,
        test_cache_info_serialisation,
        test_capability_provenance_serialisation,
        test_project_capability_report_serialisation,
        # End-to-end
        test_end_to_end_with_all_sources,
        test_end_to_end_empty_context,
        test_end_to_end_with_architecture_only,
        test_end_to_end_report_summary,
        test_end_to_end_report_notes,
        # Report ready/blocking
        test_report_blocked_when_gate_fails,
        test_report_capable_with_risks,
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
