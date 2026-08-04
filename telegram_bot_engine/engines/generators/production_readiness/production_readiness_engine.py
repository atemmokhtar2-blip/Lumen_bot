"""
ProductionReadinessEngine — Specification 045 (MAXIMUM CRITICAL)

Final engine in the pipeline. Issues or rejects the Production Ready
Certificate. Telegram Bot Token must NEVER be requested unless certified.
"""

from __future__ import annotations

import hashlib
import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    E2EReader, UnitTestReader, IntegrationReader, SelfHealingReader,
    RuntimeReader, StaticReader, ArchitectureReader, SecurityReader,
    PerformanceReader, RefactoringReader,
)
from .report_data import (
    ProductionReadinessReport, ALL_SOURCES,
    SOURCE_E2E, SOURCE_UNIT_TEST, SOURCE_INTEGRATION, SOURCE_SELF_HEALING,
    SOURCE_RUNTIME, SOURCE_STATIC, SOURCE_ARCHITECTURE, SOURCE_SECURITY,
    SOURCE_PERFORMANCE, SOURCE_REFACTORING,
    VERDICT_CERTIFIED, VERDICT_REJECTED,
)
from .certifier import ProductionCertifier
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.production_readiness")


class ProductionReadinessEngine(BaseEngine):
    """Specification 045 — Production Readiness Certification Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="production_readiness",
            version="1.0.0",
            description=(
                "Final certification gate. Scores architecture, security, "
                "performance, reliability, testing and integration. Issues "
                "Production Ready Certificate only when all thresholds pass. "
                "Telegram token gate stays CLOSED until certified."
            ),
            tags=["production", "certificate", "token-gate", "final", "qa"],
            metadata={"specification": "045", "priority": "MAXIMUM_CRITICAL"},
        )
        self._e2e_reader = E2EReader()
        self._unit_reader = UnitTestReader()
        self._integration_reader = IntegrationReader()
        self._heal_reader = SelfHealingReader()
        self._runtime_reader = RuntimeReader()
        self._static_reader = StaticReader()
        self._arch_reader = ArchitectureReader()
        self._sec_reader = SecurityReader()
        self._perf_reader = PerformanceReader()
        self._ref_reader = RefactoringReader()
        self._certifier = ProductionCertifier()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("ProductionReadinessEngine starting (Spec 045)")

            e2e = self._e2e_reader.read(context)
            unit = self._unit_reader.read(context)
            integration = self._integration_reader.read(context)
            heal = self._heal_reader.read(context)
            runtime = self._runtime_reader.read(context)
            static = self._static_reader.read(context)
            architecture = self._arch_reader.read(context)
            security = self._sec_reader.read(context)
            performance = self._perf_reader.read(context)
            refactoring = self._ref_reader.read(context)

            sources_used = []
            sources_missing = []
            for key, data in (
                (SOURCE_E2E, e2e),
                (SOURCE_UNIT_TEST, unit),
                (SOURCE_INTEGRATION, integration),
                (SOURCE_SELF_HEALING, heal),
                (SOURCE_RUNTIME, runtime),
                (SOURCE_STATIC, static),
                (SOURCE_ARCHITECTURE, architecture),
                (SOURCE_SECURITY, security),
                (SOURCE_PERFORMANCE, performance),
                (SOURCE_REFACTORING, refactoring),
            ):
                if data.available:
                    sources_used.append(key)
                else:
                    sources_missing.append(key)

            cache_payload = str(sorted(sources_used)) + str(len(sources_missing))
            cache_key = hashlib.sha256(cache_payload.encode("utf-8")).hexdigest()[:32]

            cached = self._cache.get(cache_key)
            if cached is not None:
                try:
                    report = ProductionReadinessReport(**{
                        k: v for k, v in cached.items()
                        if k in ProductionReadinessReport.__dataclass_fields__
                    })
                except Exception:
                    report = None
                if report is not None:
                    report.cache_info = self._cache.info_for_hit(cache_key)
                    context.set("production_readiness_report", report)
                    # Always expose token gate state on context
                    context.set("telegram_token_gate_open", report.token_gate_open)
                    return self.ok(
                        outputs={"production_readiness_report": report.to_dict()},
                        metadata={"cache": "hit", "certified": report.certified},
                    )

            axes, blockers, certificate, overall, certified = self._certifier.certify(
                e2e, unit, integration, heal, runtime, static,
                architecture, security, performance, refactoring,
            )

            self_ok = self._certifier.self_verify(axes, blockers, certified)

            confidence = self._confidence(
                sources_used, sources_missing, overall, certified, blockers,
            )

            report = self._builder.build(
                axes=axes,
                blockers=blockers,
                certificate=certificate,
                sources_used=sources_used,
                sources_missing=sources_missing,
                overall_score=overall,
                certified=certified,
                self_verification_passed=self_ok,
                confidence=confidence,
            )

            gate_findings, passed, verdict = self._quality_gate.validate(report)
            report.findings.extend(gate_findings)
            report.verdict = verdict
            report.readiness_status = verdict
            report.self_verification_passed = self_ok
            report.certified = certified
            report.token_gate_open = certificate.token_gate_open

            report_dict = report.to_dict()
            report.cache_info = self._cache.put(cache_key, report_dict)
            context.set("production_readiness_report", report)
            context.set("telegram_token_gate_open", certificate.token_gate_open)

            _log.info(
                "ProductionReadinessEngine finished — certified=%s overall=%.1f "
                "token_gate=%s blockers=%d",
                certified, overall, certificate.token_gate_open, len(blockers),
            )

            if not certified:
                return self.failed(
                    errors=[
                        "Production Ready Certificate REJECTED. "
                        "Telegram token gate remains CLOSED."
                    ],
                    outputs={"production_readiness_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"production_readiness_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "verdict": verdict,
                    "certified": True,
                    "overall_score": overall,
                    "token_gate_open": True,
                    "certificate_id": certificate.certificate_id,
                    "blocker_count": len(blockers),
                    "self_verification_passed": self_ok,
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("ProductionReadinessEngine crashed: %s", exc)
            return self.failed(errors=[f"ProductionReadinessEngine error: {exc}"])

    def _confidence(self, used, missing, overall, certified, blockers) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        score_factor = overall / 100.0
        penalty = min(0.4, len(blockers) * 0.05 + (0.0 if certified else 0.15))
        conf = (0.35 * ratio) + (0.45 * score_factor) + 0.20 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["ProductionReadinessEngine"]
