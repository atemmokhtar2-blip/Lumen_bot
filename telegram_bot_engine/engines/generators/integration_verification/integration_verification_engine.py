"""
IntegrationVerificationEngine — Specification 042 (ULTRA CRITICAL)

Verifies that healed project parts integrate as one system.
Any integration failure blocks delivery to the next engine.
"""

from __future__ import annotations

import hashlib
import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    SelfHealingReader, RuntimeReader, ArchitectureReader,
    StaticReader, SecurityReader, ProjectContextReader,
)
from .report_data import (
    IntegrationVerificationReport, ALL_SOURCES,
    SOURCE_SELF_HEALING, SOURCE_RUNTIME, SOURCE_ARCHITECTURE,
    SOURCE_STATIC, SOURCE_SECURITY, SOURCE_PROJECT_CONTEXT,
)
from .verifier import IntegrationVerifier
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.integration_verification")


class IntegrationVerificationEngine(BaseEngine):
    """Specification 042 — Intelligent Integration Verification Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="integration_verification",
            version="1.0.0",
            description=(
                "Verifies modules, interfaces, DI, config, database, Telegram and "
                "external services integrate correctly. Blocks on integration failure."
            ),
            tags=["integration", "telegram", "di", "compatibility", "verification"],
            metadata={"specification": "042", "priority": "ULTRA_CRITICAL"},
        )
        self._heal_reader = SelfHealingReader()
        self._runtime_reader = RuntimeReader()
        self._arch_reader = ArchitectureReader()
        self._static_reader = StaticReader()
        self._sec_reader = SecurityReader()
        self._ctx_reader = ProjectContextReader()
        self._verifier = IntegrationVerifier()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("IntegrationVerificationEngine starting (Spec 042)")

            heal_data = self._heal_reader.read(context)
            runtime_data = self._runtime_reader.read(context)
            arch_data = self._arch_reader.read(context)
            static_data = self._static_reader.read(context)
            sec_data = self._sec_reader.read(context)
            ctx_data = self._ctx_reader.read(context)

            sources_used = []
            sources_missing = []
            for key, data in (
                (SOURCE_SELF_HEALING, heal_data),
                (SOURCE_RUNTIME, runtime_data),
                (SOURCE_ARCHITECTURE, arch_data),
                (SOURCE_STATIC, static_data),
                (SOURCE_SECURITY, sec_data),
                (SOURCE_PROJECT_CONTEXT, ctx_data),
            ):
                if data.available:
                    sources_used.append(key)
                else:
                    sources_missing.append(key)

            cache_payload = str(sorted(sources_used)) + str(
                (heal_data.raw or {}).get("failed_count", 0)
            ) + str((runtime_data.raw or {}).get("failed_event_count", 0))
            cache_key = hashlib.sha256(cache_payload.encode("utf-8")).hexdigest()[:32]

            cached = self._cache.get(cache_key)
            if cached is not None:
                try:
                    report = IntegrationVerificationReport(**{
                        k: v for k, v in cached.items()
                        if k in IntegrationVerificationReport.__dataclass_fields__
                    })
                except Exception:
                    report = None
                if report is not None:
                    report.cache_info = self._cache.info_for_hit(cache_key)
                    context.set("integration_verification_report", report)
                    return self.ok(
                        outputs={"integration_verification_report": report.to_dict()},
                        metadata={"cache": "hit"},
                    )

            checks, compat, deps, score, runs = self._verifier.verify(
                heal_data, runtime_data, arch_data, static_data, sec_data, ctx_data,
            )

            self_ok = self._verifier.self_verify(checks)

            confidence = self._confidence(
                sources_used, sources_missing, checks, score.overall,
            )

            report = self._builder.build(
                checks=checks,
                compatibility=compat,
                dependencies=deps,
                score=score,
                sources_used=sources_used,
                sources_missing=sources_missing,
                self_verification_passed=self_ok,
                runs_completed=runs,
                confidence=confidence,
            )

            gate_findings, passed, verdict = self._quality_gate.validate(report)
            report.findings.extend(gate_findings)
            report.verdict = verdict
            report.readiness_status = verdict
            report.self_verification_passed = self_ok

            report_dict = report.to_dict()
            report.cache_info = self._cache.put(cache_key, report_dict)
            context.set("integration_verification_report", report)

            _log.info(
                "IntegrationVerificationEngine finished — verdict=%s checks=%d "
                "failed=%d score=%.1f",
                verdict, len(checks), report.failed_count, score.overall,
            )

            if not passed:
                return self.failed(
                    errors=[
                        f"Integration Verification failed quality gate "
                        f"(verdict={verdict})"
                    ],
                    outputs={"integration_verification_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"integration_verification_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "verdict": verdict,
                    "check_count": len(checks),
                    "failed_count": report.failed_count,
                    "warning_count": report.warning_count,
                    "integration_score": score.overall,
                    "self_verification_passed": self_ok,
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("IntegrationVerificationEngine crashed: %s", exc)
            return self.failed(
                errors=[f"IntegrationVerificationEngine error: {exc}"]
            )

    def _confidence(self, used, missing, checks, overall) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        failed = sum(1 for c in checks if getattr(c, "status", "") == "failed")
        penalty = min(0.5, failed * 0.08)
        score_factor = overall / 100.0
        conf = (0.30 * ratio) + (0.45 * score_factor) + 0.25 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["IntegrationVerificationEngine"]
