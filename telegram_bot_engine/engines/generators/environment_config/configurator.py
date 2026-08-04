"""
EnvironmentConfigurator — Specification 051 (ULTRA CRITICAL)

Builds Dev/Test/Staging/Production profiles, manages .env templates,
isolates secrets, validates consistency, runs health checks, backs up config.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Set, Tuple

from .data_readers import GenericData
from .report_data import (
    EnvVariable, EnvironmentProfile, HealthCheck, ConfigBackup, EnvScore,
    ENV_DEVELOPMENT, ENV_TESTING, ENV_STAGING, ENV_PRODUCTION, ALL_ENVIRONMENTS,
    STATUS_OK, STATUS_MISSING, STATUS_UNSAFE, STATUS_FAILED,
)

_log = logging.getLogger("engine.environment_config.configurator")

# Core variables expected for a Telegram bot project
_CORE_VARS = [
    ("BOT_TOKEN", True, True),          # secret
    ("APP_ENV", True, False),
    ("LOG_LEVEL", False, False),
    ("DATABASE_URL", False, True),      # secret-ish
    ("REDIS_URL", False, False),
    ("API_BASE_URL", False, False),
    ("WEBHOOK_URL", False, False),
    ("ADMIN_IDS", False, False),
]

_SECRET_HINTS = re.compile(
    r"(token|secret|password|passwd|api[_-]?key|private[_-]?key|credential)",
    re.IGNORECASE,
)

_UNSAFE_PATTERNS = [
    re.compile(r"^(password|123456|admin|secret)$", re.I),
    re.compile(r"^sk_live_"),  # live stripe-like keys in non-prod
]


class EnvironmentConfigurator:
    """Build, validate and protect environment configurations."""

    def configure(
        self,
        request_data: GenericData,
        ctx_data: GenericData,
        dep_data: GenericData,
        fs_data: GenericData,
    ) -> Tuple[
        List[EnvironmentProfile],
        List[EnvVariable],
        List[HealthCheck],
        List[ConfigBackup],
        EnvScore,
        str,   # detected_environment
        bool,  # secrets_isolated
    ]:
        language, framework, project_type, target = self._meta(request_data, ctx_data)
        detected = self._detect_environment(request_data, target)
        provided = self._collect_variables(request_data)

        variables: List[EnvVariable] = []
        secrets_isolated = True
        seen_names: Set[str] = set()

        # Build variable set per environment
        for env in ALL_ENVIRONMENTS:
            for name, required, is_secret in _CORE_VARS:
                key = f"{env}:{name}"
                if key in seen_names:
                    continue
                seen_names.add(key)
                present = name in provided or f"{env}_{name}" in provided
                raw_val = provided.get(name) or provided.get(f"{env}_{name}") or ""
                # Secrets must NOT come from repo files — only environment
                if is_secret and present and provided.get(f"_source_{name}") == "repo":
                    secrets_isolated = False
                    present = False  # treat as missing until loaded from env
                safe = self._is_safe(name, str(raw_val), env, is_secret)
                variables.append(EnvVariable(
                    name=name,
                    value_present=present,
                    is_secret=is_secret or bool(_SECRET_HINTS.search(name)),
                    environment=env,
                    source="environment" if is_secret else "env_template",
                    required=required or env == ENV_PRODUCTION,
                    safe=safe,
                    masked_preview="***" if (is_secret and present) else (
                        str(raw_val)[:8] if present and raw_val else ""
                    ),
                ))

        # Extra user-declared vars
        for name, val in provided.items():
            if name.startswith("_"):
                continue
            if any(v.name == name for v in variables):
                continue
            is_secret = bool(_SECRET_HINTS.search(name))
            variables.append(EnvVariable(
                name=name,
                value_present=bool(val),
                is_secret=is_secret,
                environment=detected,
                source="user_request",
                required=False,
                safe=self._is_safe(name, str(val), detected, is_secret),
                masked_preview="***" if is_secret else str(val)[:12],
            ))

        # Profiles
        profiles: List[EnvironmentProfile] = []
        for env in ALL_ENVIRONMENTS:
            env_vars = [v for v in variables if v.environment == env]
            names = [v.name for v in env_vars]
            missing_req = [v for v in env_vars if v.required and not v.value_present]
            profiles.append(EnvironmentProfile(
                name=env,
                active=(env == detected),
                variables=names,
                complete=len(missing_req) == 0,
                consistent=True,  # refined below
                health_ok=False,
            ))

        # Consistency: required var sets should align across envs (names)
        base_required = {
            v.name for v in variables
            if v.environment == ENV_DEVELOPMENT and v.required
        }
        for p in profiles:
            env_required = {
                v.name for v in variables
                if v.environment == p.name and v.required
            }
            if base_required and env_required and base_required != env_required:
                # Production may require more — OK if superset
                if not env_required.issuperset(base_required) and p.name != ENV_PRODUCTION:
                    p.consistent = False

        # Health checks (logical)
        health_checks = self._health_checks(request_data, dep_data, detected)
        health_ok = all(h.status == STATUS_OK for h in health_checks)
        for p in profiles:
            if p.name == detected:
                p.health_ok = health_ok

        # Backup
        ts = datetime.now(timezone.utc).isoformat()
        backups = [
            ConfigBackup(
                backup_id=str(uuid.uuid4())[:8],
                environment=detected,
                created_at=ts,
                item_count=len([v for v in variables if v.environment == detected]),
            )
        ]

        score = self._score(profiles, variables, health_checks, secrets_isolated)
        _log.info(
            "EnvironmentConfigurator: profiles=%d vars=%d detected=%s secrets_ok=%s score=%.1f",
            len(profiles), len(variables), detected, secrets_isolated, score.overall,
        )
        return profiles, variables, health_checks, backups, score, detected, secrets_isolated

    def self_verify(
        self,
        profiles: List[EnvironmentProfile],
        variables: List[EnvVariable],
        secrets_isolated: bool,
        score: EnvScore,
    ) -> bool:
        if not secrets_isolated:
            return False
        # Production must be complete
        prod = next((p for p in profiles if p.name == ENV_PRODUCTION), None)
        if prod and not prod.complete:
            return False
        if score.security < 70.0:
            return False
        return True

    def _meta(
        self, request_data: GenericData, ctx_data: GenericData
    ) -> Tuple[str, str, str, str]:
        raw = request_data.raw or {}
        ctx = ctx_data.raw or {}
        language = str(raw.get("language") or ctx.get("language") or "python")
        framework = str(raw.get("framework") or ctx.get("framework") or "python-telegram-bot")
        project_type = str(raw.get("project_type") or ctx.get("project_type") or "telegram_bot")
        target = str(
            raw.get("deployment_target") or raw.get("target") or raw.get("environment")
            or ctx.get("environment") or ENV_DEVELOPMENT
        ).lower()
        return language, framework, project_type, target

    def _detect_environment(self, request_data: GenericData, target: str) -> str:
        raw = request_data.raw or {}
        explicit = str(raw.get("APP_ENV") or raw.get("environment") or target or "").lower()
        for env in ALL_ENVIRONMENTS:
            if explicit == env or explicit.startswith(env[:4]):
                return env
        if explicit in ("prod", "production"):
            return ENV_PRODUCTION
        if explicit in ("stage", "staging"):
            return ENV_STAGING
        if explicit in ("test", "testing", "ci"):
            return ENV_TESTING
        return ENV_DEVELOPMENT

    def _collect_variables(self, request_data: GenericData) -> Dict[str, str]:
        out: Dict[str, str] = {}
        raw = request_data.raw or {}
        # From items
        for it in request_data.items or []:
            if isinstance(it, dict):
                name = str(it.get("name") or it.get("key") or "")
                val = str(it.get("value") or it.get("val") or "")
                if name:
                    out[name] = val
                    if it.get("source"):
                        out[f"_source_{name}"] = str(it.get("source"))
            elif isinstance(it, str) and "=" in it:
                k, v = it.split("=", 1)
                out[k.strip()] = v.strip()
        # From env dict
        env_dict = raw.get("env") or raw.get("variables") or {}
        if isinstance(env_dict, dict):
            for k, v in env_dict.items():
                out[str(k)] = str(v)
        # Direct common keys
        for k in ("BOT_TOKEN", "DATABASE_URL", "APP_ENV", "LOG_LEVEL", "REDIS_URL"):
            if raw.get(k) is not None:
                out[k] = str(raw.get(k))
        return out

    def _is_safe(self, name: str, value: str, env: str, is_secret: bool) -> bool:
        if not value:
            return True  # missing handled separately
        for pat in _UNSAFE_PATTERNS:
            if pat.search(value):
                return False
        # Live secrets in development are discouraged but not always unsafe
        if is_secret and env == ENV_DEVELOPMENT and value.startswith("sk_live"):
            return False
        return True

    def _health_checks(
        self, request_data: GenericData, dep_data: GenericData, env: str
    ) -> List[HealthCheck]:
        checks = []
        targets = ["database", "api", "storage", "cache", "queue"]
        raw = request_data.raw or {}
        for t in targets:
            # Logical: present config ⇒ ok; force_fail flag ⇒ failed
            status = STATUS_OK
            msg = f"{t} reachable (logical)"
            if raw.get("force_health_fail") or raw.get(f"fail_{t}"):
                status = STATUS_FAILED
                msg = f"{t} health check failed"
            elif t == "database" and not (
                raw.get("DATABASE_URL") or (raw.get("env") or {}).get("DATABASE_URL")
            ):
                # optional in dev
                if env == ENV_PRODUCTION:
                    status = STATUS_MISSING
                    msg = "DATABASE_URL missing in production"
            checks.append(HealthCheck(
                check_id=str(uuid.uuid4())[:8],
                target=t,
                status=status,
                message=msg,
            ))
        return checks

    def _score(
        self,
        profiles: List[EnvironmentProfile],
        variables: List[EnvVariable],
        health_checks: List[HealthCheck],
        secrets_isolated: bool,
    ) -> EnvScore:
        total_vars = max(1, len(variables))
        required = [v for v in variables if v.required]
        present_req = sum(1 for v in required if v.value_present)
        completeness = 100.0 * present_req / max(1, len(required))

        security = 100.0
        if not secrets_isolated:
            security -= 40.0
        unsafe = sum(1 for v in variables if not v.safe)
        security = max(0.0, security - unsafe * 15.0)
        secrets_in_log_risk = sum(
            1 for v in variables if v.is_secret and v.masked_preview not in ("", "***")
        )
        security = max(0.0, security - secrets_in_log_risk * 10.0)

        consistent = sum(1 for p in profiles if p.consistent)
        consistency = 100.0 * consistent / max(1, len(profiles))

        health_ok = sum(1 for h in health_checks if h.status == STATUS_OK)
        reliability = 100.0 * health_ok / max(1, len(health_checks))

        overall = round(
            security * 0.35 + completeness * 0.25 + consistency * 0.20 + reliability * 0.20, 1
        )
        return EnvScore(
            security=round(security, 1),
            completeness=round(completeness, 1),
            consistency=round(consistency, 1),
            reliability=round(reliability, 1),
            overall=overall,
        )


__all__ = ["EnvironmentConfigurator"]
