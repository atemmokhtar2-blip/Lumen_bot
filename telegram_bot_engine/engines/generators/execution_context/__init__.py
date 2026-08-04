"""Intelligent Execution Context Engine package (Specification 054)."""

from .execution_context_engine import ExecutionContextEngine
from .report_data import (
    ExecutionContextReport, ContextVersion, ContextLock, ContextChange,
    ValidationIssue, ContextFinding, CacheInfo, ContextProvenance,
    ALL_SOURCES, ALL_QUALITY_RULES, ALL_VERDICTS,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)

__all__ = [
    "ExecutionContextEngine",
    "ExecutionContextReport",
    "ContextVersion",
    "ContextLock",
    "ContextChange",
    "ValidationIssue",
    "ContextFinding",
    "CacheInfo",
    "ContextProvenance",
    "ALL_SOURCES",
    "ALL_QUALITY_RULES",
    "ALL_VERDICTS",
    "VERDICT_READY",
    "VERDICT_READY_WITH_WARNINGS",
    "VERDICT_NOT_READY",
]
