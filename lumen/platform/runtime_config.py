"""Single source of truth for production vs dev data-plane requirements.

Production (default when ENVIRONMENT is unset or production):
  DATABASE_URL  — PostgreSQL (tenants, metering, billing relational state)
  REDIS_URL     — rate limits, RQ job queue, job metadata

No file JSON, no SQLite, no Mongo, no in-process thread-pool jobs in production.
"""
from __future__ import annotations

import os


def environment() -> str:
    return (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "production").strip().lower()


def is_dev() -> bool:
    """Explicit dev only — deploy platform signals force production semantics."""
    try:
        from lumen.platform.tenants import _production_signals_present
        if _production_signals_present():
            return False
    except Exception:
        pass
    return environment() in {"dev", "development", "local", "test"}


def database_url() -> str:
    return (
        (os.getenv("DATABASE_URL") or "")
        or (os.getenv("POSTGRES_URL") or "")
        or (os.getenv("POSTGRESQL_URL") or "")
    ).strip()


def redis_url() -> str:
    """Normalize REDIS_URL — strip quotes and accidental ``redis-cli -u`` pastes.

    Correct value example:
      redis://default:PASSWORD@host:13903
    Not:
      redis-cli -u redis://default:PASSWORD@host:13903
    """
    raw = (os.getenv("JOB_REDIS_URL") or os.getenv("REDIS_URL") or "").strip()
    if not raw:
        return ""
    # strip wrapping quotes from secret UIs
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {"'", '"'}:
        raw = raw[1:-1].strip()
    # user pasted full redis-cli invocation
    lower = raw.lower()
    if "redis-cli" in lower and "redis://" in lower:
        idx = lower.find("redis://")
        raw = raw[idx:].strip()
    elif "redis-cli" in lower and "rediss://" in lower:
        idx = lower.find("rediss://")
        raw = raw[idx:].strip()
    # drop trailing flags after the URL
    for sep in (" -", " --", "\n", "\t"):
        if sep in raw and raw.startswith(("redis://", "rediss://")):
            raw = raw.split(sep, 1)[0].strip()
    return raw


def require_production_data_plane() -> None:
    """Raise if production is missing mandatory infrastructure or secrets."""
    if is_dev():
        return
    missing = []
    if not database_url():
        missing.append("DATABASE_URL (PostgreSQL)")
    if not redis_url():
        missing.append("REDIS_URL (Redis for RQ + rate limits — mandatory, no SQLite fallback)")
    if missing:
        raise RuntimeError(
            "Production data plane incomplete. Set: "
            + ", ".join(missing)
            + ". File/SQLite/Mongo backends are disabled outside ENVIRONMENT=dev."
        )
    # Auth pepper — refuse boot with missing/weak API_KEY_PEPPER
    try:
        from lumen.platform.tenants import require_api_key_pepper
        require_api_key_pepper()
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"API_KEY_PEPPER validation failed: {exc}") from exc


def allow_file_backends() -> bool:
    """File/SQLite backends only when explicit dev AND no managed infra forced."""
    if not is_dev():
        return False
    # If operator already configured Postgres/Redis in dev, prefer them.
    return True
