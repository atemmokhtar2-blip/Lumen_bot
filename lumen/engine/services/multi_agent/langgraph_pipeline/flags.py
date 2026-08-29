"""LangGraph pipeline flags, checkpoint path, availability."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
_SHARED_CHECKPOINTER = None

def _checkpoint_db_path() -> Path:
    raw = (os.getenv("LANGGRAPH_CHECKPOINT_PATH") or "").strip()
    if raw:
        return Path(raw)
    base = (os.getenv("OUTPUT_DIR") or os.getenv("LUMEN_OUTPUT_DIR") or "/tmp/lumen_output").strip()
    return Path(base) / "langgraph_checkpoints.sqlite"


def _shared_checkpointer():
    """Official durable checkpointer: SqliteSaver first, MemorySaver fallback.

    Sqlite is process+restart durable (same machine). Required for real HITL resume
    after worker restart — Memory alone is not world-class.
    """
    global _SHARED_CHECKPOINTER
    if _SHARED_CHECKPOINTER is not None:
        return _SHARED_CHECKPOINTER
    if (os.getenv("MULTI_AGENT_CHECKPOINT") or "1").strip().lower() in {"0", "false", "no", "off"}:
        return None
    # Prefer official SqliteSaver
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
        import sqlite3
        db = _checkpoint_db_path()
        db.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db), check_same_thread=False)
        if hasattr(SqliteSaver, "from_conn"):
            _SHARED_CHECKPOINTER = SqliteSaver.from_conn(conn)
        else:
            _SHARED_CHECKPOINTER = SqliteSaver(conn)
        logger.info("LangGraph SqliteSaver at %s", db)
        return _SHARED_CHECKPOINTER
    except Exception as exc:
        logger.warning("SqliteSaver unavailable (%s) — trying MemorySaver", exc)
    try:
        from langgraph.checkpoint.memory import MemorySaver
        _SHARED_CHECKPOINTER = MemorySaver()
        logger.warning("LangGraph using MemorySaver (not durable across process restart)")
        return _SHARED_CHECKPOINTER
    except Exception as exc:
        logger.warning("No checkpointer: %s", exc)
        return None


def hitl_deliver_enabled() -> bool:
    """Second HITL gate before deliver when QA passed (default off)."""
    import os
    return (os.getenv("MULTI_AGENT_HITL_DELIVER") or "0").strip().lower() in {"1", "true", "yes", "on"}


def hitl_interrupt_enabled() -> bool:

    """Official LangGraph interrupt after plan. Default ON when langgraph available."""
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


