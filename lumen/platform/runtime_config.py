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
    return environment() in {"dev", "development", "local", "test"}


def database_url() -> str:
    return (
        (os.getenv("DATABASE_URL") or "")
        or (os.getenv("POSTGRES_URL") or "")
        or (os.getenv("POSTGRESQL_URL") or "")
    ).strip()


def redis_url() -> str:
    return (os.getenv("JOB_REDIS_URL") or os.getenv("REDIS_URL") or "").strip()


def require_production_data_plane() -> None:
    """Raise if production is missing mandatory infrastructure."""
    if is_dev():
        return
    missing = []
    if not database_url():
        missing.append("DATABASE_URL (PostgreSQL)")
    if not redis_url():
        missing.append("REDIS_URL (Redis for RQ + rate limits)")
    if missing:
        raise RuntimeError(
            "Production data plane incomplete. Set: "
            + ", ".join(missing)
            + ". File/SQLite/Mongo backends are disabled outside ENVIRONMENT=dev."
        )


def allow_file_backends() -> bool:
    """File/SQLite backends only when explicit dev AND no managed infra forced."""
    if not is_dev():
        return False
    # If operator already configured Postgres/Redis in dev, prefer them.
    return True
