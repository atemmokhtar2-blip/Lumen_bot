"""
Architecture Decision Engine package (Specification 015).

This package contains the architecture decision engine — the engine
that makes **all architectural decisions** for the project.  It does
not write code, create files, or build the project.  Its sole
function is selecting the best architecture based on prior
analysis and producing the *Architecture Decision Report* — the
official reference for all other engines.

Public surface
--------------
* :class:`ArchitectureDecisionEngine` — the engine itself.
* :class:`ArchitectureDecisionReport` and all of its sub-dataclasses
  (:class:`AnalysisResult`, :class:`RejectedAlternative`,
  :class:`ArchitectureDecision`, :class:`ArchitectureFinding`,
  :class:`CacheInfo`, :class:`ArchitectureProvenance`,
  :class:`ModuleSpec`, :class:`ServiceSpec`).
* :class:`RequirementNormalizationReader`, :class:`IntelligenceGraphReader`,
  :class:`RequirementIntelligenceReader`,
  :class:`SemanticUnderstandingReader`, :class:`KnowledgeReader` — the
  five data-source readers.
* :class:`SizeAnalyzer`, :class:`ScalabilityAnalyzer`,
  :class:`PerformanceAnalyzer`, :class:`SecurityAnalyzer`,
  :class:`MaintainabilityAnalyzer` — the five analyzers.
* :class:`ArchitectureSelector` — the core decision-making component.
* :class:`DecisionValidator`, :class:`QualityGate`,
  :class:`CacheManager`, :class:`ReportAssembler` — the helpers and
  processors.
* Source-artefact, severity, size, pattern, layer, communication,
  error-handling, configuration, dependency-structure, layout,
  analysis-dimension, decision-domain, cache-status, and
  confidence-level constants.
"""

from __future__ import annotations

from .architecture_decision_engine import ArchitectureDecisionEngine
from .report_data import (
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
)
from .requirement_normalization_reader import (
    RequirementNormalizationReader,
    RequirementNormalizationData,
    NormalizedRequirementView,
)
from .intelligence_graph_reader import (
    IntelligenceGraphReader,
    IntelligenceGraphData,
)
from .requirement_intelligence_reader import (
    RequirementIntelligenceReader,
    RequirementIntelligenceData,
    RawRequirement,
)
from .semantic_understanding_reader import (
    SemanticUnderstandingReader,
    SemanticUnderstandingData,
    SemanticKeyword,
)
from .knowledge_reader import KnowledgeReader, KnowledgeData
from .size_analyzer import SizeAnalyzer
from .scalability_analyzer import ScalabilityAnalyzer
from .performance_analyzer import PerformanceAnalyzer
from .security_analyzer import SecurityAnalyzer
from .maintainability_analyzer import MaintainabilityAnalyzer
from .architecture_selector import ArchitectureSelector
from .decision_validator import DecisionValidator
from .quality_gate import QualityGate
from .cache_manager import CacheManager
from .report_assembler import ReportAssembler

__all__ = [
    # Engine
    "ArchitectureDecisionEngine",
    # Data model
    "AnalysisResult",
    "RejectedAlternative",
    "ArchitectureDecision",
    "ArchitectureFinding",
    "CacheInfo",
    "ArchitectureProvenance",
    "ModuleSpec",
    "ServiceSpec",
    "ArchitectureDecisionReport",
    # Source-artefact constants
    "SOURCE_NORMALIZED_REQUIREMENTS",
    "SOURCE_INTELLIGENCE_GRAPH",
    "SOURCE_REQUIREMENT_INTELLIGENCE",
    "SOURCE_SEMANTIC_UNDERSTANDING",
    "SOURCE_KNOWLEDGE_BASE",
    "ALL_SOURCES",
    # Severity constants
    "SEVERITY_ERROR",
    "SEVERITY_WARNING",
    "SEVERITY_INFO",
    "ALL_SEVERITIES",
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
    # Architecture pattern constants
    "PATTERN_MONOLITH",
    "PATTERN_LAYERED",
    "PATTERN_MODULAR_MONOLITH",
    "PATTERN_MICROSERVICES",
    "PATTERN_EVENT_DRIVEN",
    "PATTERN_HEXAGONAL",
    "ALL_PATTERNS",
    "PATTERN_BY_SIZE",
    # Layer constants
    "LAYER_PRESENTATION",
    "LAYER_BUSINESS",
    "LAYER_DATA_ACCESS",
    "LAYER_INFRASTRUCTURE",
    "LAYER_INTEGRATION",
    "LAYER_CACHING",
    "LAYER_MESSAGING",
    "ALL_LAYERS",
    # Communication pattern constants
    "COMM_SYNC",
    "COMM_ASYNC",
    "COMM_EVENT",
    "COMM_HYBRID",
    "ALL_COMM_PATTERNS",
    # Error handling strategy constants
    "ERROR_CENTRALIZED",
    "ERROR_DISTRIBUTED",
    "ERROR_LAYER_SPECIFIC",
    "ERROR_RESULT_TYPE",
    "ALL_ERROR_STRATEGIES",
    # Configuration strategy constants
    "CONFIG_STATIC",
    "CONFIG_ENVIRONMENT",
    "CONFIG_FILE_BASED",
    "CONFIG_HYBRID",
    "ALL_CONFIG_STRATEGIES",
    # Dependency structure constants
    "DEP_FLAT",
    "DEP_LAYERED",
    "DEP_HIERARCHICAL",
    "DEP_GRAPH",
    "ALL_DEP_STRUCTURES",
    # Project layout constants
    "LAYOUT_FEATURE_BASED",
    "LAYOUT_LAYER_BASED",
    "LAYOUT_DOMAIN_BASED",
    "LAYOUT_HYBRID",
    "ALL_LAYOUTS",
    # Analysis dimension constants
    "DIMENSION_SIZE",
    "DIMENSION_SCALABILITY",
    "DIMENSION_PERFORMANCE",
    "DIMENSION_SECURITY",
    "DIMENSION_MAINTAINABILITY",
    "ALL_DIMENSIONS",
    # Decision domain constants
    "DECISION_LAYERS",
    "DECISION_MODULES",
    "DECISION_SERVICES",
    "DECISION_DEPENDENCY_STRUCTURE",
    "DECISION_PROJECT_LAYOUT",
    "DECISION_COMMUNICATION",
    "DECISION_ERROR_HANDLING",
    "DECISION_CONFIGURATION",
    "ALL_DECISION_DOMAINS",
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
    # Readers + intermediate data
    "RequirementNormalizationReader",
    "RequirementNormalizationData",
    "NormalizedRequirementView",
    "IntelligenceGraphReader",
    "IntelligenceGraphData",
    "RequirementIntelligenceReader",
    "RequirementIntelligenceData",
    "RawRequirement",
    "SemanticUnderstandingReader",
    "SemanticUnderstandingData",
    "SemanticKeyword",
    "KnowledgeReader",
    "KnowledgeData",
    # Analyzers
    "SizeAnalyzer",
    "ScalabilityAnalyzer",
    "PerformanceAnalyzer",
    "SecurityAnalyzer",
    "MaintainabilityAnalyzer",
    # Architecture selector
    "ArchitectureSelector",
    # Helpers and processors
    "DecisionValidator",
    "QualityGate",
    "CacheManager",
    "ReportAssembler",
]
