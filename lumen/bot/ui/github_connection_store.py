"""Permanent GitHub connection persistence — MongoDB source of truth + Redis cache.

Same durability model as ``subscription_store`` (Pro plan):

  write  → MongoDB users.metadata.github_connection  (permanent, no TTL)
         → Redis token_store + session github_connection  (fast cache)

  read   → Redis first
         → MongoDB fallback on miss / flush / deploy wipe
         → Self-heal: re-populate Redis from MongoDB

Without MongoDB, a Railway redeploy or Redis flush forces every user to
re-submit their PAT — unacceptable. Connection credentials are durable
account state, not ephemeral UI state.
"""
from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger("lumen_bot.github_connection_store")

_MONGO_META_FIELD = "github_connection"


def _get_mongo_collection():
    try:
        from lumen.bot.ui.subscription_store import _get_mongo_collection as _col

        return _col()
    except Exception:
        logger.debug("mongo collection resolve failed", exc_info=True)
        return None


def _encrypt_token(user_id: int, token: str) -> str:
    from lumen.engine.services.integrations.connections import token_store as ts

    aad = f"gh|{int(user_id)}".encode("utf-8")
    return ts._encrypt(token, aad=aad)


def _decrypt_token(user_id: int, ciphertext: str) -> str | None:
    from lumen.engine.services.integrations.connections import token_store as ts

    try:
        aad = f"gh|{int(user_id)}".encode("utf-8")
        return ts._decrypt(ciphertext, aad=aad)
    except Exception:
        logger.debug("decrypt github token from mongo failed uid=%s", user_id, exc_info=True)
        return None


def write_github_connection(
    user_id: int,
    token: str,
    *,
    login: str = "",
) -> bool:
    """Persist PAT + profile to MongoDB (truth) and Redis (cache)."""
    uid = int(user_id or 0)
    tok = (token or "").strip()
    if uid <= 0 or not tok:
        return False

    try:
        cipher = _encrypt_token(uid, tok)
    except Exception:
        logger.exception("encrypt github connection failed uid=%s", uid)
        return False

    record = {
        "provider": "github",
        "login": (login or "")[:80],
        "connected": True,
        "ciphertext": cipher,
        "connected_at": time.time(),
        "updated_at": time.time(),
    }

    mongo_ok = False
    col = _get_mongo_collection()
    if col is not None:
        try:
            col.update_one(
                {"owner_telegram_id": uid},
                {
                    "$set": {
                        f"metadata.{_MONGO_META_FIELD}": record,
                        "updated_at": time.time(),
                    },
                    "$setOnInsert": {
                        "owner_telegram_id": uid,
                        "created_at": time.time(),
                    },
                },
                upsert=True,
            )
            mongo_ok = True
            logger.info(
                "github_connection persisted to MongoDB uid=%s login=%s",
                uid,
                record["login"] or "—",
            )
        except Exception:
            logger.error(
                "MongoDB github_connection write FAILED uid=%s", uid, exc_info=True
            )
    else:
        logger.warning(
            "github_connection written without MongoDB uid=%s "
            "(VULNERABLE: connection may not survive Redis flush/deploy)",
            uid,
        )

    # Redis cache via token_store (encrypted key + profile)
    redis_ok = False
    try:
        from lumen.engine.services.integrations.connections import token_store as ts

        redis_ok = bool(
            ts.save_github_token(uid, tok, meta={"login": record["login"], "provider": "github"})
        )
    except Exception:
        logger.warning("Redis github token cache write failed uid=%s", uid, exc_info=True)

    # Session durable flag (no secret)
    try:
        from lumen.bot.session_store import get_session_store

        get_session_store().save(
            uid,
            {
                "github_connection": {
                    "provider": "github",
                    "login": record["login"],
                    "connected": True,
                    "connected_at": record["connected_at"],
                }
            },
        )
    except Exception:
        logger.debug("session github_connection flag save soft-fail", exc_info=True)

    return bool(mongo_ok or redis_ok)


def read_github_token(user_id: int) -> str | None:
    """Redis first, MongoDB fallback with self-heal into Redis."""
    uid = int(user_id or 0)
    if uid <= 0:
        return None

    try:
        from lumen.engine.services.integrations.connections import token_store as ts

        tok = ts.load_github_token(uid)
        if tok:
            return tok
    except Exception:
        logger.debug("Redis github token read failed uid=%s", uid, exc_info=True)

    col = _get_mongo_collection()
    if col is None:
        return None
    try:
        doc = col.find_one({"owner_telegram_id": uid})
        if not doc:
            return None
        meta = doc.get("metadata") or {}
        rec = meta.get(_MONGO_META_FIELD)
        if not isinstance(rec, dict):
            return None
        cipher = str(rec.get("ciphertext") or "")
        if not cipher:
            return None
        tok = _decrypt_token(uid, cipher)
        if not tok:
            return None
        logger.info(
            "github_connection recovered from MongoDB → Redis uid=%s login=%s",
            uid,
            rec.get("login") or "—",
        )
        try:
            from lumen.engine.services.integrations.connections import token_store as ts

            ts.save_github_token(
                uid,
                tok,
                meta={"login": str(rec.get("login") or ""), "provider": "github"},
            )
        except Exception:
            logger.debug("self-heal Redis token failed", exc_info=True)
        try:
            from lumen.bot.session_store import get_session_store

            get_session_store().save(
                uid,
                {
                    "github_connection": {
                        "provider": "github",
                        "login": str(rec.get("login") or ""),
                        "connected": True,
                        "connected_at": rec.get("connected_at") or time.time(),
                    }
                },
            )
        except Exception:
            pass
        return tok
    except Exception:
        logger.exception("MongoDB github_connection read failed uid=%s", uid)
        return None


def read_github_profile(user_id: int) -> dict[str, Any] | None:
    """Non-secret profile — Redis session → token_store profile → MongoDB."""
    uid = int(user_id or 0)
    if uid <= 0:
        return None
    try:
        from lumen.bot.session_store import get_session_store

        saved = get_session_store().load(uid)
        gc = saved.get("github_connection") if isinstance(saved, dict) else None
        if isinstance(gc, dict) and gc.get("connected"):
            return dict(gc)
    except Exception:
        pass
    try:
        from lumen.engine.services.integrations.connections import token_store as ts

        prof = ts.load_connection_profile(uid)
        if prof and prof.get("connected"):
            return dict(prof)
    except Exception:
        pass
    col = _get_mongo_collection()
    if col is None:
        return None
    try:
        doc = col.find_one({"owner_telegram_id": uid})
        if not doc:
            return None
        rec = (doc.get("metadata") or {}).get(_MONGO_META_FIELD)
        if not isinstance(rec, dict) or not rec.get("connected"):
            return None
        return {
            "provider": "github",
            "login": str(rec.get("login") or ""),
            "connected": True,
            "connected_at": rec.get("connected_at") or 0,
        }
    except Exception:
        logger.debug("mongo profile read failed", exc_info=True)
        return None


def delete_github_connection(user_id: int) -> None:
    """Explicit user disconnect — remove Mongo + Redis."""
    uid = int(user_id or 0)
    if uid <= 0:
        return
    col = _get_mongo_collection()
    if col is not None:
        try:
            col.update_one(
                {"owner_telegram_id": uid},
                {"$unset": {f"metadata.{_MONGO_META_FIELD}": ""}},
            )
        except Exception:
            logger.exception("mongo delete github_connection failed uid=%s", uid)
    try:
        from lumen.engine.services.integrations.connections import token_store as ts

        ts.clear_github_token(uid)
    except Exception:
        pass
    try:
        from lumen.bot.session_store import get_session_store

        store = get_session_store()
        existing = store.load(uid)
        if isinstance(existing, dict) and "github_connection" in existing:
            existing.pop("github_connection", None)
            # save merge won't delete keys — need explicit rewrite
            # SessionStore.save only merges; use clear+rewrite of remaining is too heavy.
            # Write connected=False flag instead.
            store.save(uid, {"github_connection": {"provider": "github", "connected": False}})
    except Exception:
        pass


def recover_after_session_drop(user_id: int) -> None:
    """Called from drop_user_data — re-hydrate connection from Mongo into Redis."""
    uid = int(user_id or 0)
    if uid <= 0:
        return
    tok = read_github_token(uid)  # self-heals Redis + session flag
    if tok:
        logger.info("drop_user_data: restored github_connection uid=%s from MongoDB", uid)
