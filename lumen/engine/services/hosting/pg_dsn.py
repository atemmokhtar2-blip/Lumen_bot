"""Canonical Postgres DSN for hosting control-plane stores."""
from __future__ import annotations

import os


def database_url() -> str:
    return (os.getenv("TBE_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()


def available() -> bool:
    u = database_url().lower()
    return u.startswith("postgres://") or u.startswith("postgresql://")


_dsn = database_url

__all__ = ["database_url", "available", "_dsn"]
