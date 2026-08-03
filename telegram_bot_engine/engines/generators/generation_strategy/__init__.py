"""Generation Strategy Engine package (Specification 026)."""

from .generation_strategy_engine import GenerationStrategyEngine
from .report_data import (
    GenerationStrategyBlueprint, GenerationStage, GenerationItem,
    GenerationRule, RollbackPoint, OptimizationStep,
    StrategyConflict, StrategyFinding, CacheInfo, StrategyProvenance,
    ALL_SOURCES, ALL_STAGES, ALL_QUALITY_RULES, ALL_VERDICTS,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)

__all__ = [
    "GenerationStrategyEngine",
    "GenerationStrategyBlueprint",
    "GenerationStage",
    "GenerationItem",
    "GenerationRule",
    "RollbackPoint",
    "OptimizationStep",
    "StrategyConflict",
    "StrategyFinding",
    "CacheInfo",
    "StrategyProvenance",
    "ALL_SOURCES",
    "ALL_STAGES",
    "ALL_QUALITY_RULES",
    "ALL_VERDICTS",
    "VERDICT_READY",
    "VERDICT_READY_WITH_WARNINGS",
    "VERDICT_NOT_READY",
]
