"""
SecurityReviewEngine — Specification 035 (ULTRA CRITICAL)

Reviews all generated source for security issues, applies safe fixes,
and blocks progression when critical vulnerabilities remain.
"""

from __future__ import annotations

import hashlib
import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    CodeOptimizationReader, BusinessLogicReader, ClassGenerationReader,
    FunctionGenerationReader, ArchitectureDecisionReader, ProjectContextReader,
)
from .report_data import (
    SecurityReviewReport, ALL_SOURCES,
    SOURCE_CODE_OPTIMIZATION, SOURCE_BUSINESS_LOGIC, SOURCE_CLASS_GENERATION,
    SOURCE_FUNCTION_GENERATION, SOURCE_ARCHITECTURE_DECISION, SOURCE_PROJECT_CONTEXT,
)
from .security_scanner import SecurityScanner
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.security_review")


class SecurityReviewEngine(BaseEngine):
    """Specification 035 — Intelligent Security Review Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="security_review",
            version="1.0.0",
            description=(
                "Reviews generated source for security vulnerabilities, applies "
                "safe fixes, and blocks critical issues. Does not add features "
                "or change business logic beyond hardening."
            ),
            tags=["security", "review", "injection", "secrets", "hardening"],
            metadata={"specification": "035", "priority": "ULTRA_CRITICAL"},
        )
        self._opt_reader = CodeOptimizationReader()
        self._bl_reader = BusinessLogicReader()
        self._class_reader = ClassGenerationReader()
        self._func_reader = FunctionGenerationReader()
        self._arch_reader = ArchitectureDecisionReader()
        self._ctx_reader = ProjectContextReader()
        self._scanner = SecurityScanner()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("SecurityReviewEngine starting (Spec 035)")

            opt_data = self._opt_reader.read(context)
            bl_data = self._bl_reader.read(context)
            class_data = self._class_reader.read(context)
            func_data = self._func_reader.read(context)
            arch_data = self._arch_reader.read(context)
            ctx_data = self._ctx_reader.read(context)

            sources_used = []
            sources_missing = []
            for key, data in (
                (SOURCE_CODE_OPTIMIZATION, opt_data),
                (SOURCE_BUSINESS_LOGIC, bl_data),
                (SOURCE_CLASS_GENERATION, class_data),
                (SOURCE_FUNCTION_GENERATION, func_data),
                (SOURCE_ARCHITECTURE_DECISION, arch_data),
                (SOURCE_PROJECT_CONTEXT, ctx_data),
            ):
                if data.available:
                    sources_used.append(key)
                else:
                    sources_missing.append(key)

            cache_payload = ""
            primary = opt_data if opt_data.available else bl_data
            if primary.available and primary.items:
                cache_payload = str(sorted(
                    (
                        str(b.get("unit_id") or b.get("method_id") or ""),
                        str(b.get("secured_code") or b.get("source_code") or "")[:80],
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
                    report = SecurityReviewReport(**{
                        k: v for k, v in cached.items()
                        if k in SecurityReviewReport.__dataclass_fields__
                    })
                except Exception:
                    report = None
                if report is not None:
                    report.cache_info = self._cache.info_for_hit(cache_key)
                    context.set("security_review_report", report)
                    return self.ok(
                        outputs={"security_review_report": report.to_dict()},
                        metadata={"cache": "hit"},
                    )

            units, vulns, risks = self._scanner.scan_and_fix(
                opt_data, bl_data, func_data,
            )

            self_ok, residual = self._scanner.self_review(units, vulns)
            if residual:
                vulns.extend(residual)

            confidence = self._confidence(sources_used, sources_missing, vulns, units)

            report = self._builder.build(
                units=units,
                vulnerabilities=vulns,
                risks=risks,
                sources_used=sources_used,
                sources_missing=sources_missing,
                self_review_passed=self_ok,
                confidence=confidence,
            )

            gate_findings, passed, verdict = self._quality_gate.validate(report)
            report.findings.extend(gate_findings)
            report.verdict = verdict
            report.readiness_status = verdict
            report.self_review_passed = self_ok

            report_dict = report.to_dict()
            report.cache_info = self._cache.put(cache_key, report_dict)
            context.set("security_review_report", report)

            _log.info(
                "SecurityReviewEngine finished — verdict=%s units=%d vulns=%d "
                "open_crit=%d self_review=%s",
                verdict, len(units), len(vulns),
                report.open_critical_count, self_ok,
            )

            if not passed:
                return self.failed(
                    errors=[f"Security Review failed quality gate (verdict={verdict})"],
                    outputs={"security_review_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"security_review_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "verdict": verdict,
                    "unit_count": len(units),
                    "vuln_count": len(vulns),
                    "critical_count": report.critical_count,
                    "fixed_count": report.fixed_count,
                    "open_critical_count": report.open_critical_count,
                    "self_review_passed": self_ok,
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("SecurityReviewEngine crashed: %s", exc)
            return self.failed(errors=[f"SecurityReviewEngine error: {exc}"])

    def _confidence(self, used, missing, vulns, units) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        open_crit = sum(
            1 for v in vulns
            if getattr(v, "severity", "") == "critical"
            and getattr(v, "status", "") == "open"
        )
        penalty = min(0.5, open_crit * 0.2)
        richness = min(1.0, len(units) / 8.0)
        fixed_ratio = 0.0
        if vulns:
            fixed = sum(1 for v in vulns if getattr(v, "status", "") == "fixed")
            fixed_ratio = fixed / len(vulns)
        conf = (0.30 * ratio) + (0.25 * richness) + (0.25 * fixed_ratio) + 0.20 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["SecurityReviewEngine"]
