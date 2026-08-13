"""Mongo-backed user and durable session synchronization helpers."""
from __future__ import annotations

import os

from ..config import logger
from ..session_store import get_session_store


def ensure_mongo_user(user) -> None:
    """Persist Telegram identity and default plan when MongoDB is configured."""
    if not user or not (os.getenv("MONGODB_URI") or "").strip():
        return
    try:
        from b2b_platform.mongo_users import get_or_create_by_telegram
        name = (
            getattr(user, "full_name", None)
            or getattr(user, "username", None)
            or f"tg_{user.id}"
        )
        tenant, created = get_or_create_by_telegram(
            int(user.id), name=str(name)[:120], plan_id="free"
        )
        if created:
            logger.info(
                "mongo user created tg=%s tenant=%s plan=%s",
                user.id,
                tenant.tenant_id,
                tenant.plan_id,
            )
    except Exception as exc:
        logger.warning(
            "mongo user ensure failed tg=%s: %s",
            getattr(user, "id", None),
            type(exc).__name__,
        )


def mongo_plan_for_user(user_id: int) -> str | None:
    if not (os.getenv("MONGODB_URI") or "").strip():
        return None
    try:
        from b2b_platform.tenants import get_tenant_store
        store = get_tenant_store()
        if hasattr(store, "get_by_telegram"):
            tenant = store.get_by_telegram(int(user_id))
            return tenant.plan_id if tenant else None
    except Exception:
        return None
    return None


def plan_live_seconds(user) -> int:
    try:
        from b2b_platform.plan_gate import live_seconds_for_user
        return int(live_seconds_for_user(user_id=int(user.id) if user else 0))
    except Exception:
        return 30 * 60


def persist_session(user, context) -> None:
    try:
        if user and context.user_data is not None:
            get_session_store().save(int(user.id), context.user_data)
    except Exception:
        pass
