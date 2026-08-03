"""Intelligent Integration Verification Engine package (Specification 042)."""

from .integration_verification_engine import IntegrationVerificationEngine
from .report_data import (
    IntegrationVerificationReport, IntegrationCheck, CompatibilityItem,
    DependencyLink, IntegrationScore, IntegrationFinding, CacheInfo,
    IntegrationProvenance,
    ALL_SOURCES, ALL_QUALITY_RULES, ALL_VERDICTS, MIN_INTEGRATION_SCORE,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)

__all__ = [
    "IntegrationVerificationEngine",
    "IntegrationVerificationReport",
    "IntegrationCheck",
    "CompatibilityItem",
    "DependencyLink",
    "IntegrationScore",
    "IntegrationFinding",
    "CacheInfo",
    "IntegrationProvenance",
    "ALL_SOURCES",
    "ALL_QUALITY_RULES",
    "ALL_VERDICTS",
    "MIN_INTEGRATION_SCORE",
    "VERDICT_READY",
    "VERDICT_READY_WITH_WARNINGS",
    "VERDICT_NOT_READY",
]
