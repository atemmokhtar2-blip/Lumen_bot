"""
ReadinessChecker — Specification 027

Validates all upstream blueprints, computes category scores and overall readiness.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Tuple

from .report_data import (
    CategoryScore, ValidationIssue, MissingItem,
    CAT_ARCHITECTURE, CAT_STRUCTURE, CAT_DEPENDENCIES, CAT_PLANNING,
    CAT_CONSISTENCY, CAT_RISKS,
    ISSUE_MISSING_BLUEPRINT, ISSUE_NOT_READY_VERDICT, ISSUE_MISSING_ITEM,
    ISSUE_CONFLICT, ISSUE_INCONSISTENCY, ISSUE_RISK,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
    SOURCE_PROJECT_STRUCTURE, SOURCE_MODULE_ARCHITECTURE,
    SOURCE_COMPONENT_ARCHITECTURE, SOURCE_INTERFACE_CONTRACT,
    SOURCE_DATA_FLOW, SOURCE_RESOURCE_DEPENDENCY, SOURCE_GENERATION_STRATEGY,
    SOURCE_EXECUTION_PLAN,
)
from .data_readers import BlueprintSnapshot

_log = logging.getLogger("engine.generation_readiness.readiness_checker")

# Map sources → category
_SOURCE_CATEGORY = {
    SOURCE_MODULE_ARCHITECTURE: CAT_ARCHITECTURE,
    SOURCE_COMPONENT_ARCHITECTURE: CAT_ARCHITECTURE,
    SOURCE_INTERFACE_CONTRACT: CAT_ARCHITECTURE,
    SOURCE_PROJECT_STRUCTURE: CAT_STRUCTURE,
    SOURCE_DATA_FLOW: CAT_STRUCTURE,
    SOURCE_RESOURCE_DEPENDENCY: CAT_DEPENDENCIES,
    SOURCE_GENERATION_STRATEGY: CAT_PLANNING,
    SOURCE_EXECUTION_PLAN: CAT_PLANNING,
}


class ReadinessChecker:
    def check(
        self,
        snapshots: Dict[str, BlueprintSnapshot],
    ) -> Tuple[
        List[CategoryScore],
        float,
        List[ValidationIssue],
        List[MissingItem],
    ]:
        issues: List[ValidationIssue] = []
        missing: List[MissingItem] = []
        category_penalties: Dict[str, float] = {
            CAT_ARCHITECTURE: 0.0,
            CAT_STRUCTURE: 0.0,
            CAT_DEPENDENCIES: 0.0,
            CAT_PLANNING: 0.0,
            CAT_CONSISTENCY: 0.0,
            CAT_RISKS: 0.0,
        }
        category_counts: Dict[str, int] = {c: 0 for c in category_penalties}

        for source, snap in snapshots.items():
            cat = _SOURCE_CATEGORY.get(source, CAT_CONSISTENCY)
            category_counts[cat] = category_counts.get(cat, 0) + 1

            if not snap.available:
                issues.append(ValidationIssue(
                    issue_id=f"missing_{source}",
                    issue_type=ISSUE_MISSING_BLUEPRINT,
                    severity=SEVERITY_CRITICAL,
                    category=cat,
                    source=source,
                    message=f"Required blueprint '{source}' is missing.",
                    resolution_hint="Re-run the upstream engine that produces this blueprint.",
                ))
                missing.append(MissingItem(
                    item_id=source,
                    description=f"Blueprint '{source}' not found in context",
                    expected_source=source,
                    severity=SEVERITY_CRITICAL,
                ))
                category_penalties[cat] = category_penalties.get(cat, 0) + 40.0
                continue

            if snap.is_empty:
                issues.append(ValidationIssue(
                    issue_id=f"empty_{source}",
                    issue_type=ISSUE_MISSING_ITEM,
                    severity=SEVERITY_HIGH,
                    category=cat,
                    source=source,
                    message=f"Blueprint '{source}' is empty.",
                    resolution_hint="Upstream engine produced an empty blueprint.",
                ))
                category_penalties[cat] = category_penalties.get(cat, 0) + 25.0

            verdict = (snap.verdict or "").lower()
            if verdict == VERDICT_NOT_READY:
                issues.append(ValidationIssue(
                    issue_id=f"not_ready_{source}",
                    issue_type=ISSUE_NOT_READY_VERDICT,
                    severity=SEVERITY_CRITICAL,
                    category=cat,
                    source=source,
                    message=f"Blueprint '{source}' has verdict NOT_READY.",
                    resolution_hint="Fix upstream quality-gate failures before proceeding.",
                ))
                category_penalties[cat] = category_penalties.get(cat, 0) + 35.0
            elif verdict == VERDICT_READY_WITH_WARNINGS:
                issues.append(ValidationIssue(
                    issue_id=f"warnings_{source}",
                    issue_type=ISSUE_CONFLICT,
                    severity=SEVERITY_MEDIUM,
                    category=cat,
                    source=source,
                    message=f"Blueprint '{source}' is READY_WITH_WARNINGS.",
                    resolution_hint="Review warnings; they do not block but should be understood.",
                ))
                category_penalties[cat] = category_penalties.get(cat, 0) + 5.0

            if snap.conflict_count > 0:
                issues.append(ValidationIssue(
                    issue_id=f"conflicts_{source}",
                    issue_type=ISSUE_CONFLICT,
                    severity=SEVERITY_HIGH if snap.conflict_count >= 3 else SEVERITY_MEDIUM,
                    category=cat,
                    source=source,
                    message=f"Blueprint '{source}' still carries {snap.conflict_count} conflict(s).",
                    resolution_hint="Resolve remaining conflicts in the upstream engine.",
                ))
                category_penalties[cat] = category_penalties.get(cat, 0) + min(20.0, snap.conflict_count * 5.0)

        # Consistency: if architecture present but strategy missing stages → inconsistency
        strat = snapshots.get(SOURCE_GENERATION_STRATEGY)
        if strat and strat.available and strat.raw:
            stages = strat.raw.get("stages") or []
            if len(stages) < 5:
                issues.append(ValidationIssue(
                    issue_id="inconsistent_stages",
                    issue_type=ISSUE_INCONSISTENCY,
                    severity=SEVERITY_HIGH,
                    category=CAT_CONSISTENCY,
                    source=SOURCE_GENERATION_STRATEGY,
                    message=f"Generation strategy has only {len(stages)} stage(s); expected ≥ 5.",
                    resolution_hint="Re-run Generation Strategy Engine.",
                ))
                category_penalties[CAT_CONSISTENCY] += 15.0

        # Risk category from resource deps
        res = snapshots.get(SOURCE_RESOURCE_DEPENDENCY)
        if res and res.available and res.raw:
            risks = res.raw.get("risks") or []
            high_risks = [r for r in risks if isinstance(r, dict) and r.get("severity") in ("critical", "high")]
            if high_risks:
                issues.append(ValidationIssue(
                    issue_id="high_risks",
                    issue_type=ISSUE_RISK,
                    severity=SEVERITY_HIGH,
                    category=CAT_RISKS,
                    source=SOURCE_RESOURCE_DEPENDENCY,
                    message=f"{len(high_risks)} high/critical risk(s) remain in dependency plan.",
                    resolution_hint="Mitigate or accept risks explicitly before generation.",
                ))
                category_penalties[CAT_RISKS] += min(30.0, len(high_risks) * 10.0)

        # Build category scores (100 - penalty, clamped)
        scores: List[CategoryScore] = []
        weights = {
            CAT_ARCHITECTURE: 1.5,
            CAT_STRUCTURE: 1.2,
            CAT_DEPENDENCIES: 1.3,
            CAT_PLANNING: 1.4,
            CAT_CONSISTENCY: 1.0,
            CAT_RISKS: 1.0,
        }
        total_weight = 0.0
        weighted_sum = 0.0
        for cat in (CAT_ARCHITECTURE, CAT_STRUCTURE, CAT_DEPENDENCIES,
                    CAT_PLANNING, CAT_CONSISTENCY, CAT_RISKS):
            penalty = category_penalties.get(cat, 0.0)
            score = max(0.0, min(100.0, 100.0 - penalty))
            w = weights.get(cat, 1.0)
            scores.append(CategoryScore(
                category=cat, score=round(score, 1), weight=w,
                details=f"penalty={penalty:.1f}",
            ))
            weighted_sum += score * w
            total_weight += w

        overall = round(weighted_sum / total_weight, 1) if total_weight else 0.0
        _log.info("ReadinessChecker overall=%.1f issues=%d missing=%d", overall, len(issues), len(missing))
        return scores, overall, issues, missing


__all__ = ["ReadinessChecker"]
