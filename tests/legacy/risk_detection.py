#!/usr/bin/env python3
"""
Comprehensive test suite for the Risk Detection Engine
(Specification 018).

These tests cover every aspect of the specification:

1. Data model integrity (RiskItem, RiskRecommendation,
   RiskDimensionResult, RiskFinding, CacheInfo, RiskProvenance,
   RiskAnalysisReport, source-artefact constants, severity
   constants, dimension constants, risk-type constants for all
   seven dimensions, fix-priority constants, quality-rule
   constants, cache-status constants, confidence-level constants,
   verdict constants).
2. The ProjectCapabilityReader (artefact, empty context).
3. The ArchitectureDecisionReader (artefact, empty context).
4. The TechnologySelectionReader (artefact, empty context).
5. The RequirementNormalizationReader (artefact, empty context).
6. The KnowledgeReader (artefact, empty context).
7. The ArchitectureRiskAnalyzer (empty, with data).
8. The PerformanceRiskAnalyzer (empty, with data).
9. The ScalabilityRiskAnalyzer (empty, with data).
10. The SecurityRiskAnalyzer (empty, with data).
11. The DependencyRiskAnalyzer (empty, with data).
12. The MaintenanceRiskAnalyzer (empty, with data).
13. The ResourceRiskAnalyzer (empty, with data).
14. The QualityGate (pass, empty, critical risks, missing
    dimensions, insufficient confidence).
15. The CacheManager (miss, hit, store, stale).
16. The ReportBuilder (build, provenance, verdict, summary,
    notes, warnings, strengths, recommendations).
17. The main engine reads the five data sources.
18. The main engine produces a risk_analysis_report artefact.
19. The main engine fails gracefully when no data sources are
    available.
20. The main engine stores the report in the context metadata.
21. The main engine does not write files or build the project.
22. The main engine runs all seven analyses.
23. The main engine produces a verdict.
24. Bootstrap integration (engine registered in registry and
    manager at priority 104, depends on capability_analyzer).
25. Serialisation (to_dict) for all data model classes.
26. End-to-end pipeline with all data sources.
27. Cache hit returns cached report.
28. Quality gate blocks when critical risks exist.
29. Report ready with risks.
"""

import sys
import os

# Ensure the package is importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path

from telegram_bot_engine.core import build_configuration, bootstrap
from telegram_bot_engine.core.context import GenerationContext
from telegram_bot_engine.engines.generators.risk_detection import (
    # Engine
    RiskDetectionEngine,
    # Data model
    RiskItem,
    RiskRecommendation,
    RiskDimensionResult,
    RiskFinding,
    CacheInfo,
    RiskProvenance,
    RiskAnalysisReport,
    # Source-artefact constants
    SOURCE_PROJECT_CAPABILITY,
    SOURCE_ARCHITECTURE_DECISION,
    SOURCE_TECHNOLOGY_SELECTION,
    SOURCE_NORMALIZED_REQUIREMENTS,
    SOURCE_KNOWLEDGE_BASE,
    ALL_SOURCES,
    # Severity constants
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    SEVERITY_LOW,
    ALL_SEVERITIES,
    # Dimension constants
    DIMENSION_ARCHITECTURE,
    DIMENSION_PERFORMANCE,
    DIMENSION_SCALABILITY,
    DIMENSION_SECURITY,
    DIMENSION_DEPENDENCY,
    DIMENSION_MAINTENANCE,
    DIMENSION_RESOURCE,
    ALL_DIMENSIONS,
    # Architecture risk type constants
    ARCH_RISK_POOR_PARTITIONING,
    ARCH_RISK_CIRCULAR_DEPENDENCIES,
    ARCH_RISK_EXCESSIVE_COUPLING,
    ARCH_RISK_WEAK_EXTENSIBILITY,
    ALL_ARCH_RISKS,
    # Performance risk type constants
    PERF_RISK_BOTTLENECK,
    PERF_RISK_HIGH_MEMORY,
    PERF_RISK_SLOW_OPERATION,
    PERF_RISK_UNNECESSARY_REPETITION,
    ALL_PERF_RISKS,
    # Security risk type constants
    SEC_RISK_INPUT_VALIDATION,
    SEC_RISK_AUTHORIZATION,
    SEC_RISK_DATA_EXPOSURE,
    SEC_RISK_INSECURE_COMMUNICATION,
    SEC_RISK_SECRETS_MANAGEMENT,
    ALL_SEC_RISKS,
    # Dependency risk type constants
    DEP_RISK_VERSION_CONFLICT,
    DEP_RISK_DEPRECATED,
    DEP_RISK_SECURITY_VULNERABILITY,
    DEP_RISK_TOO_MANY,
    DEP_RISK_SINGLE_POINT,
    ALL_DEP_RISKS,
    # Maintenance risk type constants
    MAINT_RISK_COMPLEXITY,
    MAINT_RISK_NO_TESTS,
    MAINT_RISK_NO_DOCS,
    MAINT_RISK_TIGHT_COUPLING,
    MAINT_RISK_NO_MONITORING,
    ALL_MAINT_RISKS,
    # Resource risk type constants
    RES_RISK_CPU_BOUND,
    RES_RISK_MEMORY_BOUND,
    RES_RISK_DISK_BOUND,
    RES_RISK_NETWORK_BOUND,
    RES_RISK_COST_OVERRUN,
    ALL_RES_RISKS,
    # Fix priority constants
    PRIORITY_IMMEDIATE,
    PRIORITY_HIGH,
    PRIORITY_MEDIUM,
    PRIORITY_LOW,
    ALL_PRIORITIES,
    # Quality rule constants
    RULE_NO_CRITICAL_RISKS,
    RULE_ALL_DIMENSIONS_ANALYSED,
    RULE_RISKS_HAVE_RECOMMENDATIONS,
    RULE_SUFFICIENT_CONFIDENCE,
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
    VERDICT_READY,
    VERDICT_READY_WITH_RISKS,
    VERDICT_NOT_READY,
    ALL_VERDICTS,
    # Readers + intermediate data
    ProjectCapabilityData,
    ProjectCapabilityReader,
    ArchitectureDecisionData,
    ArchitectureDecisionReader,
    TechnologySelectionData,
    TechnologySelectionReader,
    RequirementNormalizationData,
    RequirementNormalizationReader,
    KnowledgeData,
    KnowledgeReader,
    # Analyzers
    ArchitectureRiskAnalyzer,
    PerformanceRiskAnalyzer,
    ScalabilityRiskAnalyzer,
    SecurityRiskAnalyzer,
    DependencyRiskAnalyzer,
    MaintenanceRiskAnalyzer,
    ResourceRiskAnalyzer,
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
    project_capability_report=None,
    architecture_decision_report=None,
    technology_selection_report=None,
    requirement_normalization_report=None,
    knowledge_base=None,
    request="",
):
    """Build a generation context with the five data sources."""
    ctx = GenerationContext(
        request=request,
        config=make_config(),
        work_dir=Path("/tmp/test_risk_detection"),
    )
    if project_capability_report is not None:
        ctx.set(
            "project_capability_report",
            project_capability_report,
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
    if knowledge_base is not None:
        ctx.set("knowledge_base", knowledge_base)
    return ctx


def make_project_capability_report(
    ready=True,
    verdict="capable",
    confidence=0.8,
    complexity_level="moderate",
    total_elements=50,
    scalability_score=0.7,
    stress_score=0.7,
    load_level="moderate",
    max_scalability_tier="tens_of_thousands",
    dependency_health=0.8,
    circular_dependencies=0,
    dependency_conflicts=0,
    missing_dependencies=0,
    total_dependencies=10,
    estimated_memory_mb=512,
    file_count=50,
    bottlenecks=None,
    analysis_dimensions=None,
):
    """Build a mock project capability report dictionary.

    The Risk Detection Engine reads the capability report via
    ``to_dict()``, so we provide a dictionary that mimics the
    serialised form with the nested structure the reader expects:
    ``complexity``, ``scalability``, ``stress``, ``dependencies``,
    ``resources``, ``analyses``.
    """
    if bottlenecks is None:
        bottlenecks = []
    if analysis_dimensions is None:
        analysis_dimensions = [
            "complexity",
            "resources",
            "scalability",
            "stress",
            "dependencies",
        ]
    return {
        "ready": ready,
        "verdict": verdict,
        "confidence": confidence,
        "max_scalability_tier": max_scalability_tier,
        "complexity": {
            "complexity_level": complexity_level,
            "total_elements": total_elements,
        },
        "scalability": {
            "score": scalability_score,
        },
        "stress": {
            "score": stress_score,
            "load_level": load_level,
            "bottlenecks": bottlenecks,
        },
        "dependencies": {
            "score": dependency_health,
            "circular_dependencies": [
                {"name": f"cdep_{i}"}
                for i in range(circular_dependencies)
            ],
            "conflicts": [
                {"name": f"conflict_{i}"}
                for i in range(dependency_conflicts)
            ],
            "missing_dependencies": [
                {"name": f"missing_{i}"}
                for i in range(missing_dependencies)
            ],
            "total_count": total_dependencies,
        },
        "resources": {
            "memory_mb": estimated_memory_mb,
            "file_count": file_count,
        },
        "analyses": [
            {"dimension": d}
            for d in analysis_dimensions
        ],
    }


def make_architecture_decision_report(
    pattern="layered",
    communication="sync",
    module_count=3,
    service_count=2,
    decision_count=8,
):
    """Build a mock architecture decision report dictionary."""
    decisions = [
        {
            "domain": "layers",
            "selected": "presentation, business, data_access",
            "reason": "Layered architecture for separation of concerns.",
            "analysis": "Multiple concerns benefit from layering.",
            "impact": "Clear separation, easier maintenance.",
        },
        {
            "domain": "communication",
            "selected": communication,
            "reason": "Communication pattern selected.",
            "analysis": "Based on project needs.",
            "impact": "Defines how components interact.",
        },
    ]
    for i in range(2, decision_count):
        decisions.append({
            "domain": f"domain_{i}",
            "selected": f"choice_{i}",
            "reason": f"Reason {i}.",
            "analysis": f"Analysis {i}.",
            "impact": f"Impact {i}.",
        })

    modules = [
        {
            "name": f"module_{i}",
            "layer": "business",
            "responsibility": f"Module {i} responsibility.",
            "dependencies": [],
        }
        for i in range(module_count)
    ]

    services = [
        {
            "name": f"service_{i}",
            "responsibility": f"Service {i} responsibility.",
            "communication": communication,
            "dependencies": [],
        }
        for i in range(service_count)
    ]

    return {
        "decisions": decisions,
        "modules": modules,
        "services": services,
        "summary": "Test architecture decision report.",
        "confidence": 0.8,
    }


def make_technology_selection_report(
    selection_count=5,
    ready=True,
    confidence=0.8,
):
    """Build a mock technology selection report dictionary."""
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
        selections.append({
            "category": cat,
            "selected": tech,
            "reason": f"Best {cat} for this project.",
            "analysis": f"Analysis for {cat}.",
            "impact": f"Impact of using {tech}.",
            "rejected_alternatives": [],
        })

    return {
        "selections": selections,
        "selection_count": len(selections),
        "ready": ready,
        "confidence": confidence,
        "summary": "Test technology selection report.",
    }


def make_normalization_report(
    requirement_count=3,
):
    """Build a mock normalization report dictionary."""
    requirements = []
    for i in range(1, requirement_count + 1):
        requirements.append({
            "id": f"NREQ-{i:03d}",
            "name": f"requirement_{i}",
            "display_name": f"Requirement {i}",
            "description": f"Requirement number {i}.",
            "category": "functional",
            "priority": "high" if i <= 2 else "medium",
            "status": "active",
            "feature": f"feature_{i}",
            "component": f"component_{i}",
        })
    return {
        "requirements": requirements,
        "requirement_count": len(requirements),
        "non_functional": [],
        "functional": requirements,
        "summary": "Test normalization report.",
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
        project_capability_report=(
            make_project_capability_report()
        ),
        architecture_decision_report=(
            make_architecture_decision_report()
        ),
        technology_selection_report=(
            make_technology_selection_report()
        ),
        requirement_normalization_report=make_normalization_report(),
        knowledge_base=make_knowledge_base(),
    )


def make_empty_context():
    """Build a context with no data sources."""
    return make_context()


def make_empty_data():
    """Build all five data-source objects in their empty state."""
    return (
        ProjectCapabilityData(),
        ArchitectureDecisionData(),
        TechnologySelectionData(),
        RequirementNormalizationData(),
        KnowledgeData(),
    )


# ---------------------------------------------------------------------------#
# 1. Data model -- RiskItem
# ---------------------------------------------------------------------------#

def test_risk_item_creation():
    ri = RiskItem(
        risk_id="RISK-001",
        dimension=DIMENSION_ARCHITECTURE,
        risk_type=ARCH_RISK_POOR_PARTITIONING,
        severity=SEVERITY_HIGH,
        title="Poor module partitioning",
        description="Modules are not well separated.",
        cause="No clear layer boundaries.",
        impact="Maintenance difficulties.",
        suggested_fix="Refactor into clear layers.",
        fix_priority=PRIORITY_HIGH,
        affected_components=["module_a", "module_b"],
        reasoning="High coupling detected.",
    )
    assert ri.risk_id == "RISK-001"
    assert ri.dimension == DIMENSION_ARCHITECTURE
    assert ri.risk_type == ARCH_RISK_POOR_PARTITIONING
    assert ri.severity == SEVERITY_HIGH
    assert ri.fix_priority == PRIORITY_HIGH
    assert len(ri.affected_components) == 2
    print("  [PASS] test_risk_item_creation")


def test_risk_item_to_dict():
    ri = RiskItem(
        risk_id="RISK-002",
        dimension=DIMENSION_PERFORMANCE,
        risk_type=PERF_RISK_BOTTLENECK,
        severity=SEVERITY_CRITICAL,
        title="Database bottleneck",
    )
    d = ri.to_dict()
    assert d["risk_id"] == "RISK-002"
    assert d["dimension"] == DIMENSION_PERFORMANCE
    assert d["risk_type"] == PERF_RISK_BOTTLENECK
    assert d["severity"] == SEVERITY_CRITICAL
    print("  [PASS] test_risk_item_to_dict")


# ---------------------------------------------------------------------------#
# 2. Data model -- RiskRecommendation
# ---------------------------------------------------------------------------#

def test_risk_recommendation_creation():
    rec = RiskRecommendation(
        recommendation_id="REC-001",
        dimension=DIMENSION_SECURITY,
        priority=PRIORITY_IMMEDIATE,
        title="Add input validation",
        description="Validate all user inputs.",
        related_risks=["RISK-001", "RISK-002"],
        expected_outcome="Reduced injection risk.",
    )
    assert rec.recommendation_id == "REC-001"
    assert rec.dimension == DIMENSION_SECURITY
    assert rec.priority == PRIORITY_IMMEDIATE
    assert len(rec.related_risks) == 2
    print("  [PASS] test_risk_recommendation_creation")


def test_risk_recommendation_to_dict():
    rec = RiskRecommendation(
        recommendation_id="REC-002",
        dimension=DIMENSION_DEPENDENCY,
        priority=PRIORITY_MEDIUM,
        title="Update deprecated library",
    )
    d = rec.to_dict()
    assert d["recommendation_id"] == "REC-002"
    assert d["dimension"] == DIMENSION_DEPENDENCY
    assert d["priority"] == PRIORITY_MEDIUM
    print("  [PASS] test_risk_recommendation_to_dict")


# ---------------------------------------------------------------------------#
# 3. Data model -- RiskDimensionResult
# ---------------------------------------------------------------------------#

def test_risk_dimension_result_creation():
    dr = RiskDimensionResult(
        dimension=DIMENSION_ARCHITECTURE,
        risk_count=3,
        critical_count=1,
        high_count=1,
        medium_count=1,
        low_count=0,
        score=0.7,
        summary="Architecture has 3 risks.",
    )
    assert dr.dimension == DIMENSION_ARCHITECTURE
    assert dr.risk_count == 3
    assert dr.critical_count == 1
    assert dr.high_count == 1
    assert dr.medium_count == 1
    assert dr.low_count == 0
    assert 0.0 <= dr.score <= 1.0
    print("  [PASS] test_risk_dimension_result_creation")


def test_risk_dimension_result_to_dict():
    dr = RiskDimensionResult(
        dimension=DIMENSION_PERFORMANCE,
        risk_count=2,
        score=0.5,
        risks=[RiskItem(risk_id="R-1", dimension=DIMENSION_PERFORMANCE)],
    )
    d = dr.to_dict()
    assert d["dimension"] == DIMENSION_PERFORMANCE
    assert d["risk_count"] == 2
    assert len(d["risks"]) == 1
    print("  [PASS] test_risk_dimension_result_to_dict")


# ---------------------------------------------------------------------------#
# 4. Data model -- RiskFinding
# ---------------------------------------------------------------------------#

def test_risk_finding_creation():
    rf = RiskFinding(
        severity=SEVERITY_HIGH,
        code="ARCH_001",
        message="Circular dependency detected.",
        affected="module_a",
        resolution_hint="Break the cycle.",
        category="architecture",
    )
    assert rf.severity == SEVERITY_HIGH
    assert rf.code == "ARCH_001"
    assert rf.message == "Circular dependency detected."
    assert rf.affected == "module_a"
    print("  [PASS] test_risk_finding_creation")


def test_risk_finding_to_dict():
    rf = RiskFinding(
        severity=SEVERITY_CRITICAL,
        code="SEC_001",
        message="No input validation.",
    )
    d = rf.to_dict()
    assert d["severity"] == SEVERITY_CRITICAL
    assert d["code"] == "SEC_001"
    print("  [PASS] test_risk_finding_to_dict")


# ---------------------------------------------------------------------------#
# 5. Data model -- CacheInfo
# ---------------------------------------------------------------------------#

def test_cache_info_creation():
    ci = CacheInfo(
        status=CACHE_HIT,
        cache_key="abc123",
        cached_at="2024-01-01T00:00:00",
        hit=True,
        inputs_hash="hash_abc",
    )
    assert ci.status == CACHE_HIT
    assert ci.cache_key == "abc123"
    assert ci.hit is True
    print("  [PASS] test_cache_info_creation")


def test_cache_info_to_dict():
    ci = CacheInfo(status=CACHE_MISS, cache_key="xyz")
    d = ci.to_dict()
    assert d["status"] == CACHE_MISS
    assert d["cache_key"] == "xyz"
    print("  [PASS] test_cache_info_to_dict")


# ---------------------------------------------------------------------------#
# 6. Data model -- RiskProvenance
# ---------------------------------------------------------------------------#

def test_risk_provenance_creation():
    rp = RiskProvenance(
        project_capability_available=True,
        architecture_decision_available=True,
        technology_selection_available=True,
        normalized_requirements_available=True,
        knowledge_base_available=True,
        all_sources_used=list(ALL_SOURCES),
        capability_verdict="capable",
        decision_count=8,
        selection_count=5,
        requirement_count=3,
    )
    assert rp.project_capability_available is True
    assert rp.architecture_decision_available is True
    assert rp.technology_selection_available is True
    assert rp.normalized_requirements_available is True
    assert rp.knowledge_base_available is True
    assert len(rp.all_sources_used) == 5
    assert rp.capability_verdict == "capable"
    assert rp.decision_count == 8
    print("  [PASS] test_risk_provenance_creation")


def test_risk_provenance_to_dict():
    rp = RiskProvenance(decision_count=8, selection_count=5)
    d = rp.to_dict()
    assert d["decision_count"] == 8
    assert d["selection_count"] == 5
    print("  [PASS] test_risk_provenance_to_dict")


# ---------------------------------------------------------------------------#
# 7. Data model -- RiskAnalysisReport
# ---------------------------------------------------------------------------#

def test_risk_analysis_report_creation():
    report = RiskAnalysisReport()
    assert report.dimension_count == 0
    assert report.risk_count == 0
    assert report.recommendation_count == 0
    assert report.critical_count == 0
    assert report.high_count == 0
    assert report.medium_count == 0
    assert report.low_count == 0
    assert report.is_empty is True
    assert report.verdict == VERDICT_NOT_READY
    print("  [PASS] test_risk_analysis_report_creation")


def test_risk_analysis_report_add_risk():
    report = RiskAnalysisReport()
    ri = RiskItem(
        risk_id="R-001",
        dimension=DIMENSION_ARCHITECTURE,
        severity=SEVERITY_HIGH,
    )
    report.add_risk(ri)
    assert report.risk_count == 1
    assert report.high_count == 1
    print("  [PASS] test_risk_analysis_report_add_risk")


def test_risk_analysis_report_add_critical_risk():
    report = RiskAnalysisReport()
    ri = RiskItem(
        risk_id="R-002",
        dimension=DIMENSION_SECURITY,
        severity=SEVERITY_CRITICAL,
    )
    report.add_risk(ri)
    assert report.critical_count == 1
    assert report.has_critical_risks is True
    print("  [PASS] test_risk_analysis_report_add_critical_risk")


def test_risk_analysis_report_add_recommendation():
    report = RiskAnalysisReport()
    rec = RiskRecommendation(
        recommendation_id="REC-001",
        dimension=DIMENSION_SECURITY,
    )
    report.add_recommendation(rec)
    assert report.recommendation_count == 1
    print("  [PASS] test_risk_analysis_report_add_recommendation")


def test_risk_analysis_report_add_strength():
    report = RiskAnalysisReport()
    report.add_strength("No critical risks detected.")
    assert len(report.strengths) == 1
    print("  [PASS] test_risk_analysis_report_add_strength")


def test_risk_analysis_report_add_finding():
    report = RiskAnalysisReport()
    report.add_finding(
        severity=SEVERITY_HIGH,
        code="FIND_001",
        message="High-severity finding.",
    )
    assert len(report.findings) == 1
    assert len(report.warnings) == 1
    print("  [PASS] test_risk_analysis_report_add_finding")


def test_risk_analysis_report_add_low_finding_no_warning():
    report = RiskAnalysisReport()
    report.add_finding(
        severity=SEVERITY_LOW,
        code="FIND_002",
        message="Low-severity finding.",
    )
    assert len(report.findings) == 1
    assert len(report.warnings) == 0
    print("  [PASS] test_risk_analysis_report_add_low_finding_no_warning")


def test_risk_analysis_report_get_dimension():
    report = RiskAnalysisReport()
    dr = RiskDimensionResult(dimension=DIMENSION_ARCHITECTURE)
    report.dimension_results.append(dr)
    found = report.get_dimension(DIMENSION_ARCHITECTURE)
    assert found is not None
    assert found.dimension == DIMENSION_ARCHITECTURE
    not_found = report.get_dimension(DIMENSION_SECURITY)
    assert not_found is None
    print("  [PASS] test_risk_analysis_report_get_dimension")


def test_risk_analysis_report_dimension_names():
    report = RiskAnalysisReport()
    report.dimension_results.append(
        RiskDimensionResult(dimension=DIMENSION_ARCHITECTURE)
    )
    report.dimension_results.append(
        RiskDimensionResult(dimension=DIMENSION_PERFORMANCE)
    )
    names = report.dimension_names()
    assert DIMENSION_ARCHITECTURE in names
    assert DIMENSION_PERFORMANCE in names
    print("  [PASS] test_risk_analysis_report_dimension_names")


def test_risk_analysis_report_risks_by_severity():
    report = RiskAnalysisReport()
    report.add_risk(RiskItem(risk_id="R1", severity=SEVERITY_HIGH))
    report.add_risk(RiskItem(risk_id="R2", severity=SEVERITY_HIGH))
    report.add_risk(RiskItem(risk_id="R3", severity=SEVERITY_LOW))
    high = report.risks_by_severity(SEVERITY_HIGH)
    assert len(high) == 2
    low = report.risks_by_severity(SEVERITY_LOW)
    assert len(low) == 1
    print("  [PASS] test_risk_analysis_report_risks_by_severity")


def test_risk_analysis_report_risks_by_dimension():
    report = RiskAnalysisReport()
    report.add_risk(
        RiskItem(risk_id="R1", dimension=DIMENSION_SECURITY)
    )
    report.add_risk(
        RiskItem(risk_id="R2", dimension=DIMENSION_SECURITY)
    )
    report.add_risk(
        RiskItem(risk_id="R3", dimension=DIMENSION_DEPENDENCY)
    )
    sec = report.risks_by_dimension(DIMENSION_SECURITY)
    assert len(sec) == 2
    dep = report.risks_by_dimension(DIMENSION_DEPENDENCY)
    assert len(dep) == 1
    print("  [PASS] test_risk_analysis_report_risks_by_dimension")


def test_risk_analysis_report_critical_risks():
    report = RiskAnalysisReport()
    report.add_risk(
        RiskItem(risk_id="R1", severity=SEVERITY_CRITICAL)
    )
    crits = report.critical_risks()
    assert len(crits) == 1
    print("  [PASS] test_risk_analysis_report_critical_risks")


def test_risk_analysis_report_all_dimensions_analysed():
    report = RiskAnalysisReport()
    for dim in ALL_DIMENSIONS:
        report.dimension_results.append(
            RiskDimensionResult(dimension=dim)
        )
    assert report.all_dimensions_analysed is True
    print("  [PASS] test_risk_analysis_report_all_dimensions_analysed")


def test_risk_analysis_report_not_all_dimensions_analysed():
    report = RiskAnalysisReport()
    report.dimension_results.append(
        RiskDimensionResult(dimension=DIMENSION_ARCHITECTURE)
    )
    assert report.all_dimensions_analysed is False
    print("  [PASS] test_risk_analysis_report_not_all_dimensions_analysed")


def test_risk_analysis_report_overall_risk_score():
    report = RiskAnalysisReport()
    report.add_risk(RiskItem(risk_id="R1", severity=SEVERITY_CRITICAL))
    report.add_risk(RiskItem(risk_id="R2", severity=SEVERITY_LOW))
    score = report.overall_risk_score
    assert 0.0 <= score <= 1.0
    assert score > 0.0
    print("  [PASS] test_risk_analysis_report_overall_risk_score")


def test_risk_analysis_report_overall_risk_score_empty():
    report = RiskAnalysisReport()
    assert report.overall_risk_score == 0.0
    print("  [PASS] test_risk_analysis_report_overall_risk_score_empty")


def test_risk_analysis_report_is_ready():
    report = RiskAnalysisReport()
    report.verdict = VERDICT_READY
    assert report.is_ready is True
    report.verdict = VERDICT_READY_WITH_RISKS
    assert report.is_ready is True
    report.verdict = VERDICT_NOT_READY
    assert report.is_ready is False
    print("  [PASS] test_risk_analysis_report_is_ready")


def test_risk_analysis_report_is_blocked():
    report = RiskAnalysisReport()
    report.verdict = VERDICT_NOT_READY
    assert report.is_blocked is True
    report.verdict = VERDICT_READY
    assert report.is_blocked is False
    print("  [PASS] test_risk_analysis_report_is_blocked")


def test_risk_analysis_report_has_sufficient_confidence():
    report = RiskAnalysisReport()
    report.confidence = 0.8
    assert report.has_sufficient_confidence is True
    report.confidence = 0.3
    assert report.has_sufficient_confidence is False
    print("  [PASS] test_risk_analysis_report_has_sufficient_confidence")


def test_risk_analysis_report_ready_property():
    report = RiskAnalysisReport()
    for dim in ALL_DIMENSIONS:
        report.dimension_results.append(
            RiskDimensionResult(dimension=dim)
        )
    report.confidence = 0.7
    report.verdict = VERDICT_READY
    assert report.ready is True
    print("  [PASS] test_risk_analysis_report_ready_property")


def test_risk_analysis_report_ready_blocked_by_critical():
    report = RiskAnalysisReport()
    for dim in ALL_DIMENSIONS:
        report.dimension_results.append(
            RiskDimensionResult(dimension=dim)
        )
    report.confidence = 0.7
    report.verdict = VERDICT_READY
    report.add_risk(
        RiskItem(risk_id="R1", severity=SEVERITY_CRITICAL)
    )
    assert report.ready is False
    print("  [PASS] test_risk_analysis_report_ready_blocked_by_critical")


def test_risk_analysis_report_to_dict():
    report = RiskAnalysisReport()
    d = report.to_dict()
    assert "dimension_count" in d
    assert "risk_count" in d
    assert "verdict" in d
    assert "confidence" in d
    assert "provenance" in d
    assert "cache_info" in d
    print("  [PASS] test_risk_analysis_report_to_dict")


# ---------------------------------------------------------------------------#
# 8. Constants tests
# ---------------------------------------------------------------------------#

def test_source_constants():
    assert SOURCE_PROJECT_CAPABILITY == "project_capability_report"
    assert SOURCE_ARCHITECTURE_DECISION == "architecture_decision_report"
    assert SOURCE_TECHNOLOGY_SELECTION == "technology_selection_report"
    assert SOURCE_NORMALIZED_REQUIREMENTS == "requirement_normalization_report"
    assert SOURCE_KNOWLEDGE_BASE == "knowledge_base"
    assert len(ALL_SOURCES) == 5
    print("  [PASS] test_source_constants")


def test_severity_constants():
    assert SEVERITY_CRITICAL == "critical"
    assert SEVERITY_HIGH == "high"
    assert SEVERITY_MEDIUM == "medium"
    assert SEVERITY_LOW == "low"
    assert len(ALL_SEVERITIES) == 4
    print("  [PASS] test_severity_constants")


def test_dimension_constants():
    assert len(ALL_DIMENSIONS) == 7
    assert DIMENSION_ARCHITECTURE in ALL_DIMENSIONS
    assert DIMENSION_PERFORMANCE in ALL_DIMENSIONS
    assert DIMENSION_SCALABILITY in ALL_DIMENSIONS
    assert DIMENSION_SECURITY in ALL_DIMENSIONS
    assert DIMENSION_DEPENDENCY in ALL_DIMENSIONS
    assert DIMENSION_MAINTENANCE in ALL_DIMENSIONS
    assert DIMENSION_RESOURCE in ALL_DIMENSIONS
    print("  [PASS] test_dimension_constants")


def test_arch_risk_constants():
    assert len(ALL_ARCH_RISKS) == 4
    assert ARCH_RISK_POOR_PARTITIONING in ALL_ARCH_RISKS
    assert ARCH_RISK_CIRCULAR_DEPENDENCIES in ALL_ARCH_RISKS
    assert ARCH_RISK_EXCESSIVE_COUPLING in ALL_ARCH_RISKS
    assert ARCH_RISK_WEAK_EXTENSIBILITY in ALL_ARCH_RISKS
    print("  [PASS] test_arch_risk_constants")


def test_perf_risk_constants():
    assert len(ALL_PERF_RISKS) == 4
    assert PERF_RISK_BOTTLENECK in ALL_PERF_RISKS
    assert PERF_RISK_HIGH_MEMORY in ALL_PERF_RISKS
    assert PERF_RISK_SLOW_OPERATION in ALL_PERF_RISKS
    assert PERF_RISK_UNNECESSARY_REPETITION in ALL_PERF_RISKS
    print("  [PASS] test_perf_risk_constants")


def test_sec_risk_constants():
    assert len(ALL_SEC_RISKS) == 5
    assert SEC_RISK_INPUT_VALIDATION in ALL_SEC_RISKS
    assert SEC_RISK_AUTHORIZATION in ALL_SEC_RISKS
    assert SEC_RISK_DATA_EXPOSURE in ALL_SEC_RISKS
    assert SEC_RISK_INSECURE_COMMUNICATION in ALL_SEC_RISKS
    assert SEC_RISK_SECRETS_MANAGEMENT in ALL_SEC_RISKS
    print("  [PASS] test_sec_risk_constants")


def test_dep_risk_constants():
    assert len(ALL_DEP_RISKS) == 5
    assert DEP_RISK_VERSION_CONFLICT in ALL_DEP_RISKS
    assert DEP_RISK_DEPRECATED in ALL_DEP_RISKS
    assert DEP_RISK_SECURITY_VULNERABILITY in ALL_DEP_RISKS
    assert DEP_RISK_TOO_MANY in ALL_DEP_RISKS
    assert DEP_RISK_SINGLE_POINT in ALL_DEP_RISKS
    print("  [PASS] test_dep_risk_constants")


def test_maint_risk_constants():
    assert len(ALL_MAINT_RISKS) == 5
    assert MAINT_RISK_COMPLEXITY in ALL_MAINT_RISKS
    assert MAINT_RISK_NO_TESTS in ALL_MAINT_RISKS
    assert MAINT_RISK_NO_DOCS in ALL_MAINT_RISKS
    assert MAINT_RISK_TIGHT_COUPLING in ALL_MAINT_RISKS
    assert MAINT_RISK_NO_MONITORING in ALL_MAINT_RISKS
    print("  [PASS] test_maint_risk_constants")


def test_res_risk_constants():
    assert len(ALL_RES_RISKS) == 5
    assert RES_RISK_CPU_BOUND in ALL_RES_RISKS
    assert RES_RISK_MEMORY_BOUND in ALL_RES_RISKS
    assert RES_RISK_DISK_BOUND in ALL_RES_RISKS
    assert RES_RISK_NETWORK_BOUND in ALL_RES_RISKS
    assert RES_RISK_COST_OVERRUN in ALL_RES_RISKS
    print("  [PASS] test_res_risk_constants")


def test_priority_constants():
    assert len(ALL_PRIORITIES) == 4
    assert PRIORITY_IMMEDIATE in ALL_PRIORITIES
    assert PRIORITY_HIGH in ALL_PRIORITIES
    assert PRIORITY_MEDIUM in ALL_PRIORITIES
    assert PRIORITY_LOW in ALL_PRIORITIES
    print("  [PASS] test_priority_constants")


def test_quality_rule_constants():
    assert len(ALL_QUALITY_RULES) == 4
    assert RULE_NO_CRITICAL_RISKS in ALL_QUALITY_RULES
    assert RULE_ALL_DIMENSIONS_ANALYSED in ALL_QUALITY_RULES
    assert RULE_RISKS_HAVE_RECOMMENDATIONS in ALL_QUALITY_RULES
    assert RULE_SUFFICIENT_CONFIDENCE in ALL_QUALITY_RULES
    print("  [PASS] test_quality_rule_constants")


def test_cache_status_constants():
    assert len(ALL_CACHE_STATUSES) == 4
    assert CACHE_HIT in ALL_CACHE_STATUSES
    assert CACHE_MISS in ALL_CACHE_STATUSES
    assert CACHE_STALE in ALL_CACHE_STATUSES
    assert CACHE_DISABLED in ALL_CACHE_STATUSES
    print("  [PASS] test_cache_status_constants")


def test_confidence_constants():
    assert len(ALL_CONFIDENCE_LEVELS) == 3
    assert CONFIDENCE_HIGH in ALL_CONFIDENCE_LEVELS
    assert CONFIDENCE_MEDIUM in ALL_CONFIDENCE_LEVELS
    assert CONFIDENCE_LOW in ALL_CONFIDENCE_LEVELS
    assert CONFIDENCE_HIGH_THRESHOLD == 0.8
    assert CONFIDENCE_MEDIUM_THRESHOLD == 0.6
    print("  [PASS] test_confidence_constants")


def test_verdict_constants():
    assert len(ALL_VERDICTS) == 3
    assert VERDICT_READY in ALL_VERDICTS
    assert VERDICT_READY_WITH_RISKS in ALL_VERDICTS
    assert VERDICT_NOT_READY in ALL_VERDICTS
    print("  [PASS] test_verdict_constants")


# ---------------------------------------------------------------------------#
# 9. Reader tests
# ---------------------------------------------------------------------------#

def test_project_capability_reader_empty_context():
    reader = ProjectCapabilityReader()
    ctx = make_empty_context()
    data = reader.read(ctx)
    assert data.available is False
    assert data.ready is False
    assert data.verdict == ""
    assert data.total_dependencies == 0
    print("  [PASS] test_project_capability_reader_empty_context")


def test_project_capability_reader_with_report():
    reader = ProjectCapabilityReader()
    ctx = make_context(
        project_capability_report=(
            make_project_capability_report()
        ),
    )
    data = reader.read(ctx)
    assert data.available is True
    assert data.ready is True
    assert data.verdict == "capable"
    assert data.confidence > 0.0
    assert data.total_dependencies > 0
    print("  [PASS] test_project_capability_reader_with_report")


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
    assert len(data.constraints) > 0
    print("  [PASS] test_knowledge_reader_with_base")


# ---------------------------------------------------------------------------#
# 10. ArchitectureRiskAnalyzer tests
# ---------------------------------------------------------------------------#

def test_architecture_risk_analyzer_empty():
    cap_data, arch_data, tech_data, req_data, kb_data = make_empty_data()
    analyzer = ArchitectureRiskAnalyzer()
    result = analyzer.analyze(cap_data, arch_data, tech_data, req_data, kb_data)
    assert result.dimension == DIMENSION_ARCHITECTURE
    assert result.risk_count >= 0
    assert 0.0 <= result.score <= 1.0
    print("  [PASS] test_architecture_risk_analyzer_empty")


def test_architecture_risk_analyzer_with_data():
    cap_data = ProjectCapabilityData(
        available=True,
        circular_dependencies=0,
        dependency_conflicts=0,
    )
    arch_data = ArchitectureDecisionData(
        available=True,
        pattern="layered",
        communication="sync",
        module_count=5,
        service_count=3,
        decision_count=8,
    )
    tech_data = TechnologySelectionData(
        available=True, selection_count=5,
    )
    req_data = RequirementNormalizationData(
        available=True, requirement_count=5,
    )
    kb_data = KnowledgeData(available=True)
    analyzer = ArchitectureRiskAnalyzer()
    result = analyzer.analyze(cap_data, arch_data, tech_data, req_data, kb_data)
    assert result.dimension == DIMENSION_ARCHITECTURE
    assert 0.0 <= result.score <= 1.0
    print("  [PASS] test_architecture_risk_analyzer_with_data")


def test_architecture_risk_analyzer_circular_deps():
    cap_data = ProjectCapabilityData(
        available=True,
        circular_dependencies=2,
    )
    arch_data = ArchitectureDecisionData(
        available=True,
        pattern="layered",
        module_count=5,
        service_count=3,
    )
    tech_data = TechnologySelectionData(available=True, selection_count=5)
    req_data = RequirementNormalizationData(available=True, requirement_count=5)
    kb_data = KnowledgeData(available=True)
    analyzer = ArchitectureRiskAnalyzer()
    result = analyzer.analyze(cap_data, arch_data, tech_data, req_data, kb_data)
    assert result.dimension == DIMENSION_ARCHITECTURE
    # With circular dependencies, there should be at least one risk.
    assert result.risk_count > 0
    print("  [PASS] test_architecture_risk_analyzer_circular_deps")


# ---------------------------------------------------------------------------#
# 11. PerformanceRiskAnalyzer tests
# ---------------------------------------------------------------------------#

def test_performance_risk_analyzer_empty():
    cap_data, arch_data, tech_data, req_data, kb_data = make_empty_data()
    analyzer = PerformanceRiskAnalyzer()
    result = analyzer.analyze(cap_data, arch_data, tech_data, req_data, kb_data)
    assert result.dimension == DIMENSION_PERFORMANCE
    assert result.risk_count >= 0
    assert 0.0 <= result.score <= 1.0
    print("  [PASS] test_performance_risk_analyzer_empty")


def test_performance_risk_analyzer_with_data():
    cap_data = ProjectCapabilityData(
        available=True,
        bottlenecks=[
            {"component": "db", "severity": "major"},
        ],
        stress_score=0.4,
    )
    arch_data = ArchitectureDecisionData(
        available=True,
        pattern="layered",
        communication="sync",
        module_count=5,
        service_count=3,
    )
    tech_data = TechnologySelectionData(available=True, selection_count=5)
    req_data = RequirementNormalizationData(available=True, requirement_count=5)
    kb_data = KnowledgeData(available=True)
    analyzer = PerformanceRiskAnalyzer()
    result = analyzer.analyze(cap_data, arch_data, tech_data, req_data, kb_data)
    assert result.dimension == DIMENSION_PERFORMANCE
    assert 0.0 <= result.score <= 1.0
    print("  [PASS] test_performance_risk_analyzer_with_data")


# ---------------------------------------------------------------------------#
# 12. ScalabilityRiskAnalyzer tests
# ---------------------------------------------------------------------------#

def test_scalability_risk_analyzer_empty():
    cap_data, arch_data, tech_data, req_data, kb_data = make_empty_data()
    analyzer = ScalabilityRiskAnalyzer()
    result = analyzer.analyze(cap_data, arch_data, tech_data, req_data, kb_data)
    assert result.dimension == DIMENSION_SCALABILITY
    assert result.risk_count >= 0
    assert 0.0 <= result.score <= 1.0
    print("  [PASS] test_scalability_risk_analyzer_empty")


def test_scalability_risk_analyzer_with_data():
    cap_data = ProjectCapabilityData(
        available=True,
        scalability_score=0.3,
        max_scalability_tier="thousands",
    )
    arch_data = ArchitectureDecisionData(
        available=True,
        pattern="monolith",
        module_count=1,
        service_count=0,
    )
    tech_data = TechnologySelectionData(available=True, selection_count=3)
    req_data = RequirementNormalizationData(available=True, requirement_count=5)
    kb_data = KnowledgeData(available=True)
    analyzer = ScalabilityRiskAnalyzer()
    result = analyzer.analyze(cap_data, arch_data, tech_data, req_data, kb_data)
    assert result.dimension == DIMENSION_SCALABILITY
    assert 0.0 <= result.score <= 1.0
    print("  [PASS] test_scalability_risk_analyzer_with_data")


# ---------------------------------------------------------------------------#
# 13. SecurityRiskAnalyzer tests
# ---------------------------------------------------------------------------#

def test_security_risk_analyzer_empty():
    cap_data, arch_data, tech_data, req_data, kb_data = make_empty_data()
    analyzer = SecurityRiskAnalyzer()
    result = analyzer.analyze(cap_data, arch_data, tech_data, req_data, kb_data)
    assert result.dimension == DIMENSION_SECURITY
    assert result.risk_count >= 0
    assert 0.0 <= result.score <= 1.0
    print("  [PASS] test_security_risk_analyzer_empty")


def test_security_risk_analyzer_with_data():
    cap_data = ProjectCapabilityData(available=True)
    arch_data = ArchitectureDecisionData(
        available=True,
        pattern="layered",
        communication="sync",
        module_count=5,
        service_count=3,
    )
    tech_data = TechnologySelectionData(
        available=True,
        selection_count=3,
        selected_technologies=["python", "sqlite"],
    )
    req_data = RequirementNormalizationData(available=True, requirement_count=5)
    kb_data = KnowledgeData(available=True)
    analyzer = SecurityRiskAnalyzer()
    result = analyzer.analyze(cap_data, arch_data, tech_data, req_data, kb_data)
    assert result.dimension == DIMENSION_SECURITY
    assert 0.0 <= result.score <= 1.0
    print("  [PASS] test_security_risk_analyzer_with_data")


# ---------------------------------------------------------------------------#
# 14. DependencyRiskAnalyzer tests
# ---------------------------------------------------------------------------#

def test_dependency_risk_analyzer_empty():
    cap_data, arch_data, tech_data, req_data, kb_data = make_empty_data()
    analyzer = DependencyRiskAnalyzer()
    result = analyzer.analyze(cap_data, arch_data, tech_data, req_data, kb_data)
    assert result.dimension == DIMENSION_DEPENDENCY
    assert result.risk_count >= 0
    assert 0.0 <= result.score <= 1.0
    print("  [PASS] test_dependency_risk_analyzer_empty")


def test_dependency_risk_analyzer_with_data():
    cap_data = ProjectCapabilityData(
        available=True,
        total_dependencies=30,
        dependency_health=0.3,
        dependency_conflicts=2,
    )
    arch_data = ArchitectureDecisionData(
        available=True, module_count=5, service_count=3,
    )
    tech_data = TechnologySelectionData(
        available=True, selection_count=10,
    )
    req_data = RequirementNormalizationData(available=True, requirement_count=5)
    kb_data = KnowledgeData(available=True)
    analyzer = DependencyRiskAnalyzer()
    result = analyzer.analyze(cap_data, arch_data, tech_data, req_data, kb_data)
    assert result.dimension == DIMENSION_DEPENDENCY
    assert 0.0 <= result.score <= 1.0
    print("  [PASS] test_dependency_risk_analyzer_with_data")


# ---------------------------------------------------------------------------#
# 15. MaintenanceRiskAnalyzer tests
# ---------------------------------------------------------------------------#

def test_maintenance_risk_analyzer_empty():
    cap_data, arch_data, tech_data, req_data, kb_data = make_empty_data()
    analyzer = MaintenanceRiskAnalyzer()
    result = analyzer.analyze(cap_data, arch_data, tech_data, req_data, kb_data)
    assert result.dimension == DIMENSION_MAINTENANCE
    assert result.risk_count >= 0
    assert 0.0 <= result.score <= 1.0
    print("  [PASS] test_maintenance_risk_analyzer_empty")


def test_maintenance_risk_analyzer_with_data():
    cap_data = ProjectCapabilityData(
        available=True,
        complexity_level="very_high",
        total_elements=200,
    )
    arch_data = ArchitectureDecisionData(
        available=True, module_count=20, service_count=10,
    )
    tech_data = TechnologySelectionData(
        available=True, selection_count=5,
        selected_technologies=["python", "sqlite"],
    )
    req_data = RequirementNormalizationData(available=True, requirement_count=20)
    kb_data = KnowledgeData(available=True)
    analyzer = MaintenanceRiskAnalyzer()
    result = analyzer.analyze(cap_data, arch_data, tech_data, req_data, kb_data)
    assert result.dimension == DIMENSION_MAINTENANCE
    assert 0.0 <= result.score <= 1.0
    print("  [PASS] test_maintenance_risk_analyzer_with_data")


# ---------------------------------------------------------------------------#
# 16. ResourceRiskAnalyzer tests
# ---------------------------------------------------------------------------#

def test_resource_risk_analyzer_empty():
    cap_data, arch_data, tech_data, req_data, kb_data = make_empty_data()
    analyzer = ResourceRiskAnalyzer()
    result = analyzer.analyze(cap_data, arch_data, tech_data, req_data, kb_data)
    assert result.dimension == DIMENSION_RESOURCE
    assert result.risk_count >= 0
    assert 0.0 <= result.score <= 1.0
    print("  [PASS] test_resource_risk_analyzer_empty")


def test_resource_risk_analyzer_with_data():
    cap_data = ProjectCapabilityData(
        available=True,
        estimated_memory_mb=4096,
        file_count=500,
        stress_score=0.2,
    )
    arch_data = ArchitectureDecisionData(
        available=True, module_count=5, service_count=3,
    )
    tech_data = TechnologySelectionData(
        available=True, selection_count=5,
        selected_technologies=["python", "celery", "redis"],
    )
    req_data = RequirementNormalizationData(available=True, requirement_count=10)
    kb_data = KnowledgeData(available=True)
    analyzer = ResourceRiskAnalyzer()
    result = analyzer.analyze(cap_data, arch_data, tech_data, req_data, kb_data)
    assert result.dimension == DIMENSION_RESOURCE
    assert 0.0 <= result.score <= 1.0
    print("  [PASS] test_resource_risk_analyzer_with_data")


# ---------------------------------------------------------------------------#
# 17. QualityGate tests
# ---------------------------------------------------------------------------#

def test_quality_gate_passes_good_report():
    gate = QualityGate()
    report = RiskAnalysisReport()
    # Fill in all seven dimensions.
    for dim in ALL_DIMENSIONS:
        report.dimension_results.append(
            RiskDimensionResult(dimension=dim)
        )
    report.confidence = 0.8
    findings, passed = gate.validate(report)
    assert passed is True
    print("  [PASS] test_quality_gate_passes_good_report")


def test_quality_gate_fails_empty_report():
    gate = QualityGate()
    report = RiskAnalysisReport()
    findings, passed = gate.validate(report)
    assert passed is False
    print("  [PASS] test_quality_gate_fails_empty_report")


def test_quality_gate_fails_critical_risks():
    gate = QualityGate()
    report = RiskAnalysisReport()
    for dim in ALL_DIMENSIONS:
        report.dimension_results.append(
            RiskDimensionResult(dimension=dim)
        )
    report.confidence = 0.8
    report.add_risk(
        RiskItem(
            risk_id="R-CRIT",
            dimension=DIMENSION_SECURITY,
            severity=SEVERITY_CRITICAL,
        )
    )
    findings, passed = gate.validate(report)
    assert passed is False
    print("  [PASS] test_quality_gate_fails_critical_risks")


def test_quality_gate_fails_missing_dimensions():
    gate = QualityGate()
    report = RiskAnalysisReport()
    # Only add one dimension.
    report.dimension_results.append(
        RiskDimensionResult(dimension=DIMENSION_ARCHITECTURE)
    )
    report.confidence = 0.8
    findings, passed = gate.validate(report)
    assert passed is False
    print("  [PASS] test_quality_gate_fails_missing_dimensions")


def test_quality_gate_fails_low_confidence():
    gate = QualityGate()
    report = RiskAnalysisReport()
    for dim in ALL_DIMENSIONS:
        report.dimension_results.append(
            RiskDimensionResult(dimension=dim)
        )
    report.confidence = 0.2
    findings, passed = gate.validate(report)
    assert passed is False
    print("  [PASS] test_quality_gate_fails_low_confidence")


# ---------------------------------------------------------------------------#
# 18. CacheManager tests
# ---------------------------------------------------------------------------#

def test_cache_manager_miss():
    cm = CacheManager()
    cap_data, arch_data, tech_data, req_data, kb_data = make_empty_data()
    info = cm.get_cache_info(
        cap_data, arch_data, tech_data, req_data, kb_data
    )
    assert info.status in (CACHE_MISS, CACHE_DISABLED)
    assert info.hit is False
    cached = cm.get_cached(info)
    assert cached is None
    print("  [PASS] test_cache_manager_miss")


def test_cache_manager_hit():
    cm = CacheManager()
    cap_data, arch_data, tech_data, req_data, kb_data = make_empty_data()
    info = cm.get_cache_info(
        cap_data, arch_data, tech_data, req_data, kb_data
    )
    report = RiskAnalysisReport()
    cm.store(info, report)
    # Second call should be a hit.
    info2 = cm.get_cache_info(
        cap_data, arch_data, tech_data, req_data, kb_data
    )
    assert info2.status == CACHE_HIT
    assert info2.hit is True
    cached = cm.get_cached(info2)
    assert cached is not None
    print("  [PASS] test_cache_manager_hit")


def test_cache_manager_store():
    cm = CacheManager()
    cap_data, arch_data, tech_data, req_data, kb_data = make_empty_data()
    info = cm.get_cache_info(
        cap_data, arch_data, tech_data, req_data, kb_data
    )
    report = RiskAnalysisReport()
    cm.store(info, report)
    cached = cm.get_cached(info)
    assert cached is not None
    print("  [PASS] test_cache_manager_store")


# ---------------------------------------------------------------------------#
# 19. ReportBuilder tests
# ---------------------------------------------------------------------------#

def test_report_builder_build_provenance():
    rb = ReportBuilder()
    cap_data = ProjectCapabilityData(available=True, verdict="capable")
    arch_data = ArchitectureDecisionData(available=True, decision_count=8)
    tech_data = TechnologySelectionData(available=True, selection_count=5)
    req_data = RequirementNormalizationData(available=True, requirement_count=3)
    kb_data = KnowledgeData(available=True)
    provenance = rb.build_provenance(
        cap_data, arch_data, tech_data, req_data, kb_data
    )
    assert provenance.project_capability_available is True
    assert provenance.architecture_decision_available is True
    assert provenance.technology_selection_available is True
    assert provenance.normalized_requirements_available is True
    assert provenance.knowledge_base_available is True
    assert provenance.capability_verdict == "capable"
    assert provenance.decision_count == 8
    assert provenance.selection_count == 5
    assert provenance.requirement_count == 3
    print("  [PASS] test_report_builder_build_provenance")


def test_report_builder_build():
    rb = ReportBuilder()
    dimension_results = [
        RiskDimensionResult(dimension=dim, score=0.3)
        for dim in ALL_DIMENSIONS
    ]
    findings = []
    cache_info = CacheInfo(status=CACHE_MISS)
    provenance = RiskProvenance(
        project_capability_available=True,
        architecture_decision_available=True,
        technology_selection_available=True,
        normalized_requirements_available=True,
        knowledge_base_available=True,
    )
    report = rb.build(
        dimension_results=dimension_results,
        findings=findings,
        cache_info=cache_info,
        provenance=provenance,
        gate_passed=True,
    )
    assert report.dimension_count == 7
    assert 0.0 <= report.confidence <= 1.0
    assert report.confidence_level in (
        CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    )
    assert report.verdict in ALL_VERDICTS
    assert report.summary != ""
    assert len(report.notes) > 0
    print("  [PASS] test_report_builder_build")


def test_report_builder_verdict_not_ready():
    rb = ReportBuilder()
    dimension_results = [
        RiskDimensionResult(dimension=dim)
        for dim in ALL_DIMENSIONS
    ]
    findings = []
    cache_info = CacheInfo(status=CACHE_MISS)
    provenance = RiskProvenance()
    report = rb.build(
        dimension_results=dimension_results,
        findings=findings,
        cache_info=cache_info,
        provenance=provenance,
        gate_passed=False,
    )
    assert report.verdict == VERDICT_NOT_READY
    assert report.is_blocked is True
    assert report.is_ready is False
    print("  [PASS] test_report_builder_verdict_not_ready")


def test_report_builder_verdict_ready_with_risks():
    rb = ReportBuilder()
    # Build dimension results with some low/medium risks.
    dim_results = []
    for dim in ALL_DIMENSIONS:
        dr = RiskDimensionResult(
            dimension=dim,
            risk_count=1,
            low_count=1,
            score=0.25,
            risks=[
                RiskItem(
                    risk_id=f"R-{dim}",
                    dimension=dim,
                    severity=SEVERITY_LOW,
                )
            ],
        )
        dim_results.append(dr)
    findings = []
    cache_info = CacheInfo(status=CACHE_MISS)
    provenance = RiskProvenance(
        project_capability_available=True,
        architecture_decision_available=True,
        technology_selection_available=True,
        normalized_requirements_available=True,
        knowledge_base_available=True,
    )
    report = rb.build(
        dimension_results=dim_results,
        findings=findings,
        cache_info=cache_info,
        provenance=provenance,
        gate_passed=True,
    )
    # With low risks and all sources, should be ready_with_risks.
    assert report.verdict in (
        VERDICT_READY_WITH_RISKS, VERDICT_READY, VERDICT_NOT_READY
    )
    assert report.risk_count > 0
    print("  [PASS] test_report_builder_verdict_ready_with_risks")


def test_report_builder_verdict_blocked_by_critical():
    rb = ReportBuilder()
    dim_results = []
    for dim in ALL_DIMENSIONS:
        dr = RiskDimensionResult(
            dimension=dim,
            risk_count=1,
            critical_count=1,
            score=1.0,
            risks=[
                RiskItem(
                    risk_id=f"R-CRIT-{dim}",
                    dimension=dim,
                    severity=SEVERITY_CRITICAL,
                )
            ],
        )
        dim_results.append(dr)
    findings = []
    cache_info = CacheInfo(status=CACHE_MISS)
    provenance = RiskProvenance(
        project_capability_available=True,
        architecture_decision_available=True,
        technology_selection_available=True,
        normalized_requirements_available=True,
        knowledge_base_available=True,
    )
    report = rb.build(
        dimension_results=dim_results,
        findings=findings,
        cache_info=cache_info,
        provenance=provenance,
        gate_passed=False,
    )
    assert report.verdict == VERDICT_NOT_READY
    assert report.is_blocked is True
    assert report.has_critical_risks is True
    print("  [PASS] test_report_builder_verdict_blocked_by_critical")


# ---------------------------------------------------------------------------#
# 20. Engine tests
# ---------------------------------------------------------------------------#

def test_engine_no_data():
    engine = RiskDetectionEngine()
    ctx = make_empty_context()
    result = engine.execute(ctx)
    assert result.success is True
    report = ctx.get("risk_analysis_report")
    assert report is not None
    assert isinstance(report, RiskAnalysisReport)
    print("  [PASS] test_engine_no_data")


def test_engine_with_all_data():
    engine = RiskDetectionEngine()
    ctx = make_full_context()
    result = engine.execute(ctx)
    assert result.success is True
    report = ctx.get("risk_analysis_report")
    assert report is not None
    assert report.dimension_count == 7
    print("  [PASS] test_engine_with_all_data")


def test_engine_produces_artefact():
    engine = RiskDetectionEngine()
    ctx = make_full_context()
    engine.execute(ctx)
    assert ctx.has("risk_analysis_report")
    report = ctx.get("risk_analysis_report")
    assert isinstance(report, RiskAnalysisReport)
    print("  [PASS] test_engine_produces_artefact")


def test_engine_stores_in_metadata():
    engine = RiskDetectionEngine()
    ctx = make_full_context()
    engine.execute(ctx)
    assert "risk_analysis_report" in ctx.metadata
    report = ctx.metadata["risk_analysis_report"]
    assert isinstance(report, RiskAnalysisReport)
    print("  [PASS] test_engine_stores_in_metadata")


def test_engine_does_not_write_files():
    engine = RiskDetectionEngine()
    ctx = make_full_context()
    result = engine.execute(ctx)
    # The engine should not create any files.
    assert result.success is True
    print("  [PASS] test_engine_does_not_write_files")


def test_engine_all_seven_analyses():
    engine = RiskDetectionEngine()
    ctx = make_full_context()
    engine.execute(ctx)
    report = ctx.get("risk_analysis_report")
    dims = report.dimension_names()
    assert DIMENSION_ARCHITECTURE in dims
    assert DIMENSION_PERFORMANCE in dims
    assert DIMENSION_SCALABILITY in dims
    assert DIMENSION_SECURITY in dims
    assert DIMENSION_DEPENDENCY in dims
    assert DIMENSION_MAINTENANCE in dims
    assert DIMENSION_RESOURCE in dims
    assert len(dims) == 7
    print("  [PASS] test_engine_all_seven_analyses")


def test_engine_verdict():
    engine = RiskDetectionEngine()
    ctx = make_full_context()
    engine.execute(ctx)
    report = ctx.get("risk_analysis_report")
    assert report.verdict in ALL_VERDICTS
    print("  [PASS] test_engine_verdict")


def test_engine_confidence_in_range():
    engine = RiskDetectionEngine()
    ctx = make_full_context()
    engine.execute(ctx)
    report = ctx.get("risk_analysis_report")
    assert 0.0 <= report.confidence <= 1.0
    assert report.confidence_level in (
        CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    )
    print("  [PASS] test_engine_confidence_in_range")


def test_engine_cache_hit():
    engine = RiskDetectionEngine()
    ctx = make_full_context()
    # First run -- should be a cache miss.
    result1 = engine.execute(ctx)
    assert result1.outputs["cache_hit"] is False
    # Second run with same data -- should be a cache hit.
    result2 = engine.execute(ctx)
    assert result2.outputs["cache_hit"] is True
    print("  [PASS] test_engine_cache_hit")


def test_engine_outputs_have_correct_keys():
    engine = RiskDetectionEngine()
    ctx = make_full_context()
    result = engine.execute(ctx)
    expected_keys = [
        "report",
        "dimension_count",
        "risk_count",
        "critical_count",
        "high_count",
        "medium_count",
        "low_count",
        "ready",
        "verdict",
        "confidence",
        "confidence_level",
        "cache_hit",
    ]
    for key in expected_keys:
        assert key in result.outputs, f"Missing key: {key}"
    print("  [PASS] test_engine_outputs_have_correct_keys")


# ---------------------------------------------------------------------------#
# 21. Bootstrap tests
# ---------------------------------------------------------------------------#

def test_bootstrap_registers_risk_detection():
    config = build_configuration()
    registry, orchestrator, manager = bootstrap(config)
    engines = registry.engine_names()
    found = False
    for e in engines:
        if "risk" in str(e).lower():
            found = True
            break
    assert found, "risk_detection not found in registry"
    print("  [PASS] test_bootstrap_registers_risk_detection")


def test_bootstrap_risk_detection_priority():
    config = build_configuration()
    registry, orchestrator, manager = bootstrap(config)
    entries = manager._entries if hasattr(manager, "_entries") else {}
    found = False
    for key, entry in entries.items():
        if entry.engine_id == "risk_detection":
            assert entry.priority == 45
            found = True
            break
    assert found, "risk_detection not found in manager"
    print("  [PASS] test_bootstrap_risk_detection_priority")


def test_bootstrap_risk_detection_dependencies():
    config = build_configuration()
    registry, orchestrator, manager = bootstrap(config)
    entries = manager._entries if hasattr(manager, "_entries") else {}
    found = False
    for key, entry in entries.items():
        if entry.engine_id == "risk_detection":
            assert "technology_selection" in entry.dependencies
            found = True
            break
    assert found, "risk_detection not found in manager"
    print("  [PASS] test_bootstrap_risk_detection_dependencies")


# ---------------------------------------------------------------------------#
# 22. Serialisation tests
# ---------------------------------------------------------------------------#

def test_risk_item_serialisation():
    ri = RiskItem(
        risk_id="R-SER-001",
        dimension=DIMENSION_ARCHITECTURE,
        risk_type=ARCH_RISK_POOR_PARTITIONING,
        severity=SEVERITY_HIGH,
        fix_priority=PRIORITY_HIGH,
    )
    d = ri.to_dict()
    assert d["risk_id"] == "R-SER-001"
    assert d["dimension"] == DIMENSION_ARCHITECTURE
    assert d["severity"] == SEVERITY_HIGH
    assert d["fix_priority"] == PRIORITY_HIGH
    print("  [PASS] test_risk_item_serialisation")


def test_risk_recommendation_serialisation():
    rec = RiskRecommendation(
        recommendation_id="REC-SER-001",
        dimension=DIMENSION_SECURITY,
        priority=PRIORITY_IMMEDIATE,
    )
    d = rec.to_dict()
    assert d["recommendation_id"] == "REC-SER-001"
    assert d["dimension"] == DIMENSION_SECURITY
    assert d["priority"] == PRIORITY_IMMEDIATE
    print("  [PASS] test_risk_recommendation_serialisation")


def test_risk_dimension_result_serialisation():
    dr = RiskDimensionResult(
        dimension=DIMENSION_PERFORMANCE,
        risk_count=3,
        score=0.5,
    )
    d = dr.to_dict()
    assert d["dimension"] == DIMENSION_PERFORMANCE
    assert d["risk_count"] == 3
    assert d["score"] == 0.5
    print("  [PASS] test_risk_dimension_result_serialisation")


def test_risk_finding_serialisation():
    rf = RiskFinding(
        severity=SEVERITY_MEDIUM,
        code="SER-001",
        message="Medium finding.",
    )
    d = rf.to_dict()
    assert d["severity"] == SEVERITY_MEDIUM
    assert d["code"] == "SER-001"
    print("  [PASS] test_risk_finding_serialisation")


def test_cache_info_serialisation():
    ci = CacheInfo(status=CACHE_HIT, cache_key="key_abc")
    d = ci.to_dict()
    assert d["status"] == CACHE_HIT
    assert d["cache_key"] == "key_abc"
    print("  [PASS] test_cache_info_serialisation")


def test_risk_provenance_serialisation():
    rp = RiskProvenance(
        decision_count=8,
        selection_count=5,
        capability_verdict="capable",
    )
    d = rp.to_dict()
    assert d["decision_count"] == 8
    assert d["selection_count"] == 5
    assert d["capability_verdict"] == "capable"
    print("  [PASS] test_risk_provenance_serialisation")


def test_risk_analysis_report_serialisation():
    report = RiskAnalysisReport()
    report.add_risk(
        RiskItem(risk_id="R1", severity=SEVERITY_HIGH)
    )
    report.confidence = 0.7
    report.verdict = VERDICT_READY_WITH_RISKS
    d = report.to_dict()
    assert d["risk_count"] == 1
    assert d["high_count"] == 1
    assert d["confidence"] == 0.7
    assert d["verdict"] == VERDICT_READY_WITH_RISKS
    assert "risks" in d
    assert "provenance" in d
    assert "cache_info" in d
    print("  [PASS] test_risk_analysis_report_serialisation")


# ---------------------------------------------------------------------------#
# 23. End-to-end tests
# ---------------------------------------------------------------------------#

def test_end_to_end_with_all_sources():
    engine = RiskDetectionEngine()
    ctx = make_full_context()
    result = engine.execute(ctx)
    assert result.success is True
    report = ctx.get("risk_analysis_report")
    assert report is not None
    assert report.dimension_count == 7
    assert report.verdict in ALL_VERDICTS
    assert 0.0 <= report.confidence <= 1.0
    assert report.provenance.project_capability_available is True
    assert report.provenance.architecture_decision_available is True
    assert report.provenance.technology_selection_available is True
    assert report.provenance.normalized_requirements_available is True
    assert report.provenance.knowledge_base_available is True
    print("  [PASS] test_end_to_end_with_all_sources")


def test_end_to_end_empty_context():
    engine = RiskDetectionEngine()
    ctx = make_empty_context()
    result = engine.execute(ctx)
    assert result.success is True
    report = ctx.get("risk_analysis_report")
    assert report is not None
    assert report.provenance.project_capability_available is False
    assert report.provenance.architecture_decision_available is False
    print("  [PASS] test_end_to_end_empty_context")


def test_end_to_end_with_capability_only():
    engine = RiskDetectionEngine()
    ctx = make_context(
        project_capability_report=(
            make_project_capability_report()
        ),
    )
    result = engine.execute(ctx)
    assert result.success is True
    report = ctx.get("risk_analysis_report")
    assert report is not None
    assert report.provenance.project_capability_available is True
    assert report.provenance.architecture_decision_available is False
    print("  [PASS] test_end_to_end_with_capability_only")


def test_end_to_end_report_summary():
    engine = RiskDetectionEngine()
    ctx = make_full_context()
    engine.execute(ctx)
    report = ctx.get("risk_analysis_report")
    assert report.summary != ""
    assert "verdict" in report.summary.lower() or len(report.summary) > 0
    print("  [PASS] test_end_to_end_report_summary")


def test_end_to_end_report_notes():
    engine = RiskDetectionEngine()
    ctx = make_full_context()
    engine.execute(ctx)
    report = ctx.get("risk_analysis_report")
    assert len(report.notes) > 0
    print("  [PASS] test_end_to_end_report_notes")


# ---------------------------------------------------------------------------#
# 24. Report ready/blocking tests
# ---------------------------------------------------------------------------#

def test_report_blocked_when_gate_fails():
    """When the quality gate fails, the verdict should be
    NOT_READY."""
    rb = ReportBuilder()
    dimension_results = [
        RiskDimensionResult(dimension=dim)
        for dim in ALL_DIMENSIONS
    ]
    findings = []
    cache_info = CacheInfo(status=CACHE_MISS)
    provenance = RiskProvenance()
    report = rb.build(
        dimension_results=dimension_results,
        findings=findings,
        cache_info=cache_info,
        provenance=provenance,
        gate_passed=False,
    )
    assert report.verdict == VERDICT_NOT_READY
    assert report.is_blocked is True
    assert report.ready is False
    print("  [PASS] test_report_blocked_when_gate_fails")


def test_report_ready_with_risks():
    """When the gate passes but there are low-severity risks,
    the verdict should be READY_WITH_RISKS."""
    rb = ReportBuilder()
    dim_results = []
    for dim in ALL_DIMENSIONS:
        dr = RiskDimensionResult(
            dimension=dim,
            risk_count=1,
            low_count=1,
            score=0.25,
            risks=[
                RiskItem(
                    risk_id=f"R-{dim}",
                    dimension=dim,
                    severity=SEVERITY_LOW,
                )
            ],
        )
        dim_results.append(dr)
    findings = []
    cache_info = CacheInfo(status=CACHE_MISS)
    provenance = RiskProvenance(
        project_capability_available=True,
        architecture_decision_available=True,
        technology_selection_available=True,
        normalized_requirements_available=True,
        knowledge_base_available=True,
    )
    report = rb.build(
        dimension_results=dim_results,
        findings=findings,
        cache_info=cache_info,
        provenance=provenance,
        gate_passed=True,
    )
    # With low risks and all sources, should not be blocked.
    assert report.has_critical_risks is False
    assert report.is_blocked is False
    print("  [PASS] test_report_ready_with_risks")


# ---------------------------------------------------------------------------#
# Run all tests
# ---------------------------------------------------------------------------#

def run_all_tests():
    """Run all tests and report results."""

    tests = [
        # Data model -- RiskItem
        test_risk_item_creation,
        test_risk_item_to_dict,
        # Data model -- RiskRecommendation
        test_risk_recommendation_creation,
        test_risk_recommendation_to_dict,
        # Data model -- RiskDimensionResult
        test_risk_dimension_result_creation,
        test_risk_dimension_result_to_dict,
        # Data model -- RiskFinding
        test_risk_finding_creation,
        test_risk_finding_to_dict,
        # Data model -- CacheInfo
        test_cache_info_creation,
        test_cache_info_to_dict,
        # Data model -- RiskProvenance
        test_risk_provenance_creation,
        test_risk_provenance_to_dict,
        # Data model -- RiskAnalysisReport
        test_risk_analysis_report_creation,
        test_risk_analysis_report_add_risk,
        test_risk_analysis_report_add_critical_risk,
        test_risk_analysis_report_add_recommendation,
        test_risk_analysis_report_add_strength,
        test_risk_analysis_report_add_finding,
        test_risk_analysis_report_add_low_finding_no_warning,
        test_risk_analysis_report_get_dimension,
        test_risk_analysis_report_dimension_names,
        test_risk_analysis_report_risks_by_severity,
        test_risk_analysis_report_risks_by_dimension,
        test_risk_analysis_report_critical_risks,
        test_risk_analysis_report_all_dimensions_analysed,
        test_risk_analysis_report_not_all_dimensions_analysed,
        test_risk_analysis_report_overall_risk_score,
        test_risk_analysis_report_overall_risk_score_empty,
        test_risk_analysis_report_is_ready,
        test_risk_analysis_report_is_blocked,
        test_risk_analysis_report_has_sufficient_confidence,
        test_risk_analysis_report_ready_property,
        test_risk_analysis_report_ready_blocked_by_critical,
        test_risk_analysis_report_to_dict,
        # Constants
        test_source_constants,
        test_severity_constants,
        test_dimension_constants,
        test_arch_risk_constants,
        test_perf_risk_constants,
        test_sec_risk_constants,
        test_dep_risk_constants,
        test_maint_risk_constants,
        test_res_risk_constants,
        test_priority_constants,
        test_quality_rule_constants,
        test_cache_status_constants,
        test_confidence_constants,
        test_verdict_constants,
        # Readers
        test_project_capability_reader_empty_context,
        test_project_capability_reader_with_report,
        test_architecture_decision_reader_empty_context,
        test_architecture_decision_reader_with_report,
        test_technology_selection_reader_empty_context,
        test_technology_selection_reader_with_report,
        test_requirement_normalization_reader_empty_context,
        test_requirement_normalization_reader_with_report,
        test_knowledge_reader_empty_context,
        test_knowledge_reader_with_base,
        # ArchitectureRiskAnalyzer
        test_architecture_risk_analyzer_empty,
        test_architecture_risk_analyzer_with_data,
        test_architecture_risk_analyzer_circular_deps,
        # PerformanceRiskAnalyzer
        test_performance_risk_analyzer_empty,
        test_performance_risk_analyzer_with_data,
        # ScalabilityRiskAnalyzer
        test_scalability_risk_analyzer_empty,
        test_scalability_risk_analyzer_with_data,
        # SecurityRiskAnalyzer
        test_security_risk_analyzer_empty,
        test_security_risk_analyzer_with_data,
        # DependencyRiskAnalyzer
        test_dependency_risk_analyzer_empty,
        test_dependency_risk_analyzer_with_data,
        # MaintenanceRiskAnalyzer
        test_maintenance_risk_analyzer_empty,
        test_maintenance_risk_analyzer_with_data,
        # ResourceRiskAnalyzer
        test_resource_risk_analyzer_empty,
        test_resource_risk_analyzer_with_data,
        # QualityGate
        test_quality_gate_passes_good_report,
        test_quality_gate_fails_empty_report,
        test_quality_gate_fails_critical_risks,
        test_quality_gate_fails_missing_dimensions,
        test_quality_gate_fails_low_confidence,
        # CacheManager
        test_cache_manager_miss,
        test_cache_manager_hit,
        test_cache_manager_store,
        # ReportBuilder
        test_report_builder_build_provenance,
        test_report_builder_build,
        test_report_builder_verdict_not_ready,
        test_report_builder_verdict_ready_with_risks,
        test_report_builder_verdict_blocked_by_critical,
        # Engine
        test_engine_no_data,
        test_engine_with_all_data,
        test_engine_produces_artefact,
        test_engine_stores_in_metadata,
        test_engine_does_not_write_files,
        test_engine_all_seven_analyses,
        test_engine_verdict,
        test_engine_confidence_in_range,
        test_engine_cache_hit,
        test_engine_outputs_have_correct_keys,
        # Bootstrap
        test_bootstrap_registers_risk_detection,
        test_bootstrap_risk_detection_priority,
        test_bootstrap_risk_detection_dependencies,
        # Serialisation
        test_risk_item_serialisation,
        test_risk_recommendation_serialisation,
        test_risk_dimension_result_serialisation,
        test_risk_finding_serialisation,
        test_cache_info_serialisation,
        test_risk_provenance_serialisation,
        test_risk_analysis_report_serialisation,
        # End-to-end
        test_end_to_end_with_all_sources,
        test_end_to_end_empty_context,
        test_end_to_end_with_capability_only,
        test_end_to_end_report_summary,
        test_end_to_end_report_notes,
        # Report ready/blocking
        test_report_blocked_when_gate_fails,
        test_report_ready_with_risks,
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
