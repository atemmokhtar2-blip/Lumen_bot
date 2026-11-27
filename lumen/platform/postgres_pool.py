"""Shared, bounded PostgreSQL connection pool for durable platform state.

The pool is process-local; PostgreSQL remains the source of truth across
workers and API replicas. Never log the DSN or silently fall back to files.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any

logger = logging.getLogger(__name__)

_POOL: Any | None = None
_POOL_LOCK = threading.Lock()


def get_postgres_pool():
    """Return the process-wide psycopg pool, opening it lazily and fail-closed."""
    global _POOL
    if _POOL is not None:
        return _POOL

    from lumen.platform.runtime_config import database_url

    dsn = database_url()
    if not dsn:
        raise RuntimeError("DATABASE_URL_REQUIRED_FOR_DURABLE_STATE")

    try:
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool
    except ImportError as exc:
        raise RuntimeError(
            "PostgreSQL durable state requires psycopg and psycopg-pool"
        ) from exc

    try:
        max_size = max(2, min(32, int(os.getenv("LUMEN_DB_POOL_MAX_SIZE") or "10")))
        timeout = max(1.0, min(30.0, float(os.getenv("LUMEN_DB_POOL_TIMEOUT_SEC") or "10")))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("INVALID_POSTGRES_POOL_CONFIGURATION") from exc

    with _POOL_LOCK:
        if _POOL is not None:
            return _POOL
        pool = ConnectionPool(
            conninfo=dsn,
            min_size=1,
            max_size=max_size,
            kwargs={
                "autocommit": True,
                "prepare_threshold": 0,
                "row_factory": dict_row,
            },
            open=False,
            timeout=timeout,
        )
        try:
            pool.open(wait=True, timeout=timeout)
        except Exception:
            pool.close()
            logger.exception("PostgreSQL connection pool initialization failed")
            raise
        _POOL = pool
        logger.info("PostgreSQL connection pool ready (max_size=%s)", max_size)
        return _POOL


def close_postgres_pool() -> None:
    """Close the pool during graceful process shutdown; safe to call repeatedly."""
    global _POOL
    with _POOL_LOCK:
        pool, _POOL = _POOL, None
    if pool is not None:
        pool.close()
