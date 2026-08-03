"""Intelligent Code Refactoring Engine package (Specification 038)."""

from .code_refactoring_engine import CodeRefactoringEngine
from .report_data import (
    CodeRefactoringReport, RefactoredUnit, CodeSmell, RefactoringAction,
    MaintainabilityScore, ExtensibilityPoint, RefactoringFinding,
    CacheInfo, RefactoringProvenance,
    ALL_SOURCES, ALL_QUALITY_RULES, ALL_VERDICTS, MIN_MAINTAINABILITY,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)

__all__ = [
    "CodeRefactoringEngine",
    "CodeRefactoringReport",
    "RefactoredUnit",
    "CodeSmell",
    "RefactoringAction",
    "MaintainabilityScore",
    "ExtensibilityPoint",
    "RefactoringFinding",
    "CacheInfo",
    "RefactoringProvenance",
    "ALL_SOURCES",
    "ALL_QUALITY_RULES",
    "ALL_VERDICTS",
    "MIN_MAINTAINABILITY",
    "VERDICT_READY",
    "VERDICT_READY_WITH_WARNINGS",
    "VERDICT_NOT_READY",
]
