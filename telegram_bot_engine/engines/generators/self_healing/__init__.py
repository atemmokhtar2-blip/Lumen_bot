"""Intelligent Self-Healing Engine package (Specification 041)."""

from .self_healing_engine import SelfHealingEngine
from .report_data import (
    SelfHealingReport, IssueRecord, RepairPlan, RepairAttempt,
    ValidationCycleResult, HealingFinding, CacheInfo, HealingProvenance,
    ALL_SOURCES, ALL_QUALITY_RULES, ALL_VERDICTS, MIN_REPAIR_CONFIDENCE,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)

__all__ = [
    "SelfHealingEngine",
    "SelfHealingReport",
    "IssueRecord",
    "RepairPlan",
    "RepairAttempt",
    "ValidationCycleResult",
    "HealingFinding",
    "CacheInfo",
    "HealingProvenance",
    "ALL_SOURCES",
    "ALL_QUALITY_RULES",
    "ALL_VERDICTS",
    "MIN_REPAIR_CONFIDENCE",
    "VERDICT_READY",
    "VERDICT_READY_WITH_WARNINGS",
    "VERDICT_NOT_READY",
]
