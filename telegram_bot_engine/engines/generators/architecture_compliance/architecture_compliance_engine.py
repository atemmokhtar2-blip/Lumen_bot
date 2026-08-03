"""
ArchitectureComplianceEngine — Specification 037 (ULTRA CRITICAL)

Ensures generated code still matches the designed architecture.
Any architecture violation blocks progression to the next engine.
"""

from __future__ import annotations

import hashlib
import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    PerformanceReader, SecurityReader, ArchitectureDecisionReader,
    ComponentArchitectureReader, InterfaceContractReader,
    ModuleArchitectureReader, ProjectContextReader, BusinessLogicReader,
)
from .report_data import (
    ArchitectureComplianceReport, ALL_SOURCES,
    SOURCE_PERFORMANCE, SOURCE_SECURITY, SOURCE_ARCHITECTURE_DECISION,
    SOURCE_COMPONENT_ARCHITECTURE, SOURCE_INTERFACE_CONTRACT,
    SOURCE_MODULE_ARCHITECTURE, SOURCE_PROJECT_CONTEXT, SOURCE_BUSINESS_LOGIC,
)
from .compliance_checker import ComplianceChecker
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.architecture_compliance")


class ArchitectureComplianceEngine(BaseEngine):
    """Specification 037 — Intelligent Architecture Compliance Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="architecture_compliance",
            version="1.0.0",
            description=(
                "Validates that implementation still matches architecture "
                "blueprints: layers, SOLID, dependencies, interfaces and contracts."
            ),
            tags=["architecture", "compliance", "solid", "layers", "dependencies"],
            metadata={"specification": "037", "priority": "ULTRA_CRITICAL"},
        )
        self._perf_reader = PerformanceReader()
        self._sec_reader = SecurityReader()
        self._arch_reader = ArchitectureDecisionReader()
        self._comp_reader = ComponentArchitectureReader()
        self._iface_reader = InterfaceContractReader()
        self._mod_reader = ModuleArchitectureReader()
        self._ctx_reader = ProjectContextReader()
        self._bl_reader = BusinessLogicReader()
        self._checker = ComplianceChecker()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("ArchitectureComplianceEngine starting (Spec 037)")

            perf_data = self._perf_reader.read(context)
            sec_data = self._sec_reader.read(context)
            arch_data = self._arch_reader.read(context)
            comp_data = self._comp_reader.read(context)
            iface_data = self._iface_reader.read(context)
            mod_data = self._mod_reader.read(context)
            ctx_data = self._ctx_reader.read(context)
            bl_data = self._bl_reader.read(context)

            sources_used = []
            sources_missing = []
            for key, data in (
                (SOURCE_PERFORMANCE, perf_data),
                (SOURCE_SECURITY, sec_data),
                (SOURCE_ARCHITECTURE_DECISION, arch_data),
                (SOURCE_COMPONENT_ARCHITECTURE, comp_data),
                (SOURCE_INTERFACE_CONTRACT, iface_data),
                (SOURCE_MODULE_ARCHITECTURE, mod_data),
                (SOURCE_PROJECT_CONTEXT, ctx_data),
                (SOURCE_BUSINESS_LOGIC, bl_data),
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
                        str(b.get("unit_id") or b.get("method_id") or b.get("name") or ""),
                        str(b.get("class_name") or b.get("name") or "")[:40],
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
                    report = ArchitectureComplianceReport(**{
                        k: v for k, v in cached.items()
                        if k in ArchitectureComplianceReport.__dataclass_fields__
                    })
                except Exception:
                    report = None
                if report is not None:
                    report.cache_info = self._cache.info_for_hit(cache_key)
                    context.set("architecture_compliance_report", report)
                    return self.ok(
                        outputs={"architecture_compliance_report": report.to_dict()},
                        metadata={"cache": "hit"},
                    )

            units, violations, refactorings, compliance, solid = self._checker.check(
                perf_data, sec_data, arch_data, comp_data, iface_data, mod_data, bl_data,
            )

            self_ok, residual = self._checker.self_review(units, violations)
            if residual:
                # residual already subset of open criticals
                pass

            confidence = self._confidence(
                sources_used, sources_missing, violations, units, compliance,
            )

            report = self._builder.build(
                units=units,
                violations=violations,
                refactorings=refactorings,
                sources_used=sources_used,
                sources_missing=sources_missing,
                compliance_score=compliance,
                solid_score=solid,
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
            context.set("architecture_compliance_report", report)

            _log.info(
                "ArchitectureComplianceEngine finished — verdict=%s units=%d "
                "violations=%d compliance=%.1f self_review=%s",
                verdict, len(units), len(violations), compliance, self_ok,
            )

            if not passed:
                return self.failed(
                    errors=[
                        f"Architecture Compliance failed quality gate "
                        f"(verdict={verdict})"
                    ],
                    outputs={"architecture_compliance_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"architecture_compliance_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "verdict": verdict,
                    "unit_count": len(units),
                    "violation_count": len(violations),
                    "critical_violation_count": report.critical_violation_count,
                    "compliance_score": compliance,
                    "solid_score": solid,
                    "self_review_passed": self_ok,
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("ArchitectureComplianceEngine crashed: %s", exc)
            return self.failed(
                errors=[f"ArchitectureComplianceEngine error: {exc}"]
            )

    def _confidence(self, used, missing, violations, units, compliance) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        open_crit = sum(
            1 for v in violations
            if getattr(v, "severity", "") == "critical"
            and getattr(v, "status", "") == "open"
        )
        penalty = min(0.5, open_crit * 0.15)
        richness = min(1.0, len(units) / 8.0)
        score_factor = compliance / 100.0
        conf = (0.30 * ratio) + (0.20 * richness) + (0.35 * score_factor) + 0.15 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["ArchitectureComplianceEngine"]
