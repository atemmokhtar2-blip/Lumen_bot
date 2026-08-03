"""Intelligent Unit Test Generation Engine package (Specification 043)."""

from .unit_test_generation_engine import UnitTestGenerationEngine
from .report_data import (
    UnitTestGenerationReport, GeneratedTest, TestCase, CoverageGap,
    FailureRecord, CoverageScore, UnitTestFinding, CacheInfo, UnitTestProvenance,
    ALL_SOURCES, ALL_QUALITY_RULES, ALL_VERDICTS, MIN_OVERALL_COVERAGE,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)

__all__ = [
    "UnitTestGenerationEngine",
    "UnitTestGenerationReport",
    "GeneratedTest",
    "TestCase",
    "CoverageGap",
    "FailureRecord",
    "CoverageScore",
    "UnitTestFinding",
    "CacheInfo",
    "UnitTestProvenance",
    "ALL_SOURCES",
    "ALL_QUALITY_RULES",
    "ALL_VERDICTS",
    "MIN_OVERALL_COVERAGE",
    "VERDICT_READY",
    "VERDICT_READY_WITH_WARNINGS",
    "VERDICT_NOT_READY",
]
