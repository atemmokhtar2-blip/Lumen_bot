"""
CodeRefactoringEngine — Specification 038 (ULTRA CRITICAL)

Refactors generated code for better design and maintainability
without changing behaviour, architecture, interfaces or contracts.
"""

from __future__ import annotations

import hashlib
import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    ArchitectureComplianceReader, PerformanceReader, SecurityReader,
    CodeOptimizationReader, BusinessLogicReader, ProjectContextReader,
)
from .report_data import (
    CodeRefactoringReport, ALL_SOURCES,
    SOURCE_ARCHITECTURE_COMPLIANCE, SOURCE_PERFORMANCE, SOURCE_SECURITY,
    SOURCE_CODE_OPTIMIZATION, SOURCE_BUSINESS_LOGIC, SOURCE_PROJECT_CONTEXT,
)
from .refactorer import Refactorer
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.code_refactoring")


class CodeRefactoringEngine(BaseEngine):
    """Specification 038 — Intelligent Code Refactoring Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="code_refactoring",
            version="1.0.0",
            description=(
                "Detects code smells and applies safe refactorings "
                "(extract method/class, rename, flatten nesting) without "
                "changing behaviour or breaking architecture."
            ),
            tags=["refactoring", "maintainability", "code-smells", "clean-code"],
            metadata={"specification": "038", "priority": "ULTRA_CRITICAL"},
        )
        self._arch_reader = ArchitectureComplianceReader()
        self._perf_reader = PerformanceReader()
        self._sec_reader = SecurityReader()
        self._opt_reader = CodeOptimizationReader()
        self._bl_reader = BusinessLogicReader()
        self._ctx_reader = ProjectContextReader()
        self._refactorer = Refactorer()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("CodeRefactoringEngine starting (Spec 038)")

            arch_data = self._arch_reader.read(context)
            perf_data = self._perf_reader.read(context)
            sec_data = self._sec_reader.read(context)
            opt_data = self._opt_reader.read(context)
            bl_data = self._bl_reader.read(context)
            ctx_data = self._ctx_reader.read(context)

            sources_used = []
            sources_missing = []
            for key, data in (
                (SOURCE_ARCHITECTURE_COMPLIANCE, arch_data),
                (SOURCE_PERFORMANCE, perf_data),
                (SOURCE_SECURITY, sec_data),
                (SOURCE_CODE_OPTIMIZATION, opt_data),
                (SOURCE_BUSINESS_LOGIC, bl_data),
                (SOURCE_PROJECT_CONTEXT, ctx_data),
            ):
                if data.available:
                    sources_used.append(key)
                else:
                    sources_missing.append(key)

            primary = perf_data if perf_data.available else (
                sec_data if sec_data.available else bl_data
            )
            cache_payload = ""
            if primary.available and primary.items:
                cache_payload = str(sorted(
                    (
                        str(b.get("unit_id") or b.get("method_id") or ""),
                        str(
                            b.get("optimized_code")
                            or b.get("secured_code")
                            or b.get("source_code")
                            or ""
                        )[:80],
                    )
                    for b in primary.items
                ))
            cache_key = (
                hashlib.sha256(cache_payload.encode("utf-8")).hexdigest()[:32]
                if cache_payload else "empty"
            )

            cached = self._cache.get(cache_key)
            if cached is not None:
                try:
                    report = CodeRefactoringReport(**{
                        k: v for k, v in cached.items()
                        if k in CodeRefactoringReport.__dataclass_fields__
                    })
                except Exception:
                    report = None
                if report is not None:
                    report.cache_info = self._cache.info_for_hit(cache_key)
                    context.set("code_refactoring_report", report)
                    return self.ok(
                        outputs={"code_refactoring_report": report.to_dict()},
                        metadata={"cache": "hit"},
                    )

            units, smells, actions, ext_points, maint = self._refactorer.refactor(
                arch_data, perf_data, sec_data, opt_data, bl_data,
            )

            self_ok, regression_ok = self._refactorer.self_verify(units, actions)

            confidence = self._confidence(
                sources_used, sources_missing, smells, units, actions, maint.overall,
            )

            report = self._builder.build(
                units=units,
                smells=smells,
                actions=actions,
                extensibility_points=ext_points,
                maintainability=maint,
                sources_used=sources_used,
                sources_missing=sources_missing,
                self_verification_passed=self_ok,
                regression_safe=regression_ok,
                confidence=confidence,
            )

            gate_findings, passed, verdict = self._quality_gate.validate(report)
            report.findings.extend(gate_findings)
            report.verdict = verdict
            report.readiness_status = verdict
            report.self_verification_passed = self_ok
            report.regression_safe = regression_ok

            report_dict = report.to_dict()
            report.cache_info = self._cache.put(cache_key, report_dict)
            context.set("code_refactoring_report", report)

            _log.info(
                "CodeRefactoringEngine finished — verdict=%s units=%d smells=%d "
                "actions=%d maint=%.1f self_ok=%s",
                verdict, len(units), len(smells), len(actions),
                maint.overall, self_ok,
            )

            if not passed:
                return self.failed(
                    errors=[
                        f"Code Refactoring failed quality gate (verdict={verdict})"
                    ],
                    outputs={"code_refactoring_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"code_refactoring_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "verdict": verdict,
                    "unit_count": len(units),
                    "smell_count": len(smells),
                    "action_count": len(actions),
                    "rejected_count": report.rejected_count,
                    "maintainability": maint.overall,
                    "self_verification_passed": self_ok,
                    "regression_safe": regression_ok,
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("CodeRefactoringEngine crashed: %s", exc)
            return self.failed(errors=[f"CodeRefactoringEngine error: {exc}"])

    def _confidence(
        self, used, missing, smells, units, actions, maint_overall
    ) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        unsafe = sum(
            1 for a in actions
            if not getattr(a, "behavior_safe", True)
            and getattr(a, "status", "") == "applied"
        )
        penalty = min(0.5, unsafe * 0.25)
        richness = min(1.0, len(units) / 8.0)
        maint_factor = maint_overall / 100.0
        conf = (0.30 * ratio) + (0.20 * richness) + (0.35 * maint_factor) + 0.15 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["CodeRefactoringEngine"]
