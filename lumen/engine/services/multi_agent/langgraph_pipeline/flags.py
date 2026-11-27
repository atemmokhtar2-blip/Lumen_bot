"""LangGraph pipeline flags and production-grade checkpoint persistence.

Production uses PostgreSQL so API replicas and RQ workers share checkpoints.
SQLite is a local-development option only; MemorySaver is a dev-only fallback.
"""
from __future__ import annotations

import atexit
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
_SHARED_CHECKPOINTER: Any | None = None


def _is_production_runtime() -> bool:
    from lumen.platform.runtime_config import is_dev

    return not is_dev()


def _checkpoint_db_path() -> Path:
    raw = (os.getenv("LANGGRAPH_CHECKPOINT_PATH") or "").strip()
    if raw:
        return Path(raw).expanduser()
    from lumen.platform.paths import sqlite_under_data

    return sqlite_under_data("langgraph_checkpoints.sqlite")


def _strict_checkpoint_serializer():
    """Allow only the concrete Lumen state types needed for graph recovery."""
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    from ..state import AgentEvent, AgentRole, AgentState, AgentStatus
    from ..task_tree import TaskNode, TaskRole, TaskStatus, TaskTree

    return JsonPlusSerializer(
        allowed_msgpack_modules=[
            AgentEvent,
            AgentRole,
            AgentState,
            AgentStatus,
            TaskNode,
            TaskRole,
            TaskStatus,
            TaskTree,
        ]
    )


def _postgres_checkpointer():
    """Create a shared PostgreSQL checkpointer and serialize first-time setup."""
    from langgraph.checkpoint.postgres import PostgresSaver

    from lumen.platform.postgres_pool import get_postgres_pool

    pool = get_postgres_pool()
    saver = PostgresSaver(pool, serde=_strict_checkpoint_serializer())

    # Multiple API/worker replicas can boot simultaneously. Serialize schema
    # migrations with a PostgreSQL advisory lock, without exposing the DSN.
    setup_lock_id = 72623859790382856
    with pool.connection(timeout=10) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (setup_lock_id,))
        try:
            saver.setup()
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (setup_lock_id,))

    logger.info("LangGraph PostgreSQL checkpointer ready")
    return saver


def _shared_checkpointer():
    """Return the shared saver; production never falls back to local or memory state.

    A worker and a Telegram/API process may run on different machines. Therefore
    a local SQLite file is not a valid production source of truth for HITL resume.
    """
    global _SHARED_CHECKPOINTER
    if _SHARED_CHECKPOINTER is not None:
        return _SHARED_CHECKPOINTER

    disabled = (os.getenv("MULTI_AGENT_CHECKPOINT") or "1").strip().lower() in {
        "0", "false", "no", "off",
    }
    production = _is_production_runtime()

    if disabled:
        if production and hitl_interrupt_enabled():
            raise RuntimeError(
                "production_hitl_requires_shared_postgres_checkpointer"
            )
        return None

    if production:
        try:
            _SHARED_CHECKPOINTER = _postgres_checkpointer()
            return _SHARED_CHECKPOINTER
        except Exception as exc:
            logger.exception("Production PostgreSQL checkpoint initialization failed")
            raise RuntimeError(
                "production_postgres_checkpointer_unavailable"
            ) from exc

    # Local development only: SQLite is durable across local process restarts.
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver

        db = _checkpoint_db_path()
        db.parent.mkdir(parents=True, exist_ok=True)
        import sqlite3

        conn = sqlite3.connect(str(db), check_same_thread=False)
        _SHARED_CHECKPOINTER = SqliteSaver(conn, serde=_strict_checkpoint_serializer())
        logger.info("LangGraph development SqliteSaver at %s", db)
        return _SHARED_CHECKPOINTER
    except Exception as exc:
        logger.warning("Development SqliteSaver unavailable (%s)", type(exc).__name__)

    try:
        from langgraph.checkpoint.memory import MemorySaver

        _SHARED_CHECKPOINTER = MemorySaver(serde=_strict_checkpoint_serializer())
        logger.warning("LangGraph using MemorySaver (development only; not durable)")
        return _SHARED_CHECKPOINTER
    except Exception as exc:
        logger.error("No LangGraph checkpointer available: %s", type(exc).__name__)
        return None


def close_shared_checkpointer() -> None:
    """Close shared database resources during graceful shutdown."""
    global _SHARED_CHECKPOINTER
    _SHARED_CHECKPOINTER = None
    try:
        from lumen.platform.postgres_pool import close_postgres_pool

        close_postgres_pool()
    except Exception:
        logger.exception("PostgreSQL pool shutdown failed")


atexit.register(close_shared_checkpointer)


def hitl_deliver_enabled() -> bool:
    """Second HITL gate before delivery when QA passed (default off)."""
    return (os.getenv("MULTI_AGENT_HITL_DELIVER") or "0").strip().lower() in {
        "1", "true", "yes", "on",
    }


def hitl_interrupt_enabled() -> bool:
    """Official LangGraph interrupt after plan; enabled by default when available."""
    flag = (os.getenv("MULTI_AGENT_LANGGRAPH_HITL") or "1").strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return False
    return langgraph_available()


def langgraph_available() -> bool:
    try:
        import langgraph  # noqa: F401
        from langgraph.graph import StateGraph  # noqa: F401

        return True
    except Exception:
        return False


def use_langgraph_pipeline() -> bool:
    try:
        from .production_policy import is_production

        if is_production():
            return True
    except Exception:
        pass
    flag = (os.getenv("MULTI_AGENT_LANGGRAPH") or "1").strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return False
    return langgraph_available()
