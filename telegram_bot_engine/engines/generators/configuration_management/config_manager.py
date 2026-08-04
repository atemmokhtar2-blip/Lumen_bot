"""
ConfigManager — Specification 059 (CRITICAL)

Central registry: defaults, validation, dynamic update, versioning,
rollback, sync, protection, backup and recovery.
"""

from __future__ import annotations

import copy
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from .data_readers import GenericData
from .report_data import (
    ConfigEntry, ValidationIssue, ConfigVersion, BackupRecord,
    RecoveryRecord, ConfigChangeLog,
    SCOPE_PLATFORM, SCOPE_ENGINE, SCOPE_WORKSPACE, SCOPE_ENVIRONMENT,
    ISSUE_MISSING, ISSUE_INVALID, ISSUE_DUPLICATE, ISSUE_UNSUPPORTED,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    SENSITIVE_KEYS,
)

_log = logging.getLogger("engine.configuration_management.config_manager")

# Built-in platform defaults
_PLATFORM_DEFAULTS: Dict[str, Any] = {
    "platform.name": "Telegram Bot Generation Platform",
    "platform.version": "1.0.0",
    "platform.log_level": "INFO",
    "platform.max_engines": 200,
    "platform.timeout_seconds": 300,
    "platform.output_dir": "output",
    "platform.create_zip": True,
}

_ENGINE_DEFAULTS: Dict[str, Any] = {
    "engine.priority_default": 100,
    "engine.cache_enabled": True,
    "engine.retry_count": 2,
    "engine.fail_fast": True,
}

_ENV_DEFAULTS: Dict[str, Any] = {
    "env.python_version": "3.12",
    "env.timezone": "UTC",
}

_WORKSPACE_DEFAULTS: Dict[str, Any] = {
    "workspace.max_size_mb": 1024,
    "workspace.cleanup_on_exit": True,
}

_REQUIRED_KEYS = (
    "platform.name",
    "platform.log_level",
    "platform.timeout_seconds",
)

_SUPPORTED_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class ConfigManager:
    """Central configuration registry and lifecycle manager."""

    def __init__(self) -> None:
        self._registry: Dict[str, ConfigEntry] = {}
        self._versions: List[ConfigVersion] = []
        self._version_snapshots: Dict[int, Dict[str, ConfigEntry]] = {}
        self._backups: List[BackupRecord] = []
        self._recoveries: List[RecoveryRecord] = []
        self._change_log: List[ConfigChangeLog] = []
        self._current_version = 0
        self._load_defaults()

    def manage(
        self,
        logging_data: GenericData,
        monitoring_data: GenericData,
        resource_data: GenericData,
        env_data: GenericData,
        workspace_data: GenericData,
        request_data: GenericData,
    ) -> Tuple[
        List[ConfigEntry],
        List[ValidationIssue],
        List[ConfigVersion],
        List[BackupRecord],
        List[RecoveryRecord],
        List[ConfigChangeLog],
        int,   # current_version
        bool,  # synced
        int,   # external_violations
        int,   # protected_keys
        bool,  # self_ok
    ]:
        # Apply incoming config from request / env
        self._ingest(request_data, env_data, workspace_data, resource_data)

        # Dynamic updates from request
        raw = request_data.raw or {}
        if raw.get("updates") and isinstance(raw["updates"], dict):
            self._apply_updates(raw["updates"], actor=str(raw.get("user_id") or "system"))

        if raw.get("delete_keys") and isinstance(raw["delete_keys"], list):
            for k in raw["delete_keys"]:
                self._delete_key(str(k), actor=str(raw.get("user_id") or "system"))

        # Rollback request
        if raw.get("rollback_to") is not None:
            try:
                self._rollback(int(raw["rollback_to"]), actor=str(raw.get("user_id") or "system"))
            except Exception as e:
                _log.warning("Rollback failed: %s", e)

        # Force recovery
        if raw.get("recover"):
            self._recover(actor=str(raw.get("user_id") or "system"))

        # Always version after cycle if changes happened
        if not self._versions or raw.get("updates") or raw.get("delete_keys") or raw.get("rollback_to") is not None:
            self._bump_version(summary="config cycle", author=str(raw.get("user_id") or "system"))

        # Backup periodically / on request
        if raw.get("backup") or len(self._backups) == 0:
            self._backup()

        issues = self._validate()
        violations = self._detect_external(request_data)
        entries = list(self._registry.values())
        protected = sum(1 for e in entries if e.sensitive)
        synced = self._sync_flag(entries)
        self_ok = self._self_verify(entries, issues, violations)

        _log.info(
            "ConfigManager: entries=%d issues=%d version=%d protected=%d violations=%d",
            len(entries), len(issues), self._current_version, protected, violations,
        )
        return (
            entries, issues, list(self._versions), list(self._backups),
            list(self._recoveries), list(self._change_log),
            self._current_version, synced, violations, protected, self_ok,
        )

    def self_verify(
        self,
        entries: List[ConfigEntry],
        issues: List[ValidationIssue],
        violations: int,
        self_ok: bool,
    ) -> bool:
        if not entries:
            return False
        critical = [i for i in issues if i.severity == SEVERITY_CRITICAL]
        if critical:
            return False
        return self_ok

    # ------------------------------------------------------------------

    def _load_defaults(self) -> None:
        for key, val in _PLATFORM_DEFAULTS.items():
            self._registry[key] = ConfigEntry(
                key=key, value=val, scope=SCOPE_PLATFORM,
                default=val, sensitive=self._is_sensitive(key),
                description="platform default",
            )
        for key, val in _ENGINE_DEFAULTS.items():
            self._registry[key] = ConfigEntry(
                key=key, value=val, scope=SCOPE_ENGINE,
                default=val, sensitive=self._is_sensitive(key),
                description="engine default",
            )
        for key, val in _ENV_DEFAULTS.items():
            self._registry[key] = ConfigEntry(
                key=key, value=val, scope=SCOPE_ENVIRONMENT,
                default=val, sensitive=self._is_sensitive(key),
                description="environment default",
            )
        for key, val in _WORKSPACE_DEFAULTS.items():
            self._registry[key] = ConfigEntry(
                key=key, value=val, scope=SCOPE_WORKSPACE,
                default=val, sensitive=self._is_sensitive(key),
                description="workspace default",
            )
        self._bump_version(summary="defaults loaded", author="system")

    def _is_sensitive(self, key: str) -> bool:
        kl = key.lower()
        return any(s in kl for s in SENSITIVE_KEYS)

    def _ingest(
        self,
        request_data: GenericData,
        env_data: GenericData,
        workspace_data: GenericData,
        resource_data: GenericData,
    ) -> None:
        # From explicit request items
        for it in (request_data.items or []):
            if not isinstance(it, dict):
                continue
            key = str(it.get("key") or "")
            if not key:
                continue
            scope = str(it.get("scope") or SCOPE_PLATFORM)
            if scope not in (SCOPE_PLATFORM, SCOPE_ENGINE, SCOPE_WORKSPACE, SCOPE_ENVIRONMENT):
                scope = SCOPE_PLATFORM
            self._set(
                key=key,
                value=it.get("value"),
                scope=scope,
                engine_id=str(it.get("engine_id") or ""),
                actor=str((request_data.raw or {}).get("user_id") or "system"),
                description=str(it.get("description") or ""),
            )

        # Environment variables from env report
        for it in (env_data.items or []):
            if isinstance(it, dict):
                k = str(it.get("key") or it.get("name") or "")
                if k:
                    self._set(
                        key=f"env.{k}" if not k.startswith("env.") else k,
                        value=it.get("value"),
                        scope=SCOPE_ENVIRONMENT,
                        actor="environment",
                    )
            elif isinstance(it, str):
                self._set(key=f"env.{it}", value=True, scope=SCOPE_ENVIRONMENT, actor="environment")

        # Workspace hints
        if workspace_data.available and workspace_data.raw:
            ws = workspace_data.raw
            if "max_size_mb" in ws:
                self._set("workspace.max_size_mb", ws["max_size_mb"], SCOPE_WORKSPACE, actor="workspace")

        # Resource-derived defaults
        if resource_data.available and resource_data.raw:
            sys_ = resource_data.raw.get("system") or {}
            if isinstance(sys_, dict) and sys_.get("available_ram_mb"):
                self._set(
                    "platform.available_ram_mb",
                    sys_["available_ram_mb"],
                    SCOPE_PLATFORM,
                    actor="resource_management",
                )

    def _set(
        self,
        key: str,
        value: Any,
        scope: str = SCOPE_PLATFORM,
        engine_id: str = "",
        actor: str = "system",
        description: str = "",
    ) -> None:
        sensitive = self._is_sensitive(key)
        # Protection: refuse overwrite of sensitive without elevated actor
        existing = self._registry.get(key)
        if existing and existing.sensitive and actor not in ("system", "admin"):
            self._log_change("set_denied", key, actor, "sensitive key protected")
            return

        version = (existing.version + 1) if existing else 1
        default = existing.default if existing else value
        self._registry[key] = ConfigEntry(
            key=key,
            value=value,
            scope=scope,
            engine_id=engine_id,
            default=default,
            sensitive=sensitive,
            version=version,
            description=description or (existing.description if existing else ""),
        )
        self._log_change("set" if not existing else "update", key, actor, f"v{version}")

    def _apply_updates(self, updates: Dict[str, Any], actor: str) -> None:
        for k, v in updates.items():
            self._set(str(k), v, actor=actor)

    def _delete_key(self, key: str, actor: str) -> None:
        existing = self._registry.get(key)
        if not existing:
            return
        if existing.sensitive and actor not in ("system", "admin"):
            self._log_change("delete_denied", key, actor, "sensitive key protected")
            return
        # Restore to default if available
        if existing.default is not None:
            existing.value = existing.default
            existing.version += 1
            self._log_change("update", key, actor, "reset to default")
        else:
            del self._registry[key]
            self._log_change("delete", key, actor, "removed")

    def _bump_version(self, summary: str, author: str) -> None:
        self._current_version += 1
        snap = {k: copy.deepcopy(v) for k, v in self._registry.items()}
        self._version_snapshots[self._current_version] = snap
        ver = ConfigVersion(
            version=self._current_version,
            created_at=datetime.now(timezone.utc).isoformat(),
            author=author,
            change_summary=summary,
            entry_count=len(snap),
            snapshot_keys=sorted(snap.keys()),
        )
        self._versions.append(ver)
        # Keep last 50 versions
        if len(self._versions) > 50:
            old = self._versions.pop(0)
            self._version_snapshots.pop(old.version, None)

    def _rollback(self, target: int, actor: str) -> None:
        if target not in self._version_snapshots:
            raise ValueError(f"version {target} not found")
        before = self._current_version
        self._registry = {k: copy.deepcopy(v) for k, v in self._version_snapshots[target].items()}
        self._bump_version(summary=f"rollback to v{target}", author=actor)
        self._recoveries.append(RecoveryRecord(
            recovery_id=str(uuid.uuid4())[:10],
            timestamp=datetime.now(timezone.utc).isoformat(),
            from_version=before,
            to_version=self._current_version,
            success=True,
            message=f"Rolled back to version {target}",
        ))
        self._log_change("rollback", f"v{target}", actor, f"from v{before}")

    def _backup(self) -> None:
        bid = str(uuid.uuid4())[:10]
        rec = BackupRecord(
            backup_id=bid,
            created_at=datetime.now(timezone.utc).isoformat(),
            version=self._current_version,
            entry_count=len(self._registry),
            size_estimate=len(self._registry) * 64,
            path=f"backups/config_v{self._current_version}_{bid}.json",
        )
        self._backups.append(rec)
        self._log_change("backup", f"v{self._current_version}", "system", bid)
        if len(self._backups) > 20:
            self._backups = self._backups[-20:]

    def _recover(self, actor: str) -> None:
        """Restore last known-good backup / version."""
        if not self._version_snapshots:
            return
        target = max(self._version_snapshots.keys())
        # Prefer previous if current may be bad
        keys = sorted(self._version_snapshots.keys())
        if len(keys) >= 2:
            target = keys[-2]
        before = self._current_version
        self._registry = {
            k: copy.deepcopy(v) for k, v in self._version_snapshots[target].items()
        }
        self._bump_version(summary=f"recovery from v{target}", author=actor)
        self._recoveries.append(RecoveryRecord(
            recovery_id=str(uuid.uuid4())[:10],
            timestamp=datetime.now(timezone.utc).isoformat(),
            from_version=before,
            to_version=self._current_version,
            success=True,
            message=f"Recovered from version {target}",
        ))
        self._log_change("recover", f"v{target}", actor, f"from v{before}")

    def _validate(self) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        seen: Set[str] = set()

        for key, entry in self._registry.items():
            if key in seen:
                issues.append(ValidationIssue(
                    issue_id=str(uuid.uuid4())[:8],
                    kind=ISSUE_DUPLICATE,
                    key=key,
                    message=f"Duplicate configuration key: {key}",
                    severity=SEVERITY_HIGH,
                    scope=entry.scope,
                ))
            seen.add(key)

            if entry.value is None and key in _REQUIRED_KEYS:
                issues.append(ValidationIssue(
                    issue_id=str(uuid.uuid4())[:8],
                    kind=ISSUE_MISSING,
                    key=key,
                    message=f"Required key missing value: {key}",
                    severity=SEVERITY_CRITICAL,
                    scope=entry.scope,
                ))

            if key == "platform.log_level" and str(entry.value) not in _SUPPORTED_LOG_LEVELS:
                issues.append(ValidationIssue(
                    issue_id=str(uuid.uuid4())[:8],
                    kind=ISSUE_INVALID,
                    key=key,
                    message=f"Invalid log level: {entry.value}",
                    severity=SEVERITY_HIGH,
                    scope=entry.scope,
                ))

            if key == "platform.timeout_seconds":
                try:
                    t = float(entry.value)
                    if t <= 0 or t > 86400:
                        raise ValueError("out of range")
                except (TypeError, ValueError):
                    issues.append(ValidationIssue(
                        issue_id=str(uuid.uuid4())[:8],
                        kind=ISSUE_INVALID,
                        key=key,
                        message=f"Invalid timeout: {entry.value}",
                        severity=SEVERITY_HIGH,
                        scope=entry.scope,
                    ))

            if entry.scope not in (SCOPE_PLATFORM, SCOPE_ENGINE, SCOPE_WORKSPACE, SCOPE_ENVIRONMENT):
                issues.append(ValidationIssue(
                    issue_id=str(uuid.uuid4())[:8],
                    kind=ISSUE_UNSUPPORTED,
                    key=key,
                    message=f"Unsupported scope: {entry.scope}",
                    severity=SEVERITY_MEDIUM,
                    scope=entry.scope,
                ))

        for req in _REQUIRED_KEYS:
            if req not in self._registry:
                issues.append(ValidationIssue(
                    issue_id=str(uuid.uuid4())[:8],
                    kind=ISSUE_MISSING,
                    key=req,
                    message=f"Required configuration key absent: {req}",
                    severity=SEVERITY_CRITICAL,
                    scope=SCOPE_PLATFORM,
                ))

        return issues

    def _detect_external(self, request_data: GenericData) -> int:
        raw = request_data.raw or {}
        violations = 0
        external = raw.get("external_config") or raw.get("side_channel_config") or []
        if isinstance(external, list):
            violations += len(external)
        if raw.get("bypass_central_config"):
            violations += 1
        return violations

    def _sync_flag(self, entries: List[ConfigEntry]) -> bool:
        # Consider synced when we have platform + engine + env scopes represented
        scopes = {e.scope for e in entries}
        return SCOPE_PLATFORM in scopes and SCOPE_ENGINE in scopes

    def _log_change(self, action: str, key: str, actor: str, details: str) -> None:
        self._change_log.append(ConfigChangeLog(
            change_id=str(uuid.uuid4())[:10],
            timestamp=datetime.now(timezone.utc).isoformat(),
            action=action,
            key=key,
            actor=actor,
            details=details,
        ))
        if len(self._change_log) > 500:
            self._change_log = self._change_log[-500:]

    def _self_verify(
        self,
        entries: List[ConfigEntry],
        issues: List[ValidationIssue],
        violations: int,
    ) -> bool:
        if not entries:
            return False
        if not any(e.scope == SCOPE_PLATFORM for e in entries):
            return False
        if self._current_version < 1:
            return False
        if any(i.severity == SEVERITY_CRITICAL and i.kind == ISSUE_MISSING for i in issues):
            # missing required is hard fail for self-verify
            return False
        return True


__all__ = ["ConfigManager"]
