"""
StaticAnalysisEngine — Specification 039 (ULTRA CRITICAL)

Runs static analysis on generated source without execution.
Critical issues block progression to the next engine.
Produces repair suggestions only (no direct code mutation).
"""

from __future__ import annotations

import hashlib
import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    CodeRefactoringReader, ArchitectureComplianceReader, PerformanceReader,
    SecurityReader, BusinessLogicReader, ProjectContextReader,
)
from .report_data import (
    StaticAnalysisReport, ALL_SOURCES,
    SOURCE_CODE_REFACTORING, SOURCE_ARCHITECTURE_COMPLIANCE,
    SOURCE_PERFORMANCE, SOURCE_SECURITY, SOURCE_BUSINESS_LOGIC,
    SOURCE_PROJECT_CONTEXT,
)
from .analyzer import StaticAnalyzer
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.static_analysis")


class StaticAnalysisEngine(BaseEngine):
    """Specification 039 — Intelligent Static Analysis Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="static_analysis",
            version="1.0.0",
            description=(
                "Static analysis of generated code: syntax, semantics, control/data flow, "
                "architecture, smells, dependencies, security and performance signals. "
                "Critical issues block the pipeline."
            ),
            tags=["static-analysis", "lint", "code-smells", "dependencies", "risk"],
            metadata={"specification": "039", "priority": "ULTRA_CRITICAL"},
        )
        self._ref_reader = CodeRefactoringReader()
        self._arch_reader = ArchitectureComplianceReader()
        self._perf_reader = PerformanceReader()
        self._sec_reader = SecurityReader()
        self._bl_reader = BusinessLogicReader()
        self._ctx_reader = ProjectContextReader()
        self._analyzer = StaticAnalyzer()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("StaticAnalysisEngine starting (Spec 039)")

            ref_data = self._ref_reader.read(context)
            arch_data = self._arch_reader.read(context)
            perf_data = self._perf_reader.read(context)
            sec_data = self._sec_reader.read(context)
            bl_data = self._bl_reader.read(context)
            ctx_data = self._ctx_reader.read(context)

            sources_used = []
            sources_missing = []
            for key, data in (
                (SOURCE_CODE_REFACTORING, ref_data),
                (SOURCE_ARCHITECTURE_COMPLIANCE, arch_data),
                (SOURCE_PERFORMANCE, perf_data),
                (SOURCE_SECURITY, sec_data),
                (SOURCE_BUSINESS_LOGIC, bl_data),
                (SOURCE_PROJECT_CONTEXT, ctx_data),
            ):
                if data.available:
                    sources_used.append(key)
                else:
                    sources_missing.append(key)

            primary = ref_data if ref_data.available else (
                perf_data if perf_data.available else bl_data
            )
            cache_payload = ""
            if primary.available and primary.items:
                cache_payload = str(sorted(
                    (
                        str(b.get("unit_id") or b.get("method_id") or ""),
                        str(
                            b.get("refactored_code")
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
                    report = StaticAnalysisReport(**{
                        k: v for k, v in cached.items()
                        if k in StaticAnalysisReport.__dataclass_fields__
                    })
                except Exception:
                    report = None
                if report is not None:
                    report.cache_info = self._cache.info_for_hit(cache_key)
                    context.set("static_analysis_report", report)
                    return self.ok(
                        outputs={"static_analysis_report": report.to_dict()},
                        metadata={"cache": "hit"},
                    )

            units, issues, suggestions, deps, risks = self._analyzer.analyze(
                ref_data, arch_data, perf_data, sec_data, bl_data,
            )

            self_ok, residual = self._analyzer.self_verify(units, issues)
            if residual:
                # avoid duplicating exact same criticals
                existing_ids = {i.issue_id for i in issues}
                for r in residual:
                    if r.issue_id not in existing_ids:
                        issues.append(r)

            confidence = self._confidence(
                sources_used, sources_missing, issues, units,
            )

            report = self._builder.build(
                units=units,
                issues=issues,
                suggestions=suggestions,
                dependencies=deps,
                risks=risks,
                sources_used=sources_used,
                sources_missing=sources_missing,
                self_verification_passed=self_ok,
                confidence=confidence,
            )

            gate_findings, passed, verdict = self._quality_gate.validate(report)
            report.findings.extend(gate_findings)
            report.verdict = verdict
            report.readiness_status = verdict
            report.self_verification_passed = self_ok

            report_dict = report.to_dict()
            report.cache_info = self._cache.put(cache_key, report_dict)
            context.set("static_analysis_report", report)

            _log.info(
                "StaticAnalysisEngine finished — verdict=%s units=%d issues=%d "
                "open_crit=%d self_ok=%s",
                verdict, len(units), len(issues),
                report.open_critical_count, self_ok,
            )

            if not passed:
                return self.failed(
                    errors=[
                        f"Static Analysis failed quality gate (verdict={verdict})"
                    ],
                    outputs={"static_analysis_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"static_analysis_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "verdict": verdict,
                    "unit_count": len(units),
                    "issue_count": len(issues),
                    "critical_count": report.critical_count,
                    "open_critical_count": report.open_critical_count,
                    "suggestion_count": len(suggestions),
                    "self_verification_passed": self_ok,
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("StaticAnalysisEngine crashed: %s", exc)
            return self.failed(errors=[f"StaticAnalysisEngine error: {exc}"])

    def _confidence(self, used, missing, issues, units) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        open_crit = sum(
            1 for i in issues
            if getattr(i, "severity", "") == "critical"
            and getattr(i, "status", "") == "open"
        )
        penalty = min(0.5, open_crit * 0.15)
        richness = min(1.0, len(units) / 8.0)
        syntax_ok_ratio = (
            sum(1 for u in units if u.syntax_ok) / len(units) if units else 1.0
        )
        conf = (0.30 * ratio) + (0.25 * richness) + (0.30 * syntax_ok_ratio) + 0.15 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["StaticAnalysisEngine"]
