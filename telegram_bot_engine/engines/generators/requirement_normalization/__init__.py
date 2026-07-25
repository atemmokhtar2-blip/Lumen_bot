"""
Requirement Normalization Engine package (Specification 014).

This package contains the requirement normalization engine — the engine
that transforms **all user requirements** into a unified, canonical
model that every downstream engine can understand.  It does not write
code, create files, choose libraries, or make build decisions.  Its
sole function is to produce the *Normalization Report* — a structured,
validated report that captures the canonical names, the terminology
mappings, the deduplicated requirements, the links between
requirements and features/components/priorities/dependencies, the
findings, the cache information, the provenance, and the confidence.

Public surface
--------------
* :class:`RequirementNormalizationEngine` — the engine itself.
* :class:`NormalizationReport` and all of its sub-dataclasses
  (:class:`CanonicalName`, :class:`TerminologyMapping`,
  :class:`RequirementLink`, :class:`DuplicateRecord`,
  :class:`ConflictRecord`, :class:`NormalizationFinding`,
  :class:`CacheInfo`, :class:`NormalizationProvenance`,
  :class:`NormalizedRequirement`).
* :class:`RequestReader`, :class:`RequirementIntelligenceReader`,
  :class:`SemanticUnderstandingReader`, :class:`ContextReader`,
  :class:`KnowledgeReader` — the five data-source readers.
* :class:`NameNormalizer`, :class:`TerminologyNormalizer`,
  :class:`DeduplicationRemover`, :class:`ConsistencyValidator`,
  :class:`RequirementLinker`, :class:`CacheManager`,
  :class:`QualityGate`, :class:`ReportAssembler` — the helpers and
  processors.
* :class:`RequestData`, :class:`RequirementIntelligenceData`,
  :class:`SemanticUnderstandingData`, :class:`ContextData`,
  :class:`KnowledgeData` — the intermediate data containers produced
  by the readers.
* :class:`RawRequirement`, :class:`SemanticKeyword`,
  :class:`SemanticRequirement` — the sub-dataclasses used inside the
  intermediate data containers.
* Source-artefact, severity, status, priority, category, link-kind,
  cache-status, and confidence-level constants.
"""

from __future__ import annotations

from .requirement_normalization_engine import RequirementNormalizationEngine
from .report_data import (
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
)
from .request_reader import RequestReader, RequestData
from .requirement_intelligence_reader import (
    RequirementIntelligenceReader,
    RequirementIntelligenceData,
    RawRequirement,
)
from .semantic_understanding_reader import (
    SemanticUnderstandingReader,
    SemanticUnderstandingData,
    SemanticKeyword,
    SemanticRequirement,
)
from .context_reader import ContextReader, ContextData
from .knowledge_reader import KnowledgeReader, KnowledgeData
from .name_normalizer import NameNormalizer
from .terminology_normalizer import TerminologyNormalizer
from .deduplication_remover import DeduplicationRemover
from .consistency_validator import ConsistencyValidator
from .requirement_linker import RequirementLinker
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .report_assembler import ReportAssembler

__all__ = [
    # Engine
    "RequirementNormalizationEngine",
    # Data model
    "CanonicalName",
    "TerminologyMapping",
    "RequirementLink",
    "DuplicateRecord",
    "ConflictRecord",
    "NormalizationFinding",
    "CacheInfo",
    "NormalizationProvenance",
    "NormalizedRequirement",
    "NormalizationReport",
    # Source-artefact constants
    "SOURCE_USER_REQUEST",
    "SOURCE_REQUIREMENT_INTELLIGENCE",
    "SOURCE_SEMANTIC_UNDERSTANDING",
    "SOURCE_PROJECT_CONTEXT",
    "SOURCE_KNOWLEDGE_BASE",
    "ALL_SOURCES",
    # Severity constants
    "SEVERITY_ERROR",
    "SEVERITY_WARNING",
    "SEVERITY_INFO",
    "ALL_SEVERITIES",
    # Status constants
    "STATUS_ACTIVE",
    "STATUS_DEPRECATED",
    "STATUS_MERGED",
    "STATUS_REMOVED",
    "ALL_STATUSES",
    # Priority constants
    "PRIORITY_CRITICAL",
    "PRIORITY_HIGH",
    "PRIORITY_MEDIUM",
    "PRIORITY_LOW",
    "ALL_PRIORITIES",
    "PRIORITY_WEIGHTS",
    # Category constants
    "CATEGORY_FUNCTIONAL",
    "CATEGORY_NON_FUNCTIONAL",
    "CATEGORY_TECHNICAL",
    "CATEGORY_CONSTRAINT",
    "CATEGORY_INTERFACE",
    "CATEGORY_SECURITY",
    "CATEGORY_PERFORMANCE",
    "CATEGORY_USABILITY",
    "CATEGORY_DEPLOYMENT",
    "ALL_CATEGORIES",
    # Link kind constants
    "LINK_KIND_FEATURE",
    "LINK_KIND_COMPONENT",
    "LINK_KIND_DEPENDENCY",
    "LINK_KIND_EXPECTED_OUTPUT",
    "ALL_LINK_KINDS",
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
    "RequestReader",
    "RequestData",
    "RequirementIntelligenceReader",
    "RequirementIntelligenceData",
    "RawRequirement",
    "SemanticUnderstandingReader",
    "SemanticUnderstandingData",
    "SemanticKeyword",
    "SemanticRequirement",
    "ContextReader",
    "ContextData",
    "KnowledgeReader",
    "KnowledgeData",
    # Helpers and processors
    "NameNormalizer",
    "TerminologyNormalizer",
    "DeduplicationRemover",
    "ConsistencyValidator",
    "RequirementLinker",
    "CacheManager",
    "QualityGate",
    "ReportAssembler",
]
