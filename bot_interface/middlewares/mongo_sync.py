"""User identity persistence: Mongo when configured, else local SQLite fallback."""
from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

from ..config import logger
from ..session_store import get_session_store


def _local_users_db() -> Path:
    base = Path(os.getenv("OUTPUT_DIR") or os.getenv("DATA_DIR") or "/tmp/maestro_data")
    base.mkdir(parents=True, exist_ok=True)
    return base / "maestro_users.sqlite3"


def _ensure_local_user(user) -> None:
    """Always persist Telegram users locally (survives bot block/rejoin)."""
    if not user:
        return
    uid = int(getattr(user, "id", 0) or 0)
    if uid <= 0:
        return
    name = (
        getattr(user, "full_name", None)
        or getattr(user, "username", None)
        or f"tg_{uid}"
    )
    username = str(getattr(user, "username", None) or "")[:64]
    path = _local_users_db()
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS telegram_users (
                user_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                username TEXT NOT NULL DEFAULT '',
                first_seen_at REAL NOT NULL,
                last_seen_at REAL NOT NULL,
                visit_count INTEGER NOT NULL DEFAULT 1,
                active INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        now = time.time()
        row = conn.execute(
            "SELECT user_id FROM telegram_users WHERE user_id=?", (uid,)
        ).fetchone()
        if row:
            conn.execute(
                """
                UPDATE telegram_users
                SET name=?, username=?, last_seen_at=?, visit_count=visit_count+1, active=1
                WHERE user_id=?
                """,
                (str(name)[:120], username, now, uid),
            )
        else:
            conn.execute(
                """
                INSERT INTO telegram_users
                (user_id, name, username, first_seen_at, last_seen_at, visit_count, active)
                VALUES (?, ?, ?, ?, ?, 1, 1)
                """,
                (uid, str(name)[:120], username, now, now),
            )
        conn.commit()
    finally:
        conn.close()


def ensure_mongo_user(user) -> None:
    """Persist Telegram identity on every contact (create or touch last_seen)."""
    if not user:
        return
    # Local SQLite always — works even without Mongo / after user deleted the bot
    try:
        _ensure_local_user(user)
    except Exception as exc:
        logger.warning("local user ensure failed: %s", type(exc).__name__)

    if not (os.getenv("MONGODB_URI") or "").strip():
        return
    try:
        from b2b_platform.mongo_users import get_or_create_by_telegram

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
                tenant.tenant_id,
                tenant.plan_id,
            )
        else:
            logger.debug("mongo user touched tg=%s", user.id)
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
