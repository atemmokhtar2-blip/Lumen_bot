"""
Risk Detection Engine package (Specification 018).

This package contains the risk detection engine -- the engine that
detects all potential risks before project generation begins.  It
does not write code, create files, or start the build process.  Its
sole function is reading five data sources, performing seven risk
analyses (architecture, performance, scalability, security,
dependency, maintenance, resource), classifying each risk by
severity, producing recommendations, and determining the project's
readiness for the generation phase.  It blocks generation if a
Critical risk exists.

Public surface
--------------
* :class:`RiskDetectionEngine` -- the engine itself.
* :class:`RiskAnalysisReport` and all of its sub-dataclasses
  (:class:`RiskItem`, :class:`RiskRecommendation`,
  :class:`RiskDimensionResult`, :class:`RiskFinding`,
  :class:`CacheInfo`, :class:`RiskProvenance`).
* :class:`ProjectCapabilityReader`,
  :class:`ArchitectureDecisionReader`,
  :class:`TechnologySelectionReader`,
  :class:`RequirementNormalizationReader`,
  :class:`KnowledgeReader` -- the five data-source readers.
* :class:`ArchitectureRiskAnalyzer`,
  :class:`PerformanceRiskAnalyzer`,
  :class:`ScalabilityRiskAnalyzer`,
  :class:`SecurityRiskAnalyzer`,
  :class:`DependencyRiskAnalyzer`,
  :class:`MaintenanceRiskAnalyzer`,
  :class:`ResourceRiskAnalyzer` -- the seven analyzers.
* :class:`QualityGate`, :class:`ReportBuilder`,
  :class:`CacheManager` -- the helpers and processors.
* Source-artefact, severity, dimension, risk-type, fix-priority,
  quality-rule, cache-status, confidence-level, and verdict
  constants.
"""

from __future__ import annotations

from .risk_detection_engine import RiskDetectionEngine
from .report_data import (
    # Data model -- sub-reports
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
    SEVERITY_RANK,
    SEVERITY_SCORE,
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
)
from .data_readers import (
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
)
from .architecture_risk_analyzer import ArchitectureRiskAnalyzer
from .performance_risk_analyzer import PerformanceRiskAnalyzer
from .scalability_risk_analyzer import ScalabilityRiskAnalyzer
from .security_risk_analyzer import SecurityRiskAnalyzer
from .dependency_risk_analyzer import DependencyRiskAnalyzer
from .maintenance_risk_analyzer import MaintenanceRiskAnalyzer
from .resource_risk_analyzer import ResourceRiskAnalyzer
from .quality_gate import QualityGate
from .report_builder import ReportBuilder
from .cache_manager import CacheManager

__all__ = [
    # Engine
    "RiskDetectionEngine",
    # Data model -- sub-reports
    "RiskItem",
    "RiskRecommendation",
    "RiskDimensionResult",
    "RiskFinding",
    "CacheInfo",
    "RiskProvenance",
    "RiskAnalysisReport",
    # Source-artefact constants
    "SOURCE_PROJECT_CAPABILITY",
    "SOURCE_ARCHITECTURE_DECISION",
    "SOURCE_TECHNOLOGY_SELECTION",
    "SOURCE_NORMALIZED_REQUIREMENTS",
    "SOURCE_KNOWLEDGE_BASE",
    "ALL_SOURCES",
    # Severity constants
    "SEVERITY_CRITICAL",
    "SEVERITY_HIGH",
    "SEVERITY_MEDIUM",
    "SEVERITY_LOW",
    "ALL_SEVERITIES",
    "SEVERITY_RANK",
    "SEVERITY_SCORE",
    # Dimension constants
    "DIMENSION_ARCHITECTURE",
    "DIMENSION_PERFORMANCE",
    "DIMENSION_SCALABILITY",
    "DIMENSION_SECURITY",
    "DIMENSION_DEPENDENCY",
    "DIMENSION_MAINTENANCE",
    "DIMENSION_RESOURCE",
    "ALL_DIMENSIONS",
    # Architecture risk type constants
    "ARCH_RISK_POOR_PARTITIONING",
    "ARCH_RISK_CIRCULAR_DEPENDENCIES",
    "ARCH_RISK_EXCESSIVE_COUPLING",
    "ARCH_RISK_WEAK_EXTENSIBILITY",
    "ALL_ARCH_RISKS",
    # Performance risk type constants
    "PERF_RISK_BOTTLENECK",
    "PERF_RISK_HIGH_MEMORY",
    "PERF_RISK_SLOW_OPERATION",
    "PERF_RISK_UNNECESSARY_REPETITION",
    "ALL_PERF_RISKS",
    # Security risk type constants
    "SEC_RISK_INPUT_VALIDATION",
    "SEC_RISK_AUTHORIZATION",
    "SEC_RISK_DATA_EXPOSURE",
    "SEC_RISK_INSECURE_COMMUNICATION",
    "SEC_RISK_SECRETS_MANAGEMENT",
    "ALL_SEC_RISKS",
    # Dependency risk type constants
    "DEP_RISK_VERSION_CONFLICT",
    "DEP_RISK_DEPRECATED",
    "DEP_RISK_SECURITY_VULNERABILITY",
    "DEP_RISK_TOO_MANY",
    "DEP_RISK_SINGLE_POINT",
    "ALL_DEP_RISKS",
    # Maintenance risk type constants
    "MAINT_RISK_COMPLEXITY",
    "MAINT_RISK_NO_TESTS",
    "MAINT_RISK_NO_DOCS",
    "MAINT_RISK_TIGHT_COUPLING",
    "MAINT_RISK_NO_MONITORING",
    "ALL_MAINT_RISKS",
    # Resource risk type constants
    "RES_RISK_CPU_BOUND",
    "RES_RISK_MEMORY_BOUND",
    "RES_RISK_DISK_BOUND",
    "RES_RISK_NETWORK_BOUND",
    "RES_RISK_COST_OVERRUN",
    "ALL_RES_RISKS",
    # Fix priority constants
    "PRIORITY_IMMEDIATE",
    "PRIORITY_HIGH",
    "PRIORITY_MEDIUM",
    "PRIORITY_LOW",
    "ALL_PRIORITIES",
    # Quality rule constants
    "RULE_NO_CRITICAL_RISKS",
    "RULE_ALL_DIMENSIONS_ANALYSED",
    "RULE_RISKS_HAVE_RECOMMENDATIONS",
    "RULE_SUFFICIENT_CONFIDENCE",
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
    "VERDICT_READY",
    "VERDICT_READY_WITH_RISKS",
    "VERDICT_NOT_READY",
    "ALL_VERDICTS",
    # Readers + intermediate data
    "ProjectCapabilityData",
    "ProjectCapabilityReader",
    "ArchitectureDecisionData",
    "ArchitectureDecisionReader",
    "TechnologySelectionData",
    "TechnologySelectionReader",
    "RequirementNormalizationData",
    "RequirementNormalizationReader",
    "KnowledgeData",
    "KnowledgeReader",
    # Analyzers
    "ArchitectureRiskAnalyzer",
    "PerformanceRiskAnalyzer",
    "ScalabilityRiskAnalyzer",
    "SecurityRiskAnalyzer",
    "DependencyRiskAnalyzer",
    "MaintenanceRiskAnalyzer",
    "ResourceRiskAnalyzer",
    # Helpers and processors
    "QualityGate",
    "ReportBuilder",
    "CacheManager",
]
