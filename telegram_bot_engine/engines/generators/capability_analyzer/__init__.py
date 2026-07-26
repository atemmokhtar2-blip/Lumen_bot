"""
Project Capability Analyzer Engine package (Specification 017).

This package contains the project capability analyzer engine — the
engine that analyzes the project's full capability before building
starts.  It does not write code, create files, or build the project.
Its sole function is reading five data sources, performing five
analyses (complexity, resources, scalability, stress, dependencies),
validating the architecture through the quality gate, and producing
the *Project Capability Report* — the official reference for all
downstream engines that need capability information.

Public surface
--------------
* :class:`ProjectCapabilityAnalyzerEngine` — the engine itself.
* :class:`ProjectCapabilityReport` and all of its sub-dataclasses
  (:class:`AnalysisResult`, :class:`ComplexityAnalysis`,
  :class:`ResourceEstimation`, :class:`ScalabilityTier`,
  :class:`ScalabilityAnalysis`, :class:`Bottleneck`,
  :class:`ArchitectureStressAnalysis`, :class:`DependencyIssue`,
  :class:`DependencyAnalysis`, :class:`CapabilityFinding`,
  :class:`CacheInfo`, :class:`CapabilityProvenance`).
* :class:`ArchitectureDecisionReader`,
  :class:`TechnologySelectionReader`,
  :class:`RequirementNormalizationReader`,
  :class:`IntelligenceGraphReader`, :class:`KnowledgeReader` — the
  five data-source readers.
* :class:`ComplexityAnalyzer`, :class:`ResourceEstimator`,
  :class:`ScalabilityAnalyzer`, :class:`StressAnalyzer`,
  :class:`DependencyAnalyzer` — the five analyzers.
* :class:`QualityGate`, :class:`ReportBuilder`,
  :class:`CacheManager` — the helpers and processors.
* Source-artefact, severity, complexity, size, scale-tier,
  load-level, bottleneck, dependency-issue, analysis-dimension,
  quality-rule, cache-status, confidence-level, and verdict
  constants.
"""

from __future__ import annotations

from .capability_analyzer_engine import ProjectCapabilityAnalyzerEngine
from .report_data import (
    # Data model — sub-reports
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
)
from .data_readers import (
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
)
from .complexity_analyzer import ComplexityAnalyzer
from .resource_estimator import ResourceEstimator
from .scalability_analyzer import ScalabilityAnalyzer
from .stress_analyzer import StressAnalyzer
from .dependency_analyzer import DependencyAnalyzer
from .quality_gate import QualityGate
from .report_builder import ReportBuilder
from .cache_manager import CacheManager

__all__ = [
    # Engine
    "ProjectCapabilityAnalyzerEngine",
    # Data model — sub-reports
    "AnalysisResult",
    "ComplexityAnalysis",
    "ResourceEstimation",
    "ScalabilityTier",
    "ScalabilityAnalysis",
    "Bottleneck",
    "ArchitectureStressAnalysis",
    "DependencyIssue",
    "DependencyAnalysis",
    "CapabilityFinding",
    "CacheInfo",
    "CapabilityProvenance",
    "ProjectCapabilityReport",
    # Source-artefact constants
    "SOURCE_ARCHITECTURE_DECISION",
    "SOURCE_TECHNOLOGY_SELECTION",
    "SOURCE_NORMALIZED_REQUIREMENTS",
    "SOURCE_INTELLIGENCE_GRAPH",
    "SOURCE_KNOWLEDGE_BASE",
    "ALL_SOURCES",
    # Severity constants
    "SEVERITY_ERROR",
    "SEVERITY_WARNING",
    "SEVERITY_INFO",
    "ALL_SEVERITIES",
    # Complexity level constants
    "COMPLEXITY_TRIVIAL",
    "COMPLEXITY_LOW",
    "COMPLEXITY_MODERATE",
    "COMPLEXITY_HIGH",
    "COMPLEXITY_VERY_HIGH",
    "ALL_COMPLEXITY_LEVELS",
    "COMPLEXITY_THRESHOLD_TRIVIAL",
    "COMPLEXITY_THRESHOLD_LOW",
    "COMPLEXITY_THRESHOLD_MODERATE",
    "COMPLEXITY_THRESHOLD_HIGH",
    # Project size constants
    "SIZE_TINY",
    "SIZE_SMALL",
    "SIZE_MEDIUM",
    "SIZE_LARGE",
    "SIZE_VERY_LARGE",
    "ALL_SIZES",
    "SIZE_THRESHOLD_TINY",
    "SIZE_THRESHOLD_SMALL",
    "SIZE_THRESHOLD_MEDIUM",
    "SIZE_THRESHOLD_LARGE",
    # Scale tier constants
    "SCALE_THOUSANDS",
    "SCALE_TENS_OF_THOUSANDS",
    "SCALE_HUNDREDS_OF_THOUSANDS",
    "SCALE_MILLIONS",
    "ALL_SCALE_TIERS",
    "SCALE_THRESHOLD_THOUSANDS",
    "SCALE_THRESHOLD_TENS_OF_THOUSANDS",
    "SCALE_THRESHOLD_HUNDREDS_OF_THOUSANDS",
    "SCALE_THRESHOLD_MILLIONS",
    # Load level constants
    "LOAD_LIGHT",
    "LOAD_MODERATE",
    "LOAD_HEAVY",
    "LOAD_PEAK",
    "ALL_LOAD_LEVELS",
    # Bottleneck constants
    "BOTTLENECK_CRITICAL",
    "BOTTLENECK_MAJOR",
    "BOTTLENECK_MINOR",
    "BOTTLENECK_NONE",
    "ALL_BOTTLENECK_LEVELS",
    # Dependency issue constants
    "DEP_ISSUE_CIRCULAR",
    "DEP_ISSUE_UNUSED",
    "DEP_ISSUE_MISSING",
    "DEP_ISSUE_CONFLICT",
    "ALL_DEP_ISSUES",
    # Analysis dimension constants
    "DIMENSION_COMPLEXITY",
    "DIMENSION_RESOURCES",
    "DIMENSION_SCALABILITY",
    "DIMENSION_STRESS",
    "DIMENSION_DEPENDENCIES",
    "ALL_DIMENSIONS",
    # Quality rule constants
    "RULE_PERFORMANCE",
    "RULE_SCALABILITY",
    "RULE_QUALITY",
    "RULE_DEPENDENCY_HEALTH",
    "ALL_QUALITY_RULES",
    # Cache status constants
    "CACHE_HIT",
    "CACHE_MISS",
    "CACHE_STALE",
    "CACHE_DISABLED",
    "ALL_CACHE_STATUSES",
    # Confidence level constants
    "CONFIDENCE_HIGH",
    "CONFIDENCE_MEDIUM",
    "CONFIDENCE_LOW",
    "ALL_CONFIDENCE_LEVELS",
    "CONFIDENCE_HIGH_THRESHOLD",
    "CONFIDENCE_MEDIUM_THRESHOLD",
    # Verdict constants
    "VERDICT_CAPABLE",
    "VERDICT_CAPABLE_WITH_RISKS",
    "VERDICT_NOT_CAPABLE",
    "ALL_VERDICTS",
    # Readers + intermediate data
    "ArchitectureDecisionData",
    "ArchitectureDecisionReader",
    "TechnologySelectionData",
    "TechnologySelectionReader",
    "RequirementNormalizationData",
    "RequirementNormalizationReader",
    "IntelligenceGraphData",
    "IntelligenceGraphReader",
    "KnowledgeData",
    "KnowledgeReader",
    # Analyzers
    "ComplexityAnalyzer",
    "ResourceEstimator",
    "ScalabilityAnalyzer",
    "StressAnalyzer",
    "DependencyAnalyzer",
    # Helpers and processors
    "QualityGate",
    "ReportBuilder",
    "CacheManager",
]
