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


def _persist_connection_record(user_id: int, record: dict[str, Any]) -> bool:
    """Write non-secret+encrypted connection record to Mongo, Redis profile, session."""
    uid = int(user_id or 0)
    if uid <= 0 or not record:
        return False

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
                "github_connection persisted to MongoDB uid=%s auth_kind=%s login=%s",
                uid,
                record.get("auth_kind") or "pat",
                record.get("login") or "—",
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

    try:
        from lumen.engine.services.integrations.connections import token_store as ts

        ts.save_connection_profile(
            uid,
            {
                "login": str(record.get("login") or "")[:80],
                "provider": "github",
                "connected": True,
                "connected_at": float(record.get("connected_at") or time.time()),
                "auth_kind": str(record.get("auth_kind") or "pat"),
                "installation_id": str(record.get("installation_id") or ""),
                "account_login": str(record.get("account_login") or record.get("login") or "")[:80],
                "account_type": str(record.get("account_type") or "")[:40],
                "repo_selection": str(record.get("repo_selection") or "")[:20],
            },
        )
    except Exception:
        logger.debug("token_store profile write soft-fail uid=%s", uid, exc_info=True)

    try:
        from lumen.bot.session_store import get_session_store

        get_session_store().save(
            uid,
            {
                "github_connection": {
                    "provider": "github",
                    "login": str(record.get("login") or ""),
                    "connected": True,
                    "connected_at": float(record.get("connected_at") or time.time()),
                    "auth_kind": str(record.get("auth_kind") or "pat"),
                    "installation_id": str(record.get("installation_id") or ""),
                    "account_login": str(record.get("account_login") or "")[:80],
                    "repo_selection": str(record.get("repo_selection") or ""),
                }
            },
        )
    except Exception:
        logger.debug("session github_connection flag save soft-fail", exc_info=True)

    return mongo_ok


def write_github_connection(
    user_id: int,
    token: str,
    *,
    login: str = "",
) -> bool:
    """Persist PAT + profile to MongoDB (truth) and Redis (cache). Legacy path."""
    uid = int(user_id or 0)
    tok = (token or "").strip()
    if uid <= 0 or not tok:
        return False

    try:
        cipher = _encrypt_token(uid, tok)
    except Exception:
        logger.exception("encrypt github connection failed uid=%s", uid)
        return False

    now = time.time()
    record = {
        "provider": "github",
        "auth_kind": "pat",
        "login": (login or "")[:80],
        "connected": True,
        "ciphertext": cipher,
        "installation_id": "",
        "account_login": (login or "")[:80],
        "account_type": "user",
        "repo_selection": "",
        "connected_at": now,
        "updated_at": now,
    }

    mongo_ok = _persist_connection_record(uid, record)

    redis_ok = False
    try:
        from lumen.engine.services.integrations.connections import token_store as ts

        redis_ok = bool(
            ts.save_github_token(
                uid,
                tok,
                meta={
                    "login": record["login"],
                    "provider": "github",
                    "auth_kind": "pat",
                },
            )
        )
    except Exception:
        logger.warning("Redis github token cache write failed uid=%s", uid, exc_info=True)

    return bool(mongo_ok or redis_ok)


def write_github_app_connection(
    user_id: int,
    installation_id: int | str,
    *,
    login: str = "",
    account_login: str = "",
    account_type: str = "",
    repo_selection: str = "",
) -> bool:
    """Persist GitHub App installation binding (no long-lived user PAT).

    Access tokens are minted on demand via app_auth.get_installation_token.
    """
    uid = int(user_id or 0)
    try:
        iid = str(int(installation_id))
    except (TypeError, ValueError):
        return False
    if uid <= 0 or not iid:
        return False

    now = time.time()
    account = (account_login or login or "")[:80]
    record = {
        "provider": "github",
        "auth_kind": "github_app",
        "login": account,
        "connected": True,
        "ciphertext": "",  # no PAT stored
        "installation_id": iid,
        "account_login": account,
        "account_type": (account_type or "")[:40],
        "repo_selection": (repo_selection or "")[:20],
        "connected_at": now,
        "updated_at": now,
    }
    return _persist_connection_record(uid, record)


def _load_raw_connection_record(user_id: int) -> dict[str, Any] | None:
    """Mongo → Redis profile; may include ciphertext / installation_id."""
    uid = int(user_id or 0)
    if uid <= 0:
        return None
    col = _get_mongo_collection()
    if col is not None:
        try:
            doc = col.find_one({"owner_telegram_id": uid})
            if doc:
                rec = (doc.get("metadata") or {}).get(_MONGO_META_FIELD)
                if isinstance(rec, dict) and rec.get("connected"):
                    return dict(rec)
        except Exception:
            logger.debug("mongo raw connection read failed uid=%s", uid, exc_info=True)
    try:
        from lumen.engine.services.integrations.connections import token_store as ts

        prof = ts.load_connection_profile(uid)
        if prof and prof.get("connected"):
            return dict(prof)
    except Exception:
        pass
    return None


def read_github_token(user_id: int) -> str | None:
    """Return a usable GitHub token for API/clone.

    - auth_kind=github_app → short-lived installation access token (minted)
    - auth_kind=pat / legacy → decrypted PAT from Redis/Mongo
    """
    uid = int(user_id or 0)
    if uid <= 0:
        return None

    rec = _load_raw_connection_record(uid)
    auth_kind = str((rec or {}).get("auth_kind") or "").strip().lower()
    installation_id = str((rec or {}).get("installation_id") or "").strip()

    if auth_kind == "github_app" or (not auth_kind and installation_id and not (rec or {}).get("ciphertext")):
        if not installation_id:
            return None
        try:
            from lumen.engine.services.integrations.github.app_auth import (
                get_installation_token,
            )

            return get_installation_token(installation_id)
        except Exception:
            logger.exception(
                "github_app installation token mint failed uid=%s install=%s",
                uid,
                installation_id,
            )
            return None

    # PAT path (legacy + explicit auth_kind=pat)
    try:
        from lumen.engine.services.integrations.connections import token_store as ts

        tok = ts.load_github_token(uid)
        if tok:
            return tok
    except Exception:
        logger.debug("Redis github token read failed uid=%s", uid, exc_info=True)

    if not rec:
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
            meta={
                "login": str(rec.get("login") or ""),
                "provider": "github",
                "auth_kind": "pat",
            },
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
                    "auth_kind": "pat",
                    "login": str(rec.get("login") or ""),
                    "connected": True,
                    "connected_at": rec.get("connected_at") or time.time(),
                }
            },
        )
    except Exception:
        pass
    return tok


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
            "auth_kind": str(rec.get("auth_kind") or ("github_app" if rec.get("installation_id") else "pat")),
            "login": str(rec.get("login") or ""),
            "connected": True,
            "connected_at": rec.get("connected_at") or 0,
            "installation_id": str(rec.get("installation_id") or ""),
            "account_login": str(rec.get("account_login") or rec.get("login") or ""),
            "account_type": str(rec.get("account_type") or ""),
            "repo_selection": str(rec.get("repo_selection") or ""),
        }
    except Exception:
        logger.debug("mongo profile read failed", exc_info=True)
        return None


def delete_github_connection(user_id: int) -> None:
    """Explicit user disconnect — remove Mongo + Redis + App token cache."""
    uid = int(user_id or 0)
    if uid <= 0:
        return
    iid = ""
    try:
        rec = _load_raw_connection_record(uid) or {}
        iid = str(rec.get("installation_id") or "")
    except Exception:
        pass
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
    if iid:
        try:
            from lumen.engine.services.integrations.github.app_auth import (
                clear_installation_token_cache,
            )

            clear_installation_token_cache(iid)
        except Exception:
            pass
    try:
        from lumen.bot.session_store import get_session_store

        store = get_session_store()
        existing = store.load(uid)
        if isinstance(existing, dict) and "github_connection" in existing:
            existing.pop("github_connection", None)
            store.save(
                uid,
                {
                    "github_connection": {
                        "provider": "github",
                        "connected": False,
                        "auth_kind": "",
                        "installation_id": "",
                    }
                },
            )
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
