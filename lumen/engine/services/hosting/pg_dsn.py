"""Canonical Postgres DSN for hosting control-plane stores."""
from __future__ import annotations

import os


def database_url() -> str:
    """Prefer TBE_DATABASE_URL, then platform.runtime_config.database_url()."""
    explicit = (os.getenv("TBE_DATABASE_URL") or "").strip()
    if explicit:
        return explicit
    try:
        from lumen.platform.runtime_config import database_url as _rc_db
        return (_rc_db() or "").strip()
    except Exception:
        return (
            (os.getenv("DATABASE_URL") or "")
            or (os.getenv("POSTGRES_URL") or "")
            or (os.getenv("POSTGRESQL_URL") or "")
        ).strip()


def available() -> bool:
    u = database_url().lower()
    return u.startswith("postgres://") or u.startswith("postgresql://")


_dsn = database_url

__all__ = ["database_url", "available", "_dsn"]
