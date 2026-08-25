"""Backward-compatible message handler facade."""
from __future__ import annotations

from .routers.message_router import (
    _ensure_mongo_user,
    _mongo_plan_for_user,
    _persist_session,
    _plan_live_seconds,
    _rate_limit_ok,
    _rate_limit_wait_seconds,
    handle_message,
)

__all__ = [
    "handle_message",
    "_ensure_mongo_user",
    "_mongo_plan_for_user",
    "_persist_session",
    "_plan_live_seconds",
    "_rate_limit_ok",
    "_rate_limit_wait_seconds",
]
