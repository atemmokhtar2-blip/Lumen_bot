"""StrategyValidator — Specification 026"""

from __future__ import annotations

import logging
from typing import List

from .report_data import (
    GenerationStage, GenerationItem, StrategyConflict,
    CONFLICT_ORDER, CONFLICT_MISSING_STAGE, CONFLICT_DUPLICATE_ITEM,
    ALL_STAGES, SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
)

_log = logging.getLogger("engine.generation_strategy.strategy_validator")


class StrategyValidator:
    def validate(
        self,
        stages: List[GenerationStage],
        items: List[GenerationItem],
        generation_order: List[str],
    ) -> List[StrategyConflict]:
        conflicts: List[StrategyConflict] = []
        present = {s.stage_id for s in stages}
        for expected in ALL_STAGES:
            if expected not in present:
                conflicts.append(StrategyConflict(
                    conflict_id=f"missing_stage_{expected}",
                    conflict_type=CONFLICT_MISSING_STAGE,
                    severity=SEVERITY_HIGH,
                    message=f"Required stage '{expected}' is missing.",
                    affected_ids=[expected],
                    resolution_hint="Ensure StrategyPlanner emits all canonical stages.",
                ))

        seen = {}
        for it in items:
            if it.item_id in seen:
                conflicts.append(StrategyConflict(
                    conflict_id=f"dup_{it.item_id}",
                    conflict_type=CONFLICT_DUPLICATE_ITEM,
                    severity=SEVERITY_CRITICAL,
                    message=f"Duplicate item_id '{it.item_id}'.",
                    affected_ids=[it.item_id],
                    resolution_hint="Ensure every item_id is unique.",
                ))
            else:
                seen[it.item_id] = True

        # Order: dependency must appear before dependent in generation_order
        pos = {iid: i for i, iid in enumerate(generation_order)}
        for it in items:
            for dep in it.depends_on:
                if dep in pos and it.item_id in pos and pos[dep] > pos[it.item_id]:
                    conflicts.append(StrategyConflict(
                        conflict_id=f"order_{it.item_id}_{dep}",
                        conflict_type=CONFLICT_ORDER,
                        severity=SEVERITY_CRITICAL,
                        message=f"Item '{it.item_id}' is ordered before its dependency '{dep}'.",
                        affected_ids=[it.item_id, dep],
                        resolution_hint="Reorder so dependencies come first.",
                    ))

        _log.info("StrategyValidator found %d conflicts", len(conflicts))
        return conflicts


__all__ = ["StrategyValidator"]
