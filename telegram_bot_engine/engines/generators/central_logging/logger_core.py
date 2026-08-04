"""
CentralLogger — Specification 058 (CRITICAL)

Central log sink: collect, redact, seal (immutable), search, rotate,
verify integrity. No engine may maintain its own log store.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from .data_readers import GenericData
from .report_data import (
    LogEntry, AuditRecord, SearchQuery, SearchHit, SearchReport,
    ArchiveRecord, IntegrityReport,
    CAT_EXECUTION, CAT_ENGINE, CAT_SECURITY, CAT_GIT, CAT_WORKSPACE,
    CAT_REPOSITORY, CAT_PERFORMANCE, CAT_SYSTEM, ALL_CATEGORIES,
    LEVEL_DEBUG, LEVEL_INFO, LEVEL_WARNING, LEVEL_ERROR, LEVEL_CRITICAL,
    ALL_LEVELS, LEVEL_RANK, SENSITIVE_KEYS,
)

_log = logging.getLogger("engine.central_logging.logger_core")

_MAX_ACTIVE_ENTRIES = 500
_ROTATE_THRESHOLD = 200
_REDACT_RE = re.compile(
    r"(?i)\b(" + "|".join(re.escape(k) for k in SENSITIVE_KEYS) + r")\b\s*[=:]\s*([^\s,;\"']+)",
)


class CentralLogger:
    """Collect, protect, search and archive platform logs."""

    def __init__(self) -> None:
        self._store: List[LogEntry] = []
        self._audit: List[AuditRecord] = []
        self._archives: List[ArchiveRecord] = []
        self._external_violations: int = 0

    def process(
        self,
        monitoring_data: GenericData,
        resource_data: GenericData,
        sync_data: GenericData,
        orch_data: GenericData,
        ctx_data: GenericData,
        workspace_data: GenericData,
        request_data: GenericData,
    ) -> Tuple[
        List[LogEntry],
        List[AuditRecord],
        SearchReport,
        IntegrityReport,
        List[ArchiveRecord],
        int,   # redacted_count
        bool,  # rotated
        int,   # external_log_violations
        bool,  # self_ok
    ]:
        events = self._collect_events(
            monitoring_data, resource_data, sync_data, orch_data,
            ctx_data, workspace_data, request_data,
        )
        redacted_count = 0
        entries: List[LogEntry] = []

        for ev in events:
            msg, n = self._redact(str(ev.get("message") or ""))
            redacted_count += n
            meta = self._redact_dict(ev.get("metadata") or {})
            redacted_count += meta[1]
            entry = self._seal(
                level=str(ev.get("level") or LEVEL_INFO),
                category=str(ev.get("category") or CAT_SYSTEM),
                engine_id=str(ev.get("engine_id") or ""),
                user_id=str(ev.get("user_id") or ""),
                project_id=str(ev.get("project_id") or ""),
                action=str(ev.get("action") or ""),
                message=msg,
                result=str(ev.get("result") or ""),
                metadata=meta[0],
            )
            entries.append(entry)
            self._store.append(entry)

        audit = self._build_audit(entries, request_data)
        self._audit.extend(audit)

        violations = self._detect_external_logs(request_data)
        self._external_violations += violations

        rotated = False
        if len(self._store) >= _ROTATE_THRESHOLD:
            archive = self._rotate()
            if archive:
                self._archives.append(archive)
                rotated = True

        search = self._search(entries, request_data)
        integrity = self._verify_integrity(entries)
        self_ok = self._self_verify(entries, integrity, violations)

        _log.info(
            "CentralLogger: entries=%d audit=%d redacted=%d rotated=%s violations=%d",
            len(entries), len(audit), redacted_count, rotated, violations,
        )
        return (
            entries, audit, search, integrity, list(self._archives),
            redacted_count, rotated, self._external_violations, self_ok,
        )

    def self_verify(
        self,
        entries: List[LogEntry],
        integrity: IntegrityReport,
        violations: int,
        self_ok: bool,
    ) -> bool:
        if not entries:
            return False
        if not integrity.verified and integrity.total_entries > 0:
            return False
        if violations > 0 and not any(
            e.category == CAT_SECURITY for e in entries
        ):
            return False
        return self_ok

    # ------------------------------------------------------------------

    def _collect_events(
        self,
        monitoring_data: GenericData,
        resource_data: GenericData,
        sync_data: GenericData,
        orch_data: GenericData,
        ctx_data: GenericData,
        workspace_data: GenericData,
        request_data: GenericData,
    ) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []

        # Explicit events from request
        for it in (request_data.items or []):
            if isinstance(it, dict):
                events.append(dict(it))
            elif isinstance(it, str):
                events.append({
                    "message": it, "level": LEVEL_INFO,
                    "category": CAT_SYSTEM, "engine_id": "user",
                })

        raw_req = request_data.raw or {}
        for key in ("events", "logs"):
            for it in (raw_req.get(key) or []):
                if isinstance(it, dict):
                    events.append(dict(it))

        # Monitoring alerts → logs
        for a in (monitoring_data.items or []):
            if not isinstance(a, dict):
                continue
            events.append({
                "level": LEVEL_ERROR if a.get("severity") == "critical" else LEVEL_WARNING,
                "category": CAT_SYSTEM,
                "engine_id": str(a.get("source") or "system_monitoring"),
                "action": "alert",
                "message": str(a.get("message") or a.get("kind") or "alert"),
                "result": str(a.get("kind") or ""),
            })

        # Resource usage anomalies
        for u in (resource_data.items or []):
            if isinstance(u, dict) and u.get("over_limit"):
                events.append({
                    "level": LEVEL_WARNING,
                    "category": CAT_PERFORMANCE,
                    "engine_id": str(u.get("engine_id") or "resource_management"),
                    "action": "resource_over_limit",
                    "message": f"Engine over limit: {u.get('engine_id')}",
                    "result": "over_limit",
                })

        # Sync events
        for e in (sync_data.items or []):
            if isinstance(e, dict):
                events.append({
                    "level": LEVEL_INFO,
                    "category": CAT_SYSTEM,
                    "engine_id": "synchronization",
                    "action": str(e.get("type") or "sync"),
                    "message": str(e.get("message") or e.get("type") or "sync event"),
                    "result": str(e.get("status") or "ok"),
                })

        # Orchestrator plan steps
        for p in (orch_data.items or [])[:20]:
            if isinstance(p, dict):
                events.append({
                    "level": LEVEL_INFO,
                    "category": CAT_EXECUTION,
                    "engine_id": str(p.get("engine_id") or p.get("id") or "orchestrator"),
                    "action": "plan_step",
                    "message": str(p.get("action") or p.get("name") or "step"),
                    "result": str(p.get("status") or "planned"),
                })
            elif isinstance(p, str):
                events.append({
                    "level": LEVEL_INFO,
                    "category": CAT_EXECUTION,
                    "engine_id": "orchestrator",
                    "action": "plan_step",
                    "message": p,
                    "result": "planned",
                })

        # Workspace
        if workspace_data.available:
            events.append({
                "level": LEVEL_INFO,
                "category": CAT_WORKSPACE,
                "engine_id": "workspace_management",
                "action": "workspace_snapshot",
                "message": "Workspace state recorded",
                "result": "ok",
            })

        # Always record a system heartbeat
        events.append({
            "level": LEVEL_INFO,
            "category": CAT_SYSTEM,
            "engine_id": "central_logging",
            "action": "heartbeat",
            "message": "Central logging cycle",
            "result": "ok",
            "user_id": str(raw_req.get("user_id") or ""),
            "project_id": str(raw_req.get("project_id") or ""),
        })

        # Inject security log if secrets appear in request
        blob = json.dumps(raw_req, default=str)
        if any(k in blob.lower() for k in SENSITIVE_KEYS):
            events.append({
                "level": LEVEL_WARNING,
                "category": CAT_SECURITY,
                "engine_id": "central_logging",
                "action": "sensitive_input_detected",
                "message": "Sensitive keys detected in input; values redacted",
                "result": "redacted",
            })

        return events

    def _redact(self, text: str) -> Tuple[str, int]:
        count = 0

        def _sub(m: re.Match) -> str:
            nonlocal count
            count += 1
            return f"{m.group(1)}=***REDACTED***"

        return _REDACT_RE.sub(_sub, text), count

    def _redact_dict(self, d: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        out: Dict[str, Any] = {}
        count = 0
        for k, v in d.items():
            if any(s in str(k).lower() for s in SENSITIVE_KEYS):
                out[k] = "***REDACTED***"
                count += 1
            elif isinstance(v, str):
                nv, n = self._redact(v)
                out[k] = nv
                count += n
            elif isinstance(v, dict):
                nv, n = self._redact_dict(v)
                out[k] = nv
                count += n
            else:
                out[k] = v
        return out, count

    def _seal(
        self,
        level: str,
        category: str,
        engine_id: str,
        user_id: str,
        project_id: str,
        action: str,
        message: str,
        result: str,
        metadata: Dict[str, Any],
    ) -> LogEntry:
        if level not in ALL_LEVELS:
            level = LEVEL_INFO
        if category not in ALL_CATEGORIES:
            category = CAT_SYSTEM
        ts = datetime.now(timezone.utc).isoformat()
        log_id = str(uuid.uuid4())
        payload = {
            "log_id": log_id,
            "timestamp": ts,
            "level": level,
            "category": category,
            "engine_id": engine_id,
            "user_id": user_id,
            "project_id": project_id,
            "action": action,
            "message": message,
            "result": result,
            "metadata": metadata,
        }
        checksum = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()
        return LogEntry(
            log_id=log_id,
            timestamp=ts,
            level=level,
            category=category,
            engine_id=engine_id,
            user_id=user_id,
            project_id=project_id,
            action=action,
            message=message,
            result=result,
            metadata=metadata,
            immutable=True,
            checksum=checksum,
        )

    def _build_audit(
        self,
        entries: List[LogEntry],
        request_data: GenericData,
    ) -> List[AuditRecord]:
        raw = request_data.raw or {}
        user = str(raw.get("user_id") or "system")
        project = str(raw.get("project_id") or "")
        trail: List[AuditRecord] = []
        for e in entries:
            if e.action in ("", "heartbeat"):
                continue
            trail.append(AuditRecord(
                audit_id=str(uuid.uuid4())[:12],
                timestamp=e.timestamp,
                user_id=e.user_id or user,
                engine_id=e.engine_id,
                action=e.action,
                result=e.result,
                project_id=e.project_id or project,
                details={"log_id": e.log_id, "level": e.level},
            ))
        # Always one audit for the logging cycle itself
        trail.append(AuditRecord(
            audit_id=str(uuid.uuid4())[:12],
            timestamp=datetime.now(timezone.utc).isoformat(),
            user_id=user,
            engine_id="central_logging",
            action="log_cycle",
            result="ok",
            project_id=project,
            details={"entries": len(entries)},
        ))
        return trail

    def _detect_external_logs(self, request_data: GenericData) -> int:
        """Detect attempts by engines to write outside central logging."""
        raw = request_data.raw or {}
        violations = 0
        external = raw.get("external_logs") or raw.get("side_channel_logs") or []
        if isinstance(external, list):
            violations += len(external)
        if raw.get("bypass_central_logging"):
            violations += 1
        return violations

    def _rotate(self) -> Optional[ArchiveRecord]:
        if len(self._store) < _ROTATE_THRESHOLD:
            return None
        # Archive older half
        cut = len(self._store) // 2
        batch = self._store[:cut]
        self._store = self._store[cut:]
        blob = json.dumps([e.to_dict() for e in batch], default=str)
        size = len(blob.encode())
        # Simulated compression ratio
        compressed_size = max(1, int(size * 0.4))
        return ArchiveRecord(
            archive_id=str(uuid.uuid4())[:12],
            created_at=datetime.now(timezone.utc).isoformat(),
            entry_count=len(batch),
            size_bytes=compressed_size,
            compressed=True,
            path=f"archives/logs_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json.gz",
        )

    def _search(
        self,
        entries: List[LogEntry],
        request_data: GenericData,
    ) -> SearchReport:
        raw = request_data.raw or {}
        qraw = raw.get("search") or {}
        if not isinstance(qraw, dict):
            qraw = {}
        query = SearchQuery(
            engine_id=str(qraw.get("engine_id") or ""),
            level=str(qraw.get("level") or ""),
            category=str(qraw.get("category") or ""),
            user_id=str(qraw.get("user_id") or ""),
            project_id=str(qraw.get("project_id") or ""),
            time_from=str(qraw.get("time_from") or ""),
            time_to=str(qraw.get("time_to") or ""),
            text=str(qraw.get("text") or ""),
            error_type=str(qraw.get("error_type") or ""),
        )
        # Default: search recent ERROR/CRITICAL if no query
        hits: List[SearchHit] = []
        for e in entries:
            score = 0.0
            if query.engine_id and e.engine_id == query.engine_id:
                score += 1.0
            if query.level and e.level == query.level:
                score += 1.0
            if query.category and e.category == query.category:
                score += 1.0
            if query.user_id and e.user_id == query.user_id:
                score += 1.0
            if query.project_id and e.project_id == query.project_id:
                score += 1.0
            if query.text and query.text.lower() in e.message.lower():
                score += 1.5
            if query.error_type and query.error_type.lower() in (
                e.message.lower() + e.result.lower()
            ):
                score += 1.5
            # If no filters, include warnings+
            if not any([
                query.engine_id, query.level, query.category,
                query.user_id, query.project_id, query.text, query.error_type,
            ]):
                if LEVEL_RANK.get(e.level, 0) >= LEVEL_RANK[LEVEL_WARNING]:
                    score = 0.5
            if score > 0:
                hits.append(SearchHit(
                    log_id=e.log_id,
                    score=round(score, 2),
                    snippet=e.message[:120],
                ))
        hits.sort(key=lambda h: h.score, reverse=True)
        return SearchReport(query=query, hits=hits[:50], total=len(hits))

    def _verify_integrity(self, entries: List[LogEntry]) -> IntegrityReport:
        total = len(entries)
        valid = 0
        tampered = 0
        missing = 0
        for e in entries:
            if not e.checksum:
                missing += 1
                continue
            payload = {
                "log_id": e.log_id,
                "timestamp": e.timestamp,
                "level": e.level,
                "category": e.category,
                "engine_id": e.engine_id,
                "user_id": e.user_id,
                "project_id": e.project_id,
                "action": e.action,
                "message": e.message,
                "result": e.result,
                "metadata": e.metadata,
            }
            expected = hashlib.sha256(
                json.dumps(payload, sort_keys=True, default=str).encode()
            ).hexdigest()
            if expected == e.checksum:
                valid += 1
            else:
                tampered += 1
        verified = tampered == 0 and missing == 0 and total > 0
        msg = (
            "All log checksums valid."
            if verified
            else f"Integrity issues: tampered={tampered} missing={missing}"
        )
        return IntegrityReport(
            verified=verified,
            total_entries=total,
            valid_checksums=valid,
            tampered=tampered,
            missing_checksums=missing,
            message=msg,
        )

    def _self_verify(
        self,
        entries: List[LogEntry],
        integrity: IntegrityReport,
        violations: int,
    ) -> bool:
        if not entries:
            return False
        if not all(e.immutable for e in entries):
            return False
        if not integrity.verified:
            return False
        # Must have at least a system category entry (heartbeat)
        if not any(e.category == CAT_SYSTEM for e in entries):
            return False
        return True


__all__ = ["CentralLogger"]
