"""User identity persistence — MongoDB only (no SQLite fallback)."""
from __future__ import annotations

import os

from ..config import logger
from ..session_store import get_session_store


def ensure_mongo_user(user) -> None:
    """Persist Telegram identity on every contact (create or touch last_seen).

    Requires MONGODB_URI. Users are stored in the Mongo ``users`` collection only.
    """
    if not user:
        return
    try:
        from lumen.platform.mongo_users import resolve_mongodb_uri as _rmu
        _mongo_ok = bool(_rmu())
    except Exception:
        _mongo_ok = bool((os.getenv("MONGODB_URI") or "").strip())
    if not _mongo_ok:
        logger.error(
            "MONGODB_URI missing — cannot persist user tg=%s (SQLite fallback removed)",
            getattr(user, "id", None),
        )
        return
    try:
        from lumen.platform.mongo_users import get_or_create_by_telegram

        name = (
            getattr(user, "full_name", None)
            or getattr(user, "username", None)
            or f"tg_{user.id}"
        )
        username = str(getattr(user, "username", None) or "")
        tenant, created = get_or_create_by_telegram(
            int(user.id),
            name=str(name)[:120],
            plan_id="free",
            username=username,
        )
        if created:
            logger.info(
                "mongo user created tg=%s tenant=%s plan=%s",
                user.id,
                getattr(tenant, "tenant_id", None),
                getattr(tenant, "plan_id", None),
            )
            try:
                from lumen.platform.credits.onboarding import grant_welcome_credits
                tid = str(getattr(tenant, "tenant_id", "") or f"tg:{int(user.id)}")
                grant_welcome_credits(tid)
            except Exception as grant_exc:
                logger.warning("welcome credits grant failed tg=%s: %s", user.id, grant_exc)
        else:
            logger.debug("mongo user touched tg=%s", user.id)
    except Exception as exc:
        logger.warning(
            "mongo user ensure failed tg=%s: %s:%s",
            getattr(user, "id", None),
            type(exc).__name__,
            str(exc)[:160],
        )


def mongo_plan_for_user(user_id: int) -> str | None:
    try:
        from lumen.platform.mongo_users import resolve_mongodb_uri as _rmu2
        if not _rmu2():
            return None
    except Exception:
        if not (os.getenv("MONGODB_URI") or "").strip():
            return None
    try:
        from lumen.platform.tenants import get_tenant_store

        store = get_tenant_store()
        if hasattr(store, "get_by_telegram"):
            tenant = store.get_by_telegram(int(user_id))
            return tenant.plan_id if tenant else None
    except Exception:
        return None
    return None


def plan_live_seconds(user) -> int:
    try:
        from lumen.platform.plan_gate import live_seconds_for_user

        return int(live_seconds_for_user(user_id=int(user.id) if user else 0))
    except Exception:
        return 30 * 60


def persist_session(user, context) -> None:
    try:
        if user and context.user_data is not None:
            get_session_store().save(int(user.id), context.user_data)
    except Exception:
        pass
