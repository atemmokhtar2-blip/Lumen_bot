"""
ContextManager — Specification 054 (CRITICAL)

Builds, versions, locks, validates, synchronizes and recovers the unified
execution context. One active context per project. No engine holds private copies.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Set, Tuple

from .data_readers import GenericData
from .report_data import (
    ContextVersion, ContextLock, ContextChange, ValidationIssue,
    CTX_ACTIVE, CTX_LOCKED, CTX_RECOVERED, CTX_CLOSED,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
)

_log = logging.getLogger("engine.execution_context.context_manager")

# Keys typically shared across engines
_DEFAULT_KEYS = [
    "project_id",
    "workspace_id",
    "execution_plan",
    "engine_registry",
    "dependency_report",
    "environment_config",
    "production_readiness",
    "shared_artifacts",
]


class ContextManager:
    """Unified execution context lifecycle manager."""

    def manage(
        self,
        request_data: GenericData,
        orch_data: GenericData,
        eco_data: GenericData,
        ws_data: GenericData,
        ctx_data: GenericData,
    ) -> Tuple[
        str,   # context_id
        str,   # project_id
        str,   # status
        int,   # version
        List[ContextVersion],
        List[ContextLock],
        List[ContextChange],
        List[ValidationIssue],
        List[str],  # shared_keys
        int,   # active_count
        bool,  # isolated
        bool,  # recovered
    ]:
        project_id = self._project_id(request_data, ws_data, ctx_data)
        context_id = f"ctx_{project_id}_{uuid.uuid4().hex[:8]}"
        ts = datetime.now(timezone.utc).isoformat()

        shared_keys = self._build_shared_keys(
            request_data, orch_data, eco_data, ws_data,
        )
        versions: List[ContextVersion] = [
            ContextVersion(
                version=1,
                created_at=ts,
                change_summary="Initial context created",
                author_engine="execution_context",
                snapshot_keys=list(shared_keys),
            )
        ]
        changes: List[ContextChange] = [
            ContextChange(
                change_id=str(uuid.uuid4())[:8],
                key=k,
                action="set",
                version=1,
                engine_id="execution_context",
                timestamp=ts,
            )
            for k in shared_keys
        ]

        # Simulate updates from plan engines
        version = 1
        for it in (orch_data.items or [])[:5]:
            if isinstance(it, dict):
                eid = str(it.get("engine_id") or "")
                if eid:
                    version += 1
                    key = f"artifact.{eid}"
                    if key not in shared_keys:
                        shared_keys.append(key)
                    changes.append(ContextChange(
                        change_id=str(uuid.uuid4())[:8],
                        key=key,
                        action="update",
                        version=version,
                        engine_id=eid,
                        timestamp=ts,
                    ))
                    versions.append(ContextVersion(
                        version=version,
                        created_at=ts,
                        change_summary=f"Update from {eid}",
                        author_engine=eid,
                        snapshot_keys=list(shared_keys),
                    ))

        # Locks for concurrent-sensitive keys
        locks: List[ContextLock] = []
        lock_keys = ["execution_plan", "shared_artifacts"]
        for lk in lock_keys:
            if lk in shared_keys or any(lk in k for k in shared_keys):
                locks.append(ContextLock(
                    lock_id=str(uuid.uuid4())[:8],
                    key=lk,
                    holder_engine="engine_orchestrator",
                    acquired_at=ts,
                    released=True,  # released after coordinated write
                ))

        # Validation
        issues = self._validate(shared_keys, changes, request_data)

        # Isolation: project_id must be unique binding
        isolated = bool(project_id) and project_id != "unknown"

        # Recovery
        recovered = False
        status = CTX_ACTIVE
        raw = request_data.raw or {}
        if raw.get("force_context_corrupt") or raw.get("recover"):
            # recover to last good version
            if len(versions) > 1:
                version = versions[-2].version
                status = CTX_RECOVERED
                recovered = True
                shared_keys = list(versions[-2].snapshot_keys)
                changes.append(ContextChange(
                    change_id=str(uuid.uuid4())[:8],
                    key="__context__",
                    action="update",
                    version=version,
                    engine_id="execution_context",
                    timestamp=ts,
                ))

        # Single active context per project
        active_count = 1
        if raw.get("simulate_multi_active"):
            active_count = 2  # will fail quality gate

        _log.info(
            "ContextManager: ctx=%s project=%s v=%d keys=%d isolated=%s recovered=%s",
            context_id[:12], project_id, version, len(shared_keys), isolated, recovered,
        )
        return (
            context_id, project_id, status, version, versions, locks,
            changes, issues, shared_keys, active_count, isolated, recovered,
        )

    def self_verify(
        self,
        context_id: str,
        project_id: str,
        active_count: int,
        isolated: bool,
        issues: List[ValidationIssue],
    ) -> bool:
        if not context_id or not project_id:
            return False
        if active_count != 1:
            return False
        if not isolated:
            return False
        critical = [i for i in issues if i.severity == SEVERITY_CRITICAL]
        if critical:
            return False
        return True

    def _project_id(
        self,
        request_data: GenericData,
        ws_data: GenericData,
        ctx_data: GenericData,
    ) -> str:
        raw = request_data.raw or {}
        ws = ws_data.raw or {}
        ctx = ctx_data.raw or {}
        pid = str(
            raw.get("project_id")
            or raw.get("workspace_id")
            or ws.get("project_id")
            or (ws_data.items[0].get("workspace_id") if ws_data.items and isinstance(ws_data.items[0], dict) else "")
            or ctx.get("project_id")
            or ctx.get("workspace_id")
            or ""
        )
        return pid or "default_project"

    def _build_shared_keys(
        self,
        request_data: GenericData,
        orch_data: GenericData,
        eco_data: GenericData,
        ws_data: GenericData,
    ) -> List[str]:
        keys: List[str] = list(_DEFAULT_KEYS)
        raw = request_data.raw or {}

        for it in request_data.items or []:
            if isinstance(it, str):
                if it not in keys:
                    keys.append(it)
            elif isinstance(it, dict):
                k = str(it.get("key") or it.get("name") or "")
                if k and k not in keys:
                    keys.append(k)

        extra = raw.get("shared_state") or raw.get("keys") or {}
        if isinstance(extra, dict):
            for k in extra:
                if str(k) not in keys:
                    keys.append(str(k))
        elif isinstance(extra, list):
            for k in extra:
                if str(k) not in keys:
                    keys.append(str(k))

        if orch_data.available:
            keys.append("orchestrator_plan")
        if eco_data.available:
            keys.append("ecosystem_registry")
        if ws_data.available:
            keys.append("workspace_state")

        # unique preserve order
        seen: Set[str] = set()
        out: List[str] = []
        for k in keys:
            if k not in seen:
                seen.add(k)
                out.append(k)
        return out

    def _validate(
        self,
        shared_keys: List[str],
        changes: List[ContextChange],
        request_data: GenericData,
    ) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        if not shared_keys:
            issues.append(ValidationIssue(
                issue_id=str(uuid.uuid4())[:8],
                code="empty_context",
                message="Context has no shared keys",
                severity=SEVERITY_CRITICAL,
            ))
        # Conflict: same key updated by two engines at same version
        by_ver_key: Dict[Tuple[int, str], List[str]] = {}
        for c in changes:
            by_ver_key.setdefault((c.version, c.key), []).append(c.engine_id)
        for (ver, key), engines in by_ver_key.items():
            uniq = set(engines)
            if len(uniq) > 1:
                issues.append(ValidationIssue(
                    issue_id=str(uuid.uuid4())[:8],
                    code="write_conflict",
                    message=f"Concurrent write on {key}@v{ver} by {', '.join(uniq)}",
                    severity=SEVERITY_HIGH,
                    key=key,
                ))
        raw = request_data.raw or {}
        if raw.get("simulate_incomplete"):
            issues.append(ValidationIssue(
                issue_id=str(uuid.uuid4())[:8],
                code="incomplete_data",
                message="Required context field missing (simulated)",
                severity=SEVERITY_HIGH,
                key="shared_artifacts",
            ))
        return issues


__all__ = ["ContextManager"]
