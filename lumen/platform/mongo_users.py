"""MongoDB-backed user/tenant identity — users + plan only.

Connection via MONGODB_URI env (never hardcode credentials).
Collection: users
Plans: free | pro | unlimited
"""
from __future__ import annotations

import logging
import os
import secrets
import time
from typing import Any

logger = logging.getLogger(__name__)


_mongo_client = None
_mongo_db = None



def resolve_mongodb_uri() -> str:
    """Accept common env names; strip quotes/whitespace.

    Deploy panels often use MONGO_URL / MONGODB_URL instead of MONGODB_URI.
    """
    keys = (
        "MONGODB_URI",
        "MONGO_URI",
        "MONGODB_URL",
        "MONGO_URL",
        "MONGODB_CONNECTION_STRING",
    )
    for key in keys:
        raw = os.getenv(key)
        if raw is None:
            continue
        v = str(raw).strip().strip('"').strip("'")
        if v:
            return v
    # Some hosts put mongodb:// in DATABASE_URL
    for key in ("DATABASE_URL", "DB_URL"):
        raw = os.getenv(key)
        if raw is None:
            continue
        v = str(raw).strip().strip('"').strip("'")
        if v.startswith("mongodb"):
            return v
    return ""


def get_mongo_db():
    """Shared Mongo database handle (same MONGODB_URI / MONGODB_DB as users).

    Used by referrals and any feature that must hit the same cluster/db.
    """
    global _mongo_client, _mongo_db
    if _mongo_db is not None:
        return _mongo_db
    try:
        from pymongo import MongoClient
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("pymongo is required for MONGODB_URI") from exc
    uri = resolve_mongodb_uri()
    if not uri:
        raise ValueError("MONGODB_URI (or MONGO_URL / MONGODB_URL) is required")
    db_name = (os.getenv("MONGODB_DB") or "lumen").strip()
    timeout = int(os.getenv("MONGODB_TIMEOUT_MS") or "3000")
    _mongo_client = MongoClient(
        uri,
        serverSelectionTimeoutMS=timeout,
        connectTimeoutMS=timeout,
        retryWrites=True,
    )
    _mongo_db = _mongo_client[db_name]
    logger.info("shared MongoDB ready db=%s", db_name)
    return _mongo_db


# Canonical plan ids — explorer | starter | growth
CANONICAL_PLANS = frozenset({"free", "starter", "growth"})


def normalize_plan_id(plan_id: str | None) -> str:
    try:
        from .plans import normalize_plan_id as _np
        return _np(plan_id)
    except Exception:
        key = (plan_id or "free").strip().lower()
        aliases = {
            "free": "free", "hobby": "free", "explorer": "free",
            "indie": "starter", "starter": "starter",
            "pro": "growth", "growth": "growth", "business": "growth",
            "unlimited": "growth", "enterprise": "growth",
        }
        return aliases.get(key, "free")


def _new_api_key(prefix: str = "sk_live") -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def _hash_key(raw: str) -> str:
    import hashlib
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class MongoUserStore:
    """Same behavioural surface as TenantStore, persisted in MongoDB `users`."""

    def __init__(self, uri: str | None = None, *, db_name: str | None = None) -> None:
        try:
            from pymongo import MongoClient, ASCENDING
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "pymongo is required for MONGODB_URI. pip install pymongo"
            ) from exc

        self.uri = (uri or resolve_mongodb_uri() or "").strip()
        if not self.uri:
            raise ValueError("MONGODB_URI is required for MongoUserStore")
        self.db_name = (db_name or os.getenv("MONGODB_DB") or "lumen").strip()
        timeout = int(os.getenv("MONGODB_TIMEOUT_MS") or "3000")
        self._client = MongoClient(
            self.uri,
            serverSelectionTimeoutMS=timeout,
            connectTimeoutMS=timeout,
            retryWrites=True,
        )
        self._db = self._client[self.db_name]
        self.col = self._db["users"]
        # Indexes (best-effort — do not crash if network/IP allowlist blocks us at boot)
        try:
            self.col.create_index([("tenant_id", ASCENDING)], unique=True)
            self.col.create_index([("api_key_hash", ASCENDING)], unique=True, sparse=True)
            self.col.create_index([("owner_telegram_id", ASCENDING)])
            self.col.create_index([("plan_id", ASCENDING)])
        except Exception as exc:
            logger.warning("MongoUserStore index setup deferred: %s", type(exc).__name__)
        # Compatibility shims used by billing.apply_plan legacy path
        self._by_id: dict[str, Any] = {}
        self.index_path = None  # type: ignore
        logger.info("MongoUserStore ready db=%s collection=users", self.db_name)

    def _doc_to_tenant(self, doc: dict[str, Any]):
        from .tenants import Tenant

        if not doc:
            return None
        fields = {k: doc.get(k) for k in Tenant.__dataclass_fields__ if k in doc or k == "tenant_id"}
        # ensure required
        fields["tenant_id"] = doc.get("tenant_id") or ""
        fields["name"] = doc.get("name") or "User"
        fields["plan_id"] = normalize_plan_id(doc.get("plan_id"))
        fields.setdefault("brand_name", doc.get("brand_name") or "")
        fields.setdefault("brand_logo_url", doc.get("brand_logo_url") or "")
        fields.setdefault("primary_color", doc.get("primary_color") or "#2563eb")
        fields.setdefault("support_email", doc.get("support_email") or "")
        fields.setdefault("custom_domain", doc.get("custom_domain") or "")
        fields.setdefault("api_key_hash", doc.get("api_key_hash") or "")
        fields.setdefault("api_key_prefix", doc.get("api_key_prefix") or "")
        fields.setdefault("owner_telegram_id", int(doc.get("owner_telegram_id") or 0))
        fields.setdefault("active", bool(doc.get("active", True)))
        fields.setdefault("created_at", float(doc.get("created_at") or time.time()))
        fields.setdefault("metadata", dict(doc.get("metadata") or {}))
        return Tenant(**{k: v for k, v in fields.items() if k in Tenant.__dataclass_fields__})

    def _tenant_to_doc(self, t) -> dict[str, Any]:
        from dataclasses import asdict
        doc = asdict(t)
        doc["plan_id"] = normalize_plan_id(doc.get("plan_id"))
        doc["updated_at"] = time.time()
        return doc

    def create(
        self,
        name: str,
        *,
        plan_id: str = "free",
        brand_name: str = "",
        owner_telegram_id: int = 0,
        **wl: Any,
    ):
        from .tenants import Tenant

        tid = f"ten_{secrets.token_hex(8)}"
        raw = _new_api_key()
        plan = normalize_plan_id(plan_id)
        t = Tenant(
            tenant_id=tid,
            name=(name or "User").strip()[:120],
            plan_id=plan,
            brand_name=(brand_name or name or "").strip()[:120],
            brand_logo_url=str(wl.get("brand_logo_url") or "")[:300],
            primary_color=str(wl.get("primary_color") or "#2563eb")[:20],
            support_email=str(wl.get("support_email") or "")[:120],
            custom_domain=str(wl.get("custom_domain") or "")[:200],
            api_key_hash=_hash_key(raw),
            api_key_prefix=raw[:12],
            owner_telegram_id=int(owner_telegram_id or 0),
        )
        doc = self._tenant_to_doc(t)
        self.col.insert_one(doc)
        return t, raw

    def rotate_key(self, tenant_id: str) -> str | None:
        cur = self.col.find_one({"tenant_id": tenant_id})
        if not cur:
            return None
        raw = _new_api_key()
        self.col.update_one(
            {"tenant_id": tenant_id},
            {
                "$set": {
                    "api_key_hash": _hash_key(raw),
                    "api_key_prefix": raw[:12],
                    "updated_at": time.time(),
                }
            },
        )
        return raw

    def authenticate(self, api_key: str):
        if not api_key:
            return None
        h = _hash_key(api_key.strip())
        doc = self.col.find_one({"api_key_hash": h, "active": True})
        return self._doc_to_tenant(doc) if doc else None

    def get(self, tenant_id: str):
        doc = self.col.find_one({"tenant_id": tenant_id})
        return self._doc_to_tenant(doc) if doc else None

    def get_by_telegram(self, owner_telegram_id: int):
        doc = self.col.find_one({"owner_telegram_id": int(owner_telegram_id or 0)})
        return self._doc_to_tenant(doc) if doc else None

    def update_white_label(self, tenant_id: str, **fields: Any):
        allowed = {
            "brand_name",
            "brand_logo_url",
            "primary_color",
            "support_email",
            "custom_domain",
            "name",
        }
        patch = {k: str(fields[k])[:300] for k in allowed if k in fields and fields[k] is not None}
        if not patch:
            return self.get(tenant_id)
        patch["updated_at"] = time.time()
        self.col.update_one({"tenant_id": tenant_id}, {"$set": patch})
        return self.get(tenant_id)

    def set_plan(
        self,
        tenant_id: str,
        plan_id: str,
        *,
        metadata_updates: dict[str, Any] | None = None,
        active: bool = True,
    ) -> bool:
        doc = self.col.find_one({"tenant_id": tenant_id})
        if not doc:
            return False
        meta = dict(doc.get("metadata") or {})
        if metadata_updates:
            meta.update(metadata_updates)
        meta["last_plan_change"] = time.time()
        self.col.update_one(
            {"tenant_id": tenant_id},
            {
                "$set": {
                    "plan_id": normalize_plan_id(plan_id),
                    "active": bool(active),
                    "metadata": meta,
                    "updated_at": time.time(),
                }
            },
        )
        return True

    def list_all(self):
        return [self._doc_to_tenant(d) for d in self.col.find({}) if d]

    def _mutate(self, fn):
        """Compatibility for billing.apply_plan that touches _by_id.

        Loads the target tenant into _by_id, runs fn, then persists plan/metadata.
        """
        # Refresh cache snapshot for ids referenced during fn
        self._by_id = {}
        for d in self.col.find({}):
            t = self._doc_to_tenant(d)
            if t:
                self._by_id[t.tenant_id] = t
        result = fn()
        # Persist any mutations done on Tenant objects in _by_id
        for tid, t in list(self._by_id.items()):
            self.col.update_one(
                {"tenant_id": tid},
                {"$set": self._tenant_to_doc(t)},
                upsert=True,
            )
        return result


def get_or_create_by_telegram(
    owner_telegram_id: int,
    *,
    name: str = "",
    plan_id: str = "free",
    username: str = "",
) -> tuple:
    """Ensure a Mongo user exists for a Telegram user_id; return (tenant, created: bool).

    Returning users (even after blocking/deleting the bot) are touched: last_seen + profile.
    """
    import time as _time
    from .tenants import get_tenant_store
    store = get_tenant_store()
    uid = int(owner_telegram_id or 0)
    if uid <= 0:
        raise ValueError("owner_telegram_id required")
    display = (name or f"tg_{uid}")[:120]
    existing = None
    if hasattr(store, "get_by_telegram"):
        existing = store.get_by_telegram(uid)
    if existing is None and hasattr(store, "list_all"):
        for t in store.list_all():
            if int(getattr(t, "owner_telegram_id", 0) or 0) == uid:
                existing = t
                break
    if existing is not None:
        # Re-entry: always refresh last_seen so reinstall / unblock is recorded
        try:
            if hasattr(store, "col"):
                store.col.update_one(
                    {"owner_telegram_id": uid},
                    {
                        "$set": {
                            "last_seen_at": _time.time(),
                            "name": display or getattr(existing, "name", "") or f"tg_{uid}",
                            "username": (username or "")[:64],
                            "active": True,
                            "updated_at": _time.time(),
                        },
                        "$inc": {"visit_count": 1},
                    },
                    upsert=False,
                )
            elif hasattr(store, "update_white_label"):
                meta = dict(getattr(existing, "metadata", None) or {})
                meta["last_seen_at"] = _time.time()
                meta["visit_count"] = int(meta.get("visit_count") or 0) + 1
                if username:
                    meta["username"] = username[:64]
                store.update_white_label(existing.tenant_id, metadata=meta, name=display)
        except Exception:
            pass
        return existing, False
    tenant, _raw = store.create(
        display,
        plan_id=plan_id,
        owner_telegram_id=uid,
    )
    try:
        if hasattr(store, "col"):
            store.col.update_one(
                {"tenant_id": tenant.tenant_id},
                {
                    "$set": {
                        "last_seen_at": _time.time(),
                        "username": (username or "")[:64],
                        "visit_count": 1,
                        "active": True,
                    }
                },
            )
    except Exception:
        pass
    return tenant, True
