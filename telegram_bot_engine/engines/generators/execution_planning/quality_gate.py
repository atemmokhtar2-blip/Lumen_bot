"""
QualityGate — Specification 019

Validates the finished Execution Plan against the mandatory quality
rules.  A plan that fails any critical rule receives the verdict
NOT_READY and blocks the pipeline from proceeding.
"""

from __future__ import annotations

import logging
from typing import List, Tuple

from .report_data import (
    ExecutionPlan,
    ExecutionFinding,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    SEVERITY_LOW,
    RULE_NO_CRITICAL_CONFLICTS,
    RULE_ALL_PHASES_PRESENT,
    RULE_ALL_TASKS_ORDERED,
    RULE_NO_CIRCULAR_DEPENDENCIES,
    RULE_NO_MISSING_DEPENDENCIES,
    RULE_PLAN_COMPLETE,
    RULE_SUFFICIENT_CONFIDENCE,
    ALL_QUALITY_RULES,
    ALL_PHASES,
    CONFLICT_CIRCULAR_DEPENDENCY,
    CONFLICT_MISSING_DEPENDENCY,
    CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_READY,
    VERDICT_READY_WITH_WARNINGS,
    VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.execution_planning.quality_gate")


class QualityGate:
    """Enforces the quality rules defined by Specification 019."""

    def __init__(self) -> None:
        self._findings: List[ExecutionFinding] = []

    def validate(
        self,
        plan: ExecutionPlan,
    ) -> Tuple[List[ExecutionFinding], bool, str]:
        """Validate the plan.

        Returns:
            (findings, passed, verdict)
            where ``passed`` is True only when every critical rule succeeds
            and ``verdict`` is one of the VERDICT_* constants.
        """
        self._findings = []
        critical_failed = False
        warning_count = 0

        if plan.is_empty:
            self._findings.append(ExecutionFinding(
                severity=SEVERITY_CRITICAL,
                code="empty_plan",
                message="The Execution Plan is empty. No planning has been performed.",
                affected="plan",
                resolution_hint="Ensure the Execution Planning Engine received sufficient upstream data.",
                category="quality",
            ))
            return self._findings, False, VERDICT_NOT_READY

        for rule in ALL_QUALITY_RULES:
            ok = self._check_rule(rule, plan)
            if not ok:
                # Critical rules force NOT_READY.
                if rule in (
                    RULE_NO_CRITICAL_CONFLICTS,
                    RULE_NO_CIRCULAR_DEPENDENCIES,
                    RULE_NO_MISSING_DEPENDENCIES,
                    RULE_PLAN_COMPLETE,
                ):
                    critical_failed = True
                else:
                    warning_count += 1

        if critical_failed:
            verdict = VERDICT_NOT_READY
            passed = False
        elif warning_count > 0:
            verdict = VERDICT_READY_WITH_WARNINGS
            passed = True
        else:
            verdict = VERDICT_READY
            passed = True

        _log.info(
            "QualityGate result: passed=%s verdict=%s findings=%d",
            passed, verdict, len(self._findings),
        )
        return self._findings, passed, verdict

    @property
    def findings(self) -> List[ExecutionFinding]:
        return self._findings

    # ------------------------------------------------------------------ #
    # Individual rule checkers
    # ------------------------------------------------------------------ #

    def _check_rule(self, rule: str, plan: ExecutionPlan) -> bool:
        if rule == RULE_NO_CRITICAL_CONFLICTS:
            return self._rule_no_critical_conflicts(plan)
        if rule == RULE_ALL_PHASES_PRESENT:
            return self._rule_all_phases_present(plan)
        if rule == RULE_ALL_TASKS_ORDERED:
            return self._rule_all_tasks_ordered(plan)
        if rule == RULE_NO_CIRCULAR_DEPENDENCIES:
            return self._rule_no_circular(plan)
        if rule == RULE_NO_MISSING_DEPENDENCIES:
            return self._rule_no_missing_deps(plan)
        if rule == RULE_PLAN_COMPLETE:
            return self._rule_plan_complete(plan)
        if rule == RULE_SUFFICIENT_CONFIDENCE:
            return self._rule_sufficient_confidence(plan)
        return True

    def _rule_no_critical_conflicts(self, plan: ExecutionPlan) -> bool:
        criticals = [c for c in plan.conflicts if c.severity == SEVERITY_CRITICAL]
        if criticals:
            self._findings.append(ExecutionFinding(
                severity=SEVERITY_CRITICAL,
                code=RULE_NO_CRITICAL_CONFLICTS,
                message=f"Plan contains {len(criticals)} critical conflict(s).",
                affected="conflicts",
                resolution_hint="Resolve all critical conflicts before proceeding.",
                category="conflict",
            ))
            return False
        return True

    def _rule_all_phases_present(self, plan: ExecutionPlan) -> bool:
        present = {p.phase_id for p in plan.phases}
        missing = [p for p in ALL_PHASES if p not in present]
        if missing:
            self._findings.append(ExecutionFinding(
                severity=SEVERITY_HIGH,
                code=RULE_ALL_PHASES_PRESENT,
                message=f"Missing phases: {', '.join(missing)}",
                affected="phases",
                resolution_hint="All canonical phases must be present.",
                category="quality",
            ))
            return False
        return True

    def _rule_all_tasks_ordered(self, plan: ExecutionPlan) -> bool:
        if not plan.execution_order and plan.tasks:
            self._findings.append(ExecutionFinding(
                severity=SEVERITY_HIGH,
                code=RULE_ALL_TASKS_ORDERED,
                message="Execution order is empty while tasks exist.",
                affected="execution_order",
                resolution_hint="Produce a total order of all tasks.",
                category="ordering",
            ))
            return False
        ordered_set = set(plan.execution_order)
        task_ids = {t.task_id for t in plan.tasks}
        missing = task_ids - ordered_set
        if missing:
            self._findings.append(ExecutionFinding(
                severity=SEVERITY_MEDIUM,
                code=RULE_ALL_TASKS_ORDERED,
                message=f"{len(missing)} task(s) missing from execution order.",
                affected="execution_order",
                resolution_hint="Include every task in the global execution order.",
                category="ordering",
            ))
            return False
        return True

    def _rule_no_circular(self, plan: ExecutionPlan) -> bool:
        circular = [
            c for c in plan.conflicts
            if c.conflict_type == CONFLICT_CIRCULAR_DEPENDENCY
        ]
        if circular:
            self._findings.append(ExecutionFinding(
                severity=SEVERITY_CRITICAL,
                code=RULE_NO_CIRCULAR_DEPENDENCIES,
                message=f"{len(circular)} circular dependency cycle(s) detected.",
                affected="dependencies",
                resolution_hint="Break all cycles before the plan can be accepted.",
                category="dependency",
            ))
            return False
        return True

    def _rule_no_missing_deps(self, plan: ExecutionPlan) -> bool:
        missing = [
            c for c in plan.conflicts
            if c.conflict_type == CONFLICT_MISSING_DEPENDENCY
        ]
        if missing:
            self._findings.append(ExecutionFinding(
                severity=SEVERITY_CRITICAL,
                code=RULE_NO_MISSING_DEPENDENCIES,
                message=f"{len(missing)} missing dependency reference(s).",
                affected="dependencies",
                resolution_hint="Remove or satisfy every missing dependency.",
                category="dependency",
            ))
            return False
        return True

    def _rule_plan_complete(self, plan: ExecutionPlan) -> bool:
        if not plan.phases or not plan.tasks:
            self._findings.append(ExecutionFinding(
                severity=SEVERITY_CRITICAL,
                code=RULE_PLAN_COMPLETE,
                message="Plan is incomplete (no phases or no tasks).",
                affected="plan",
                resolution_hint="Ensure PhasePlanner and task seeding ran successfully.",
                category="quality",
            ))
            return False
        return True

    def _rule_sufficient_confidence(self, plan: ExecutionPlan) -> bool:
        conf = plan.provenance.confidence
        if conf < CONFIDENCE_MEDIUM_THRESHOLD:
            self._findings.append(ExecutionFinding(
                severity=SEVERITY_MEDIUM,
                code=RULE_SUFFICIENT_CONFIDENCE,
                message=(
                    f"Confidence {conf:.2f} is below the medium threshold "
                    f"({CONFIDENCE_MEDIUM_THRESHOLD})."
                ),
                affected="provenance",
                resolution_hint="Provide more upstream artefacts to raise confidence.",
                category="quality",
            ))
            return False
        return True


__all__ = ["QualityGate"]
