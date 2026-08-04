"""QualityGate — Specification 056 (CRITICAL)"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    ResourceManagementReport, ResourceFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_NO_OVER_LIMIT, RULE_NO_SYSTEM_DEGRADE, RULE_LEAKS_CLEANED,
    RULE_SELF_VERIFICATION, RULE_QUALITY_PASS, ALL_QUALITY_RULES,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)


class QualityGate:
    def validate(
        self, report: ResourceManagementReport
    ) -> Tuple[List[ResourceFinding], bool, str]:
        findings: List[ResourceFinding] = []
        critical_fail = False
        warnings = 0

        for rule in ALL_QUALITY_RULES:
            if rule == RULE_NO_OVER_LIMIT:
                over = [u for u in report.usage if u.over_limit]
                if over and not report.recovered:
                    findings.append(ResourceFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(over)} engine(s) exceeded resource limits.",
                        affected=",".join(u.engine_id for u in over[:5]),
                        category="limits",
                        resolution_hint="Throttle or rebalance quotas.",
                    ))
                    critical_fail = True
                elif over and report.recovered:
                    findings.append(ResourceFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message=f"{len(over)} over-limit engine(s) recovered via rebalance.",
                        affected="quotas", category="limits",
                    ))
                    warnings += 1

            elif rule == RULE_NO_SYSTEM_DEGRADE:
                if report.system.available_cpu_percent < 5.0:
                    findings.append(ResourceFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="System CPU nearly exhausted by engine load.",
                        affected="system", category="performance",
                    ))
                    critical_fail = True
                if report.system.available_ram_mb < 32.0:
                    findings.append(ResourceFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="System RAM critically low.",
                        affected="system", category="performance",
                    ))
                    critical_fail = True
                if report.system.total_cpu_percent > 80.0:
                    findings.append(ResourceFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"High aggregate CPU: {report.system.total_cpu_percent}%",
                        affected="system", category="performance",
                    ))
                    warnings += 1

            elif rule == RULE_LEAKS_CLEANED:
                unclean = [l for l in report.leaks if not l.cleaned]
                if unclean:
                    findings.append(ResourceFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(unclean)} resource leak(s) not cleaned.",
                        affected=",".join(l.engine_id for l in unclean[:5]),
                        category="leaks",
                    ))
                    critical_fail = True
                elif report.leak_count:
                    findings.append(ResourceFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message=f"{report.leak_count} leak(s) detected and cleaned.",
                        affected="leaks", category="leaks",
                    ))
                    warnings += 1

            elif rule == RULE_SELF_VERIFICATION:
                if not report.self_verification_passed:
                    findings.append(ResourceFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Self-verification did not pass.",
                        affected="report", category="self_verification",
                    ))
                    critical_fail = True

            elif rule == RULE_QUALITY_PASS:
                if report.engine_count == 0:
                    findings.append(ResourceFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message="No engines allocated resources.",
                        affected="quotas", category="quality",
                    ))
                    warnings += 1

        if critical_fail:
            return findings, False, VERDICT_NOT_READY
        if warnings > 0 or any(f.severity == SEVERITY_HIGH for f in findings):
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
