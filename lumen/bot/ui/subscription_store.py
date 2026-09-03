"""Permanent subscription persistence — MongoDB source of truth + Redis cache.

SECURITY MODEL
--------------
The Pro subscription is a **paid entitlement**.  Losing it means a paying user
is denied service; forging it means a non-paying user gets free resources.

Therefore the subscription MUST live in a **permanent, networked database**
(MongoDB ``users`` collection) — NOT only in Redis (which has a 30-day TTL and
can be flushed / evicted under memory pressure).

This module is the SINGLE write-path and SINGLE read-path for the durable
subscription record:

  write_subscription(user_id, record)
      → MongoDB  users.metadata.pro_subscription  (permanent, no TTL)
      → Redis    lumen:tg:session:{uid}.pro_plan   (fast-read cache)

  read_subscription(user_id)
      → Redis first (fast path)
      → MongoDB fallback if Redis miss / flush / key expired
      → Re-populate Redis from MongoDB on fallback (self-healing)

  delete_subscription(user_id)   — admin / refund only
      → Removes from both MongoDB and Redis.

Redis is a **cache** for the subscription, not the source of truth.
MongoDB is the source of truth.  This means:

  • Redis flush / restart / TTL expiry  → subscription survives (MongoDB).
  • User deletes the bot and re-enters  → subscription survives (MongoDB).
  • Multi-worker / multi-replica        → all workers read same MongoDB.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger("lumen_bot.subscription_store")

# MongoDB field path: users.metadata.pro_subscription
_MONGO_META_FIELD = "pro_subscription"

# Resolve get_session_store dynamically so that tests (and production) can
# monkeypatch ``lumen.bot.session_store.get_session_store`` and have the change
# propagate here.  A module-level ``from … import`` would capture the original
# function object and ignore later reassignments of the module attribute.
def _get_session_store():
    """Return the active SessionStore (dynamically resolved each call).

    This indirection is intentional: it lets callers — including tests — patch
    ``lumen.bot.session_store.get_session_store`` and have every read/write in
    this module pick up the patched factory.  A static ``from … import`` would
    bind the *original* function at import time and silently ignore patches.
    """
    try:
        import lumen.bot.session_store as _ss_mod
        return _ss_mod.get_session_store()
    except Exception:
        logger.debug("get_session_store dynamic resolve failed", exc_info=True)
        return None


def _mongo_uri_available() -> bool:
    return bool((os.getenv("MONGODB_URI") or "").strip())


def _get_mongo_collection():
    """Return the pymongo Collection for ``users`` or None if unavailable."""
    if not _mongo_uri_available():
        return None
    try:
        from lumen.platform.mongo_users import get_tenant_store
        store = get_tenant_store()
        col = getattr(store, "col", None)
        if col is not None:
            return col
    except Exception:
        logger.debug("mongo collection resolve failed", exc_info=True)
    return None


def write_subscription(user_id: int, record: dict[str, Any]) -> bool:
    """Persist the Pro subscription to MongoDB (permanent) + Redis (cache).

    Args:
        user_id: Telegram user id.
        record:  The pro_plan dict (plan_id, started_at, expires_at,
                 stars_paid, charge_id).

    Returns:
        True if MongoDB write succeeded (Redis is best-effort).
    """
    uid = int(user_id or 0)
    if uid <= 0 or not isinstance(record, dict):
        return False

    # ── 1. MongoDB (permanent source of truth) ──
    mongo_ok = False
    col = _get_mongo_collection()
    if col is not None:
        try:
            col.update_one(
                {"owner_telegram_id": uid},
                {
                    "$set": {
                        f"metadata.{_MONGO_META_FIELD}": dict(record),
                        f"metadata.{_MONGO_META_FIELD}_updated_at": time.time(),
                        "plan_id": "growth",  # Pro maps to growth tier
                        "updated_at": time.time(),
                    },
                },
                upsert=False,  # user must already exist (created on /start)
            )
            mongo_ok = True
            logger.info(
                "subscription persisted to MongoDB uid=%s plan=%s expires=%s",
                uid, record.get("plan_id"), record.get("expires_at"),
            )
        except Exception:
            logger.error("MongoDB subscription write FAILED uid=%s", uid, exc_info=True)
    else:
        logger.warning(
            "MongoDB unavailable — subscription written to Redis ONLY uid=%s "
            "(VULNERABLE: subscription may not survive Redis flush/TTL)", uid,
        )

    # ── 2. Redis (fast-read cache) ──
    try:
        store = _get_session_store()
        # Load existing session, merge pro_plan, save back
        existing = store.load(uid)
        existing["pro_plan"] = dict(record)
        store.save(uid, existing)
        logger.debug("subscription cached to Redis uid=%s", uid)
    except Exception:
        logger.warning("Redis subscription cache write failed uid=%s", uid, exc_info=True)

    return mongo_ok


def read_subscription(user_id: int) -> dict[str, Any] | None:
    """Read the Pro subscription — Redis first, MongoDB fallback (self-healing).

    If Redis has the record, return it immediately (fast path).
    If Redis is empty (flush / TTL expiry / drop_user_data), fall back to
    MongoDB, re-populate Redis, and return the record.

    Returns:
        The pro_plan dict, or None if no subscription exists anywhere.
    """
    uid = int(user_id or 0)
    if uid <= 0:
        return None

    # ── 1. Redis (fast path) ──
    try:
        store = _get_session_store()
        saved = store.load(uid)
        rec = saved.get("pro_plan") if isinstance(saved, dict) else None
        if isinstance(rec, dict) and rec:
            return rec
    except Exception:
        logger.debug("Redis subscription read failed uid=%s", uid, exc_info=True)

    # ── 2. MongoDB (fallback — self-healing) ──
    col = _get_mongo_collection()
    if col is None:
        return None
    try:
        doc = col.find_one({"owner_telegram_id": uid})
        if not doc:
            return None
        meta = doc.get("metadata") or {}
        rec = meta.get(_MONGO_META_FIELD)
        if not isinstance(rec, dict) or not rec:
            return None

        logger.info(
            "subscription recovered from MongoDB → Redis uid=%s expires=%s",
            uid, rec.get("expires_at"),
        )

        # Self-heal: re-populate Redis so next read is fast
        try:
            store = _get_session_store()
            existing = store.load(uid)
            existing["pro_plan"] = dict(rec)
            store.save(uid, existing)
        except Exception:
            logger.debug("Redis self-heal write failed uid=%s", uid, exc_info=True)

        return rec
    except Exception:
        logger.error("MongoDB subscription read FAILED uid=%s", uid, exc_info=True)
        return None


def delete_subscription(user_id: int) -> bool:
    """Remove the subscription from MongoDB + Redis (admin/refund only)."""
    uid = int(user_id or 0)
    if uid <= 0:
        return False

    mongo_ok = False
    col = _get_mongo_collection()
    if col is not None:
        try:
            col.update_one(
                {"owner_telegram_id": uid},
                {
                    "$unset": {f"metadata.{_MONGO_META_FIELD}": ""},
                    "$set": {
                        "plan_id": "free",
                        "updated_at": time.time(),
                    },
                },
            )
            mongo_ok = True
            logger.info("subscription deleted from MongoDB uid=%s", uid)
        except Exception:
            logger.error("MongoDB subscription delete FAILED uid=%s", uid, exc_info=True)

    # Remove pro_plan from Redis session (preserve other durable keys)
    try:
        store = _get_session_store()
        existing = store.load(uid)
        if "pro_plan" in existing:
            # save() merges, so we must clear then re-save remaining keys
            remaining = {k: v for k, v in existing.items() if k != "pro_plan"}
            store.clear(uid)
            if remaining:
                store.save(uid, remaining)
    except Exception:
        logger.warning("Redis subscription delete failed uid=%s", uid, exc_info=True)

    return mongo_ok


def has_active_subscription(user_id: int) -> bool:
    """Quick boolean check — does this user have a Pro subscription record?"""
    rec = read_subscription(user_id)
    return rec is not None and bool(rec.get("plan_id"))


__all__ = [
    "write_subscription",
    "read_subscription",
    "delete_subscription",
    "has_active_subscription",
]
