"""Intelligent Class Generation Engine package (Specification 031)."""

from .class_generation_engine import ClassGenerationEngine
from .report_data import (
    ClassGenerationReport, ClassSkeleton, MethodSignature, PropertySpec,
    ClassDocSkeleton, ClassConflict, ClassFinding, CacheInfo, ClassProvenance,
    ALL_SOURCES, ALL_CLASS_KINDS, ALL_QUALITY_RULES, ALL_VERDICTS,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)

__all__ = [
    "ClassGenerationEngine",
    "ClassGenerationReport",
    "ClassSkeleton",
    "MethodSignature",
    "PropertySpec",
    "ClassDocSkeleton",
    "ClassConflict",
    "ClassFinding",
    "CacheInfo",
    "ClassProvenance",
    "ALL_SOURCES",
    "ALL_CLASS_KINDS",
    "ALL_QUALITY_RULES",
    "ALL_VERDICTS",
    "VERDICT_READY",
    "VERDICT_READY_WITH_WARNINGS",
    "VERDICT_NOT_READY",
]
