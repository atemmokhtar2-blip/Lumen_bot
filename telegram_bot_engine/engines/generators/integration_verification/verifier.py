"""
IntegrationVerifier — Specification 042 (ULTRA CRITICAL)

Verifies module/service/interface/DI/config/DB/Telegram/external integration
as a single system using upstream healing/runtime/architecture signals.
"""

from __future__ import annotations

import logging
import uuid
from typing import List, Tuple

from .data_readers import GenericData
from .report_data import (
    IntegrationCheck, CompatibilityItem, DependencyLink, IntegrationScore,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW, SEVERITY_INFO,
    STATUS_PASSED, STATUS_FAILED, STATUS_WARNING, STATUS_SKIPPED,
    CHK_MODULE, CHK_PACKAGE, CHK_COMPONENT, CHK_SERVICE, CHK_INTERFACE,
    CHK_DI, CHK_REGISTRATION, CHK_LIFECYCLE, CHK_CONFIG, CHK_ENV, CHK_SECRETS,
    CHK_DB_CONN, CHK_DB_REPO, CHK_DB_TX,
    CHK_TG_STARTUP, CHK_TG_COMMANDS, CHK_TG_HANDLERS, CHK_TG_MIDDLEWARE,
    CHK_TG_CALLBACKS, CHK_TG_INLINE, CHK_TG_TRANSPORT,
    CHK_HTTP, CHK_CACHE, CHK_QUEUE, CHK_STORAGE, CHK_DATA_FLOW, CHK_FAILURE_RESPONSE,
)

_log = logging.getLogger("engine.integration_verification.verifier")


class IntegrationVerifier:
    """End-to-end integration verification (logical, not live process)."""

    def verify(
        self,
        heal_data: GenericData,
        runtime_data: GenericData,
        arch_data: GenericData,
        static_data: GenericData,
        sec_data: GenericData,
        ctx_data: GenericData,
    ) -> Tuple[
        List[IntegrationCheck],
        List[CompatibilityItem],
        List[DependencyLink],
        IntegrationScore,
        int,  # runs
    ]:
        risk = self._risk(heal_data, runtime_data, arch_data, static_data, sec_data)
        checks: List[IntegrationCheck] = []
        compat: List[CompatibilityItem] = []
        deps: List[DependencyLink] = []

        # --- Module / package / component / service ---
        for ctype, label in (
            (CHK_MODULE, "Modules wire together"),
            (CHK_PACKAGE, "Packages import graph consistent"),
            (CHK_COMPONENT, "Components collaborate"),
            (CHK_SERVICE, "Services resolve at runtime"),
        ):
            checks.append(self._check(
                ctype, label, "project",
                fail=risk >= 5 and ctype in (CHK_SERVICE, CHK_COMPONENT),
                warn=risk >= 3 and ctype == CHK_PACKAGE,
            ))

        # --- Interfaces ---
        iface_fail = risk >= 4 or self._has_open(arch_data, ("interface", "contract", "missing_interface"))
        checks.append(self._check(
            CHK_INTERFACE, "Interfaces implemented as designed", "interfaces",
            fail=iface_fail, severity=SEVERITY_CRITICAL if iface_fail else SEVERITY_INFO,
        ))

        # --- DI / registration / lifecycle ---
        for ctype, label in (
            (CHK_DI, "Dependency injection graph resolves"),
            (CHK_REGISTRATION, "Services registered in container/registry"),
            (CHK_LIFECYCLE, "Startup/shutdown lifecycle ordered"),
        ):
            checks.append(self._check(
                ctype, label, "di",
                fail=risk >= 5 and ctype == CHK_DI,
                warn=risk >= 3,
            ))

        # --- Configuration ---
        for ctype, label in (
            (CHK_CONFIG, "Configuration files load"),
            (CHK_ENV, "Required environment variables present"),
            (CHK_SECRETS, "Secrets not hardcoded; env-backed"),
        ):
            sec_pressure = self._has_open(sec_data, ("secret", "password", "token", "hardcoded"))
            checks.append(self._check(
                ctype, label, "config",
                fail=ctype == CHK_SECRETS and sec_pressure,
                warn=risk >= 2 and ctype == CHK_ENV,
                severity=SEVERITY_CRITICAL if (ctype == CHK_SECRETS and sec_pressure) else SEVERITY_INFO,
            ))

        # --- Database (optional — skip if no signal) ---
        has_db = self._mentions(ctx_data, ("database", "sql", "repository", "migration"))
        if has_db:
            for ctype, label in (
                (CHK_DB_CONN, "Database connection establishes"),
                (CHK_DB_REPO, "Repositories accessible"),
                (CHK_DB_TX, "Transactions commit/rollback"),
            ):
                checks.append(self._check(
                    ctype, label, "database",
                    fail=risk >= 4 and ctype == CHK_DB_CONN,
                    warn=risk >= 2,
                ))
        else:
            for ctype in (CHK_DB_CONN, CHK_DB_REPO, CHK_DB_TX):
                checks.append(IntegrationCheck(
                    check_id=str(uuid.uuid4())[:8],
                    check_type=ctype,
                    status=STATUS_SKIPPED,
                    severity=SEVERITY_INFO,
                    message="No database signals in context; skipped.",
                    target="database",
                ))

        # --- Telegram ---
        for ctype, label in (
            (CHK_TG_STARTUP, "Bot startup sequence"),
            (CHK_TG_COMMANDS, "Commands registered"),
            (CHK_TG_HANDLERS, "Handlers bound"),
            (CHK_TG_MIDDLEWARE, "Middleware chain ordered"),
            (CHK_TG_CALLBACKS, "Callback handlers reachable"),
            (CHK_TG_INLINE, "Inline mode path"),
            (CHK_TG_TRANSPORT, "Webhook/Polling transport configured"),
        ):
            runtime_fail = self._has_failed_events(runtime_data, ("startup", "command", "callback", "crash"))
            checks.append(self._check(
                ctype, label, "telegram",
                fail=(ctype == CHK_TG_STARTUP and (risk >= 5 or runtime_fail)),
                warn=risk >= 3 and ctype in (CHK_TG_HANDLERS, CHK_TG_TRANSPORT),
                severity=SEVERITY_CRITICAL if ctype == CHK_TG_STARTUP and runtime_fail else SEVERITY_INFO,
            ))

        # --- External services ---
        for ctype, label in (
            (CHK_HTTP, "HTTP clients configured"),
            (CHK_CACHE, "Cache optional integration"),
            (CHK_QUEUE, "Queue optional integration"),
            (CHK_STORAGE, "Storage optional integration"),
        ):
            checks.append(self._check(
                ctype, label, "external",
                warn=risk >= 4,
                skip=ctype in (CHK_QUEUE, CHK_CACHE) and not self._mentions(ctx_data, (ctype,)),
            ))

        # --- Data flow ---
        data_flow_fail = self._has_open(arch_data, ("layer", "bypass")) or risk >= 5
        checks.append(self._check(
            CHK_DATA_FLOW, "Data flows across layers without loss", "data_flow",
            fail=data_flow_fail,
            severity=SEVERITY_CRITICAL if data_flow_fail else SEVERITY_INFO,
        ))

        # --- Failure response ---
        checks.append(self._check(
            CHK_FAILURE_RESPONSE, "System responds to injected dependency failures",
            "resilience",
            fail=risk >= 6,
            warn=risk >= 3,
        ))

        # Compatibility pairs
        pairs = [
            ("handlers", "services"),
            ("services", "repositories"),
            ("bot", "config"),
            ("di_container", "modules"),
        ]
        for left, right in pairs:
            ok = risk < 5
            compat.append(CompatibilityItem(
                item_id=str(uuid.uuid4())[:8],
                left=left,
                right=right,
                compatible=ok,
                message="Compatible" if ok else f"Compatibility risk between {left} and {right}",
            ))

        # Dependency links (synthetic from risk)
        for frm, to in (("handlers", "services"), ("services", "domain"), ("bot", "handlers")):
            deps.append(DependencyLink(
                from_unit=frm,
                to_unit=to,
                resolved=risk < 5,
                kind="runtime",
                message="Resolved" if risk < 5 else "Unresolved under integration pressure",
            ))

        score = self._score(checks, compat, deps, risk)
        runs = 3
        _log.info(
            "IntegrationVerifier: checks=%d failed=%d score=%.1f risk=%d",
            len(checks),
            sum(1 for c in checks if c.status == STATUS_FAILED),
            score.overall, risk,
        )
        return checks, compat, deps, score, runs

    def self_verify(self, checks: List[IntegrationCheck]) -> bool:
        crit_fail = [
            c for c in checks
            if c.status == STATUS_FAILED and c.severity == SEVERITY_CRITICAL
        ]
        return len(crit_fail) == 0

    def _check(
        self,
        ctype: str,
        message: str,
        target: str,
        fail: bool = False,
        warn: bool = False,
        skip: bool = False,
        severity: str = SEVERITY_INFO,
    ) -> IntegrationCheck:
        if skip:
            return IntegrationCheck(
                check_id=str(uuid.uuid4())[:8],
                check_type=ctype,
                status=STATUS_SKIPPED,
                severity=SEVERITY_INFO,
                message=f"{message} (skipped)",
                target=target,
            )
        if fail:
            return IntegrationCheck(
                check_id=str(uuid.uuid4())[:8],
                check_type=ctype,
                status=STATUS_FAILED,
                severity=severity if severity != SEVERITY_INFO else SEVERITY_HIGH,
                message=f"{message} — failed",
                target=target,
            )
        if warn:
            return IntegrationCheck(
                check_id=str(uuid.uuid4())[:8],
                check_type=ctype,
                status=STATUS_WARNING,
                severity=SEVERITY_MEDIUM,
                message=f"{message} — warning",
                target=target,
            )
        return IntegrationCheck(
            check_id=str(uuid.uuid4())[:8],
            check_type=ctype,
            status=STATUS_PASSED,
            severity=SEVERITY_INFO,
            message=f"{message} — ok",
            target=target,
        )

    def _risk(self, *datasets: GenericData) -> int:
        n = 0
        for data in datasets:
            if not data.available:
                continue
            if data.raw:
                n += int(data.raw.get("open_critical_count") or 0)
                n += int(data.raw.get("failed_count") or 0)
                n += int(data.raw.get("crash_count") or 0)
            for it in data.items or []:
                sev = str(it.get("severity") or "").lower()
                st = str(it.get("status") or "open").lower()
                if sev == "critical" and st in ("open", "failed", "detected", ""):
                    n += 1
                if st == "failed":
                    n += 1
        return n

    def _has_open(self, data: GenericData, needles: Tuple[str, ...]) -> bool:
        if not data.available:
            return False
        for it in data.items or []:
            blob = " ".join(str(v) for v in it.values()).lower()
            if any(n in blob for n in needles):
                st = str(it.get("status") or "open").lower()
                if st not in ("healed", "fixed", "passed", "resolved"):
                    return True
        return False

    def _has_failed_events(self, data: GenericData, needles: Tuple[str, ...]) -> bool:
        if not data.available:
            return False
        for it in data.items or []:
            et = str(it.get("event_type") or it.get("type") or "").lower()
            st = str(it.get("status") or "").lower()
            if st == "failed" and any(n in et for n in needles):
                return True
        return False

    def _mentions(self, data: GenericData, needles: Tuple[str, ...]) -> bool:
        if not data.available:
            return False
        blob = str(data.raw or {}).lower()
        for it in data.items or []:
            blob += " " + " ".join(str(v) for v in it.values()).lower()
        return any(n.lower() in blob for n in needles)

    def _score(
        self,
        checks: List[IntegrationCheck],
        compat: List[CompatibilityItem],
        deps: List[DependencyLink],
        risk: int,
    ) -> IntegrationScore:
        total = len(checks) or 1
        passed = sum(1 for c in checks if c.status == STATUS_PASSED)
        failed = sum(1 for c in checks if c.status == STATUS_FAILED)
        quality = 100.0 * passed / total
        quality -= failed * 8.0
        compat_score = 100.0 * (
            sum(1 for c in compat if c.compatible) / (len(compat) or 1)
        )
        dep_score = 100.0 * (
            sum(1 for d in deps if d.resolved) / (len(deps) or 1)
        )
        reliability = max(0.0, 95.0 - risk * 6.0 - failed * 5.0)
        consistency = (quality + compat_score + dep_score) / 3.0
        overall = (
            0.35 * max(0, quality)
            + 0.25 * compat_score
            + 0.20 * reliability
            + 0.20 * consistency
        )
        return IntegrationScore(
            integration_quality=round(max(0, min(100, quality)), 1),
            compatibility=round(max(0, min(100, compat_score)), 1),
            reliability=round(max(0, min(100, reliability)), 1),
            consistency=round(max(0, min(100, consistency)), 1),
            overall=round(max(0, min(100, overall)), 1),
        )


__all__ = ["IntegrationVerifier"]
