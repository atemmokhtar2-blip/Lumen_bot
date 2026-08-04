"""BlueprintBuilder — Specification 060"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    SecurityPermissionReport, PermissionGrant, RoleAssignment, AccessCheck,
    IsolationViolation, AuthRecord, SecurityAuditEntry, RecoveryAction,
    CacheInfo, SecurityProvenance,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.security_permission.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        grants: List[PermissionGrant],
        roles: List[RoleAssignment],
        access_checks: List[AccessCheck],
        isolation_violations: List[IsolationViolation],
        auth_records: List[AuthRecord],
        audit_trail: List[SecurityAuditEntry],
        recoveries: List[RecoveryAction],
        sources_used: List[str],
        sources_missing: List[str],
        unauthorized_attempts: int = 0,
        recovered: bool = False,
        self_verification_passed: bool = False,
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> SecurityPermissionReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        denied = sum(1 for c in access_checks if not c.allowed)
        report = SecurityPermissionReport(
            report_id=str(uuid.uuid4()),
            grants=grants,
            roles=roles,
            access_checks=access_checks,
            isolation_violations=isolation_violations,
            auth_records=auth_records,
            audit_trail=audit_trail,
            recoveries=recoveries,
            findings=[],
            engine_count=len(roles),
            denied_count=denied,
            violation_count=len(isolation_violations),
            unauthorized_attempts=unauthorized_attempts,
            recovered=recovered,
            self_verification_passed=self_verification_passed,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=SecurityProvenance(
                engine_name="security_permission",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
                self_verification_passed=self_verification_passed,
            ),
            is_empty=len(roles) == 0,
        )
        _log.info(
            "BlueprintBuilder produced %s (engines=%d denied=%d violations=%d)",
            report.report_id[:8], len(roles), denied, len(isolation_violations),
        )
        return report


__all__ = ["BlueprintBuilder"]
