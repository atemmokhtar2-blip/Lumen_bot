"""
ProductionCertifier — Specification 045 (MAXIMUM CRITICAL)

Aggregates all upstream reports, scores every axis, issues or rejects
the Production Ready Certificate, and controls the Telegram token gate.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from .data_readers import GenericData
from .report_data import (
    AxisScore, CriticalBlocker, Certificate,
    STATUS_PASS, STATUS_FAIL, STATUS_WARN,
    AXIS_ARCHITECTURE, AXIS_SECURITY, AXIS_PERFORMANCE, AXIS_CODE_QUALITY,
    AXIS_RELIABILITY, AXIS_MAINTAINABILITY, AXIS_SCALABILITY, AXIS_TESTING,
    AXIS_INTEGRATION, AXIS_OVERALL,
    MIN_ARCHITECTURE, MIN_SECURITY, MIN_PERFORMANCE, MIN_CODE_QUALITY,
    MIN_RELIABILITY, MIN_MAINTAINABILITY, MIN_SCALABILITY, MIN_TESTING,
    MIN_INTEGRATION, MIN_OVERALL,
    SEVERITY_CRITICAL,
)

_log = logging.getLogger("engine.production_readiness.certifier")

_THRESHOLDS: Dict[str, float] = {
    AXIS_ARCHITECTURE: MIN_ARCHITECTURE,
    AXIS_SECURITY: MIN_SECURITY,
    AXIS_PERFORMANCE: MIN_PERFORMANCE,
    AXIS_CODE_QUALITY: MIN_CODE_QUALITY,
    AXIS_RELIABILITY: MIN_RELIABILITY,
    AXIS_MAINTAINABILITY: MIN_MAINTAINABILITY,
    AXIS_SCALABILITY: MIN_SCALABILITY,
    AXIS_TESTING: MIN_TESTING,
    AXIS_INTEGRATION: MIN_INTEGRATION,
    AXIS_OVERALL: MIN_OVERALL,
}


class ProductionCertifier:
    """Final production-readiness decision engine."""

    def certify(
        self,
        e2e: GenericData,
        unit: GenericData,
        integration: GenericData,
        heal: GenericData,
        runtime: GenericData,
        static: GenericData,
        architecture: GenericData,
        security: GenericData,
        performance: GenericData,
        refactoring: GenericData,
    ) -> Tuple[
        List[AxisScore],
        List[CriticalBlocker],
        Certificate,
        float,  # overall
        bool,   # certified
    ]:
        scores: Dict[str, float] = {}
        blockers: List[CriticalBlocker] = []

        # Architecture
        scores[AXIS_ARCHITECTURE] = self._score_from_report(
            architecture, positive_keys=("compliance_score", "score"),
            default=88.0, penalty_keys=("open_critical_count", "violation_count"),
        )
        self._collect_blockers(architecture, "architecture_compliance", blockers)

        # Security
        scores[AXIS_SECURITY] = self._score_from_report(
            security, positive_keys=("security_score", "score"),
            default=90.0, penalty_keys=("open_critical_count", "critical_count"),
        )
        self._collect_blockers(security, "security_review", blockers)

        # Performance
        scores[AXIS_PERFORMANCE] = self._score_from_report(
            performance, positive_keys=("performance_score", "score"),
            default=85.0, penalty_keys=("bottleneck_count", "critical_count"),
        )
        self._collect_blockers(performance, "performance_optimization", blockers)

        # Code quality (static + refactoring)
        static_s = self._score_from_report(
            static, positive_keys=("quality_score", "score"),
            default=82.0, penalty_keys=("open_critical_count", "issue_count"),
        )
        ref_s = self._score_from_report(
            refactoring, positive_keys=("average_maintainability_after", "score"),
            default=80.0, penalty_keys=("smell_count",),
        )
        scores[AXIS_CODE_QUALITY] = round((static_s + ref_s) / 2.0, 1)
        self._collect_blockers(static, "static_analysis", blockers)

        # Reliability (runtime + self-healing)
        runtime_s = self._score_from_report(
            runtime, positive_keys=("score", "overall"),
            nested="score", default=85.0,
            penalty_keys=("crash_count", "failed_event_count"),
        )
        # score might be nested dict
        if runtime.available and runtime.raw and isinstance(runtime.raw.get("score"), dict):
            runtime_s = float(runtime.raw["score"].get("overall") or runtime_s)
        heal_s = self._score_from_report(
            heal, positive_keys=("average_confidence",),
            default=80.0, penalty_keys=("failed_count",),
            confidence_scale=True,
        )
        scores[AXIS_RELIABILITY] = round((runtime_s + heal_s) / 2.0, 1)
        self._collect_blockers(runtime, "runtime_simulation", blockers)
        self._collect_blockers(heal, "self_healing", blockers)

        # Maintainability from refactoring maintainability
        scores[AXIS_MAINTAINABILITY] = self._score_from_report(
            refactoring, positive_keys=("average_maintainability_after",),
            default=78.0, penalty_keys=("smell_count",),
        )

        # Scalability from performance + e2e load
        perf_s = scores[AXIS_PERFORMANCE]
        e2e_load = 85.0
        if e2e.available and e2e.raw:
            loads = e2e.raw.get("load_results") or []
            if loads:
                rates = [float(l.get("success_rate") or 0) for l in loads if isinstance(l, dict)]
                if rates:
                    e2e_load = sum(rates) / len(rates)
            elif e2e.raw.get("success_rate") is not None:
                e2e_load = float(e2e.raw["success_rate"])
        scores[AXIS_SCALABILITY] = round((perf_s * 0.4 + e2e_load * 0.6), 1)

        # Testing
        scores[AXIS_TESTING] = self._score_from_report(
            unit, positive_keys=("coverage", "overall"),
            nested="coverage", default=85.0,
            penalty_keys=("failure_count", "gap_count"),
        )
        if unit.available and unit.raw and isinstance(unit.raw.get("coverage"), dict):
            scores[AXIS_TESTING] = float(
                unit.raw["coverage"].get("overall") or scores[AXIS_TESTING]
            )
        self._collect_blockers(unit, "unit_test_generation", blockers)

        # Integration
        scores[AXIS_INTEGRATION] = self._score_from_report(
            integration, positive_keys=("score", "overall"),
            nested="score", default=85.0,
            penalty_keys=("failed_count",),
        )
        if integration.available and integration.raw and isinstance(
            integration.raw.get("score"), dict
        ):
            scores[AXIS_INTEGRATION] = float(
                integration.raw["score"].get("overall") or scores[AXIS_INTEGRATION]
            )
        self._collect_blockers(integration, "integration_verification", blockers)

        # E2E contributes to reliability/testing pressure
        self._collect_blockers(e2e, "e2e_scenario_testing", blockers)
        if e2e.available and e2e.raw:
            sr = float(e2e.raw.get("success_rate") or 100)
            if sr < 95:
                scores[AXIS_RELIABILITY] = min(scores[AXIS_RELIABILITY], sr)
            ux = e2e.raw.get("ux") or {}
            if isinstance(ux, dict) and ux.get("overall") is not None:
                scores[AXIS_CODE_QUALITY] = round(
                    (scores[AXIS_CODE_QUALITY] + float(ux["overall"])) / 2.0, 1
                )

        # Overall weighted
        weights = {
            AXIS_ARCHITECTURE: 0.12,
            AXIS_SECURITY: 0.15,
            AXIS_PERFORMANCE: 0.10,
            AXIS_CODE_QUALITY: 0.10,
            AXIS_RELIABILITY: 0.13,
            AXIS_MAINTAINABILITY: 0.08,
            AXIS_SCALABILITY: 0.08,
            AXIS_TESTING: 0.12,
            AXIS_INTEGRATION: 0.12,
        }
        overall = sum(scores[a] * w for a, w in weights.items())
        scores[AXIS_OVERALL] = round(overall, 1)

        # Build AxisScore list
        axes: List[AxisScore] = []
        engine_map = {
            AXIS_ARCHITECTURE: "architecture_compliance",
            AXIS_SECURITY: "security_review",
            AXIS_PERFORMANCE: "performance_optimization",
            AXIS_CODE_QUALITY: "static_analysis/code_refactoring",
            AXIS_RELIABILITY: "runtime_simulation/self_healing",
            AXIS_MAINTAINABILITY: "code_refactoring",
            AXIS_SCALABILITY: "performance_optimization/e2e",
            AXIS_TESTING: "unit_test_generation/e2e",
            AXIS_INTEGRATION: "integration_verification",
            AXIS_OVERALL: "production_readiness",
        }
        all_pass = True
        for axis, score in scores.items():
            thr = _THRESHOLDS.get(axis, 80.0)
            if score >= thr:
                status = STATUS_PASS
                reason = ""
                hint = ""
            else:
                status = STATUS_FAIL
                all_pass = False
                reason = f"{axis} score {score:.1f} below threshold {thr:.1f}"
                hint = f"Improve {axis} via {engine_map.get(axis, 'upstream')} engine"
            axes.append(AxisScore(
                axis=axis,
                score=score,
                threshold=thr,
                status=status,
                responsible_engine=engine_map.get(axis, ""),
                rejection_reason=reason,
                repair_hint=hint,
            ))

        # Certificate decision: all axes pass AND no critical blockers
        critical_blockers = [b for b in blockers if b.severity == SEVERITY_CRITICAL]
        certified = all_pass and len(critical_blockers) == 0

        if certified:
            cert = Certificate(
                certificate_id=str(uuid.uuid4()),
                issued=True,
                issued_at=datetime.now(timezone.utc).isoformat(),
                overall_score=scores[AXIS_OVERALL],
                token_gate_open=True,
                summary=(
                    f"Production Ready Certificate issued. "
                    f"Overall score {scores[AXIS_OVERALL]:.1f}. "
                    f"Telegram token gate OPEN."
                ),
            )
        else:
            failed_axes = [a.axis for a in axes if a.status == STATUS_FAIL]
            cert = Certificate(
                certificate_id="",
                issued=False,
                issued_at="",
                overall_score=scores[AXIS_OVERALL],
                token_gate_open=False,
                summary=(
                    f"Production Ready Certificate REJECTED. "
                    f"Failed axes: {', '.join(failed_axes) or 'none'}; "
                    f"critical blockers: {len(critical_blockers)}. "
                    f"Telegram token gate CLOSED."
                ),
            )

        _log.info(
            "ProductionCertifier: overall=%.1f certified=%s blockers=%d token_gate=%s",
            scores[AXIS_OVERALL], certified, len(critical_blockers),
            cert.token_gate_open,
        )
        return axes, blockers, cert, scores[AXIS_OVERALL], certified

    def self_verify(
        self, axes: List[AxisScore], blockers: List[CriticalBlocker], certified: bool
    ) -> bool:
        failed = [a for a in axes if a.status == STATUS_FAIL]
        crit = [b for b in blockers if b.severity == SEVERITY_CRITICAL]
        if certified:
            return len(failed) == 0 and len(crit) == 0
        # Rejection is valid self-state
        return True

    def _score_from_report(
        self,
        data: GenericData,
        positive_keys: Tuple[str, ...] = (),
        default: float = 80.0,
        penalty_keys: Tuple[str, ...] = (),
        nested: str = "",
        confidence_scale: bool = False,
    ) -> float:
        if not data.available or not data.raw:
            return default * 0.9  # slight penalty for missing report
        raw = data.raw
        score = default
        if nested and isinstance(raw.get(nested), dict):
            for k in positive_keys:
                if raw[nested].get(k) is not None:
                    score = float(raw[nested][k])
                    break
        else:
            for k in positive_keys:
                if raw.get(k) is not None:
                    val = float(raw[k])
                    if confidence_scale and val <= 1.0:
                        val *= 100.0
                    score = val
                    break
        penalty = 0.0
        for k in penalty_keys:
            penalty += float(raw.get(k) or 0) * 3.0
        # Critical items in list
        for it in data.items or []:
            if str(it.get("severity") or "").lower() == "critical":
                st = str(it.get("status") or "open").lower()
                if st in ("open", "failed", "detected", ""):
                    penalty += 8.0
            if str(it.get("status") or "").lower() == "failed":
                penalty += 4.0
        return round(max(0.0, min(100.0, score - penalty)), 1)

    def _collect_blockers(
        self, data: GenericData, engine: str, blockers: List[CriticalBlocker]
    ) -> None:
        if not data.available:
            return
        for it in data.items or []:
            sev = str(it.get("severity") or "").lower()
            st = str(it.get("status") or "open").lower()
            if sev == "critical" and st in ("open", "failed", "detected", ""):
                msg = str(
                    it.get("message") or it.get("title") or it.get("description") or "critical"
                )
                blockers.append(CriticalBlocker(
                    blocker_id=str(uuid.uuid4())[:8],
                    source_engine=engine,
                    severity=SEVERITY_CRITICAL,
                    message=msg[:300],
                    repair_hint=f"Resolve via {engine}",
                ))
        if data.raw:
            if int(data.raw.get("open_critical_count") or 0) > 0 and not any(
                b.source_engine == engine for b in blockers
            ):
                blockers.append(CriticalBlocker(
                    blocker_id=str(uuid.uuid4())[:8],
                    source_engine=engine,
                    severity=SEVERITY_CRITICAL,
                    message=f"{data.raw.get('open_critical_count')} open critical issue(s)",
                    repair_hint=f"Resolve criticals in {engine}",
                ))
            if int(data.raw.get("crash_count") or 0) > 0:
                blockers.append(CriticalBlocker(
                    blocker_id=str(uuid.uuid4())[:8],
                    source_engine=engine,
                    severity=SEVERITY_CRITICAL,
                    message=f"crash_count={data.raw.get('crash_count')}",
                    repair_hint=f"Eliminate crashes reported by {engine}",
                ))


__all__ = ["ProductionCertifier"]
