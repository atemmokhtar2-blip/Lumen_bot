"""Intelligent Function Generation Engine package (Specification 032)."""

from .function_generation_engine import FunctionGenerationEngine
from .report_data import (
    FunctionGenerationReport, MethodSkeleton, ParamSpec, MethodDocSkeleton,
    MethodConflict, MethodFinding, CacheInfo, MethodProvenance,
    ALL_SOURCES, ALL_QUALITY_RULES, ALL_VERDICTS,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)

__all__ = [
    "FunctionGenerationEngine",
    "FunctionGenerationReport",
    "MethodSkeleton",
    "ParamSpec",
    "MethodDocSkeleton",
    "MethodConflict",
    "MethodFinding",
    "CacheInfo",
    "MethodProvenance",
    "ALL_SOURCES",
    "ALL_QUALITY_RULES",
    "ALL_VERDICTS",
    "VERDICT_READY",
    "VERDICT_READY_WITH_WARNINGS",
    "VERDICT_NOT_READY",
]
