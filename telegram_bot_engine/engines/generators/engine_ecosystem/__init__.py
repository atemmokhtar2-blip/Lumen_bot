"""Intelligent Engine Ecosystem & Registry Engine package (Specification 052)."""

from .engine_ecosystem_engine import EngineEcosystemEngine
from .report_data import (
    EngineEcosystemReport, EngineManifest, DependencyEdge, CapabilityEntry,
    CompatibilityResult, EngineHealth, EcosystemFinding, CacheInfo, EcosystemProvenance,
    ALL_SOURCES, ALL_QUALITY_RULES, ALL_VERDICTS, ALL_CAPABILITIES,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)

__all__ = [
    "EngineEcosystemEngine",
    "EngineEcosystemReport",
    "EngineManifest",
    "DependencyEdge",
    "CapabilityEntry",
    "CompatibilityResult",
    "EngineHealth",
    "EcosystemFinding",
    "CacheInfo",
    "EcosystemProvenance",
    "ALL_SOURCES",
    "ALL_QUALITY_RULES",
    "ALL_VERDICTS",
    "ALL_CAPABILITIES",
    "VERDICT_READY",
    "VERDICT_READY_WITH_WARNINGS",
    "VERDICT_NOT_READY",
]
