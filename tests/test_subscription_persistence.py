"""Database persistence audit — subscription survives Redis flush, TTL, bot deletion.

Tests that the Pro subscription is persisted to MongoDB (permanent source of
truth) and that the entitlement resolver falls back to MongoDB when Redis is
empty (flush / TTL expiry / drop_user_data).  Also tests that re-entry (user
deletes bot and comes back) preserves the subscription.
"""
from __future__ import annotations

import os

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test:t123")
os.environ.setdefault("TBE_TOKEN_SECRET", "test_secret_1234567890")
os.environ.setdefault("API_KEY_PEPPER", "test_pepper_1234567890")
os.environ.setdefault("TBE_ENV", "test")
os.environ.setdefault("ALLOW_ALL_USERS", "1")
os.environ.setdefault("GEMINI_API_KEY", "test_key")
os.environ.setdefault("SESSION_ALLOW_MEMORY", "1")

import time
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from lumen.bot.session_store import (
    SessionStore,
    _DURABLE_KEYS,
    _MemoryBackend,
    _ttl_sec_for_data,
    _PRO_SUBSCRIPTION_TTL_SEC,
    _DEFAULT_TTL_SEC,
    reset_session_store_for_tests,
)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_singletons():
    reset_session_store_for_tests()
    yield
    reset_session_store_for_tests()


def _make_pro_record(days_remaining: int = 30) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "plan_id": "lumen_pro",
        "started_at": now.isoformat(),
        "expires_at": (now + timedelta(days=days_remaining)).isoformat(),
        "stars_paid": 2000,
        "charge_id": "tg_charge_test_123",
    }


class _FakeMongoCollection:
    """In-memory fake of a pymongo Collection for testing."""

    def __init__(self):
        self._docs: dict[int, dict[str, Any]] = {}

    def find_one(self, query: dict) -> dict[str, Any] | None:
        if "owner_telegram_id" in query:
            return self._docs.get(int(query["owner_telegram_id"]))
        return None

    def update_one(self, query: dict, update: dict, upsert: bool = False) -> MagicMock:
        uid = int(query.get("owner_telegram_id", 0))
        doc = self._docs.get(uid, {})
        if "$set" in update:
            for k, v in update["$set"].items():
                # Support dot notation: metadata.pro_subscription
                parts = k.split(".")
                d = doc
                for p in parts[:-1]:
                    if p not in d or not isinstance(d[p], dict):
                        d[p] = {}
                    d = d[p]
                d[parts[-1]] = v
        if "$unset" in update:
            for k in update["$unset"]:
                parts = k.split(".")
                d = doc
                for p in parts[:-1]:
                    if p not in d or not isinstance(d[p], dict):
                        break
                    d = d[p]
                else:
                    d.pop(parts[-1], None)
        if "$inc" in update:
            for k, v in update["$inc"].items():
                doc[k] = doc.get(k, 0) + v
        self._docs[uid] = doc
        result = MagicMock()
        result.modified_count = 1
        return result


class _FakeMongoStore:
    """Fake store with a .col attribute like MongoUserStore."""

    def __init__(self):
        self.col = _FakeMongoCollection()


# ──────────────────────────────────────────────────────────────────────────────
# 1. pro_plan IS a durable key
# ──────────────────────────────────────────────────────────────────────────────

def test_pro_plan_is_durable_key():
    """pro_plan must be in _DURABLE_KEYS so it persists to Redis."""
    assert "pro_plan" in _DURABLE_KEYS


# ──────────────────────────────────────────────────────────────────────────────
# 2. Redis TTL extended when pro_plan is present
# ──────────────────────────────────────────────────────────────────────────────

def test_ttl_extended_when_pro_plan_present():
    """When pro_plan is in the data, TTL must be > 30 days (45 days)."""
    data_with_pro = {"pro_plan": _make_pro_record()}
    ttl = _ttl_sec_for_data(data_with_pro)
    assert ttl == _PRO_SUBSCRIPTION_TTL_SEC
    assert ttl > _DEFAULT_TTL_SEC
    assert ttl >= 45 * 24 * 3600  # at least 45 days


def test_ttl_default_without_pro_plan():
    """Without pro_plan, TTL is the default 30 days."""
    ttl = _ttl_sec_for_data({"lang": "ar"})
    assert ttl == _DEFAULT_TTL_SEC


def test_ttl_default_with_empty_data():
    ttl = _ttl_sec_for_data({})
    assert ttl == _DEFAULT_TTL_SEC


def test_ttl_default_with_none():
    ttl = _ttl_sec_for_data(None)
    assert ttl == _DEFAULT_TTL_SEC


# ──────────────────────────────────────────────────────────────────────────────
# 3. subscription_store.write_subscription writes to MongoDB + Redis
# ──────────────────────────────────────────────────────────────────────────────

def test_write_subscription_persists_to_mongodb():
    """write_subscription must write to MongoDB (permanent source of truth)."""
    from lumen.bot.ui import subscription_store

    fake_store = _FakeMongoStore()
    backend = _MemoryBackend()
    session_store = SessionStore(client=backend)

    with patch.object(subscription_store, "_get_mongo_collection", return_value=fake_store.col), \
         patch.object(subscription_store, "get_session_store", return_value=session_store, create=True), \
         patch.object(subscription_store, "_get_session_store", return_value=session_store):
        record = _make_pro_record()
        result = subscription_store.write_subscription(42, record)

    assert result is True  # MongoDB write succeeded
    doc = fake_store.col.find_one({"owner_telegram_id": 42})
    assert doc is not None
    assert doc["metadata"]["pro_subscription"]["plan_id"] == "lumen_pro"
    assert doc["metadata"]["pro_subscription"]["stars_paid"] == 2000
    assert doc["plan_id"] == "growth"  # Pro maps to growth tier


def test_write_subscription_also_caches_to_redis():
    """write_subscription must also write to Redis (fast-read cache)."""
    from lumen.bot.ui import subscription_store

    fake_store = _FakeMongoStore()
    backend = _MemoryBackend()
    session_store = SessionStore(client=backend)

    with patch.object(subscription_store, "_get_mongo_collection", return_value=fake_store.col), \
         patch.object(subscription_store, "_get_session_store", return_value=session_store):
        record = _make_pro_record()
        subscription_store.write_subscription(42, record)

    # Redis should also have the pro_plan
    redis_data = session_store.load(42)
    assert "pro_plan" in redis_data
    assert redis_data["pro_plan"]["plan_id"] == "lumen_pro"


# ──────────────────────────────────────────────────────────────────────────────
# 4. read_subscription: Redis first, MongoDB fallback
# ──────────────────────────────────────────────────────────────────────────────

def test_read_subscription_from_redis_fast_path():
    """read_subscription returns from Redis when available (fast path)."""
    from lumen.bot.ui import subscription_store

    fake_store = _FakeMongoStore()
    backend = _MemoryBackend()
    session_store = SessionStore(client=backend)

    # Write pro_plan to Redis only (not MongoDB)
    session_store.save(99, {"pro_plan": _make_pro_record()})

    with patch.object(subscription_store, "_get_mongo_collection", return_value=fake_store.col), \
         patch.object(subscription_store, "_get_session_store", return_value=session_store):
        rec = subscription_store.read_subscription(99)

    assert rec is not None
    assert rec["plan_id"] == "lumen_pro"
    # MongoDB should NOT have been queried (fast path)
    assert fake_store.col.find_one({"owner_telegram_id": 99}) is None


def test_read_subscription_falls_back_to_mongodb_when_redis_empty():
    """CRITICAL: when Redis is empty, read_subscription falls back to MongoDB."""
    from lumen.bot.ui import subscription_store

    fake_store = _FakeMongoStore()
    backend = _MemoryBackend()
    session_store = SessionStore(client=backend)

    # Write to MongoDB only (simulating Redis flush / TTL expiry)
    record = _make_pro_record()
    fake_store.col._docs[77] = {
        "owner_telegram_id": 77,
        "plan_id": "growth",
        "metadata": {"pro_subscription": record},
    }

    # Redis should be empty
    assert session_store.load(77) == {}

    with patch.object(subscription_store, "_get_mongo_collection", return_value=fake_store.col), \
         patch.object(subscription_store, "_get_session_store", return_value=session_store):
        rec = subscription_store.read_subscription(77)

    assert rec is not None
    assert rec["plan_id"] == "lumen_pro"
    assert rec["stars_paid"] == 2000


def test_read_subscription_self_heals_redis_from_mongodb():
    """When falling back to MongoDB, Redis should be re-populated (self-healing)."""
    from lumen.bot.ui import subscription_store

    fake_store = _FakeMongoStore()
    backend = _MemoryBackend()
    session_store = SessionStore(client=backend)

    record = _make_pro_record()
    fake_store.col._docs[88] = {
        "owner_telegram_id": 88,
        "plan_id": "growth",
        "metadata": {"pro_subscription": record},
    }

    # Redis empty
    assert session_store.load(88) == {}

    with patch.object(subscription_store, "_get_mongo_collection", return_value=fake_store.col), \
         patch.object(subscription_store, "_get_session_store", return_value=session_store):
        rec = subscription_store.read_subscription(88)

    # After read, Redis should be self-healed
    redis_data = session_store.load(88)
    assert "pro_plan" in redis_data
    assert redis_data["pro_plan"]["plan_id"] == "lumen_pro"


def test_read_subscription_returns_none_when_neither_has_record():
    """When neither Redis nor MongoDB has a record, return None."""
    from lumen.bot.ui import subscription_store

    fake_store = _FakeMongoStore()
    backend = _MemoryBackend()
    session_store = SessionStore(client=backend)

    with patch.object(subscription_store, "_get_mongo_collection", return_value=fake_store.col), \
         patch.object(subscription_store, "_get_session_store", return_value=session_store):
        rec = subscription_store.read_subscription(123)

    assert rec is None


# ──────────────────────────────────────────────────────────────────────────────
# 5. End-to-end: entitlement resolver uses MongoDB fallback
# ──────────────────────────────────────────────────────────────────────────────

def test_entitlement_resolves_from_mongodb_when_redis_flushed():
    """CRITICAL: resolve_pro_entitlement must work even after Redis is flushed.

    This is the bot-deletion-and-re-entry scenario:
      1. User pays → subscription written to MongoDB + Redis
      2. Redis is flushed / key expires / drop_user_data called
      3. User comes back → entitlement must still resolve from MongoDB
    """
    from lumen.bot.ui import subscription_store, pro_plan_entitlement

    fake_store = _FakeMongoStore()
    backend = _MemoryBackend()
    session_store = SessionStore(client=backend)

    record = _make_pro_record(days_remaining=25)
    fake_store.col._docs[555] = {
        "owner_telegram_id": 555,
        "plan_id": "growth",
        "metadata": {"pro_subscription": record},
    }

    # Redis is EMPTY (simulating flush / TTL / drop)
    assert session_store.load(555) == {}

    with patch.object(subscription_store, "_get_mongo_collection", return_value=fake_store.col), \
         patch.object(subscription_store, "_get_session_store", return_value=session_store):
        ent = pro_plan_entitlement.resolve_pro_entitlement(555)

    assert ent is not None
    assert ent.plan_id == "lumen_pro"
    assert ent.is_expired is False
    assert ent.stars_paid == 2000


def test_entitlement_returns_none_for_nonexistent_user():
    """Nonexistent user gets no entitlement (fail-closed)."""
    from lumen.bot.ui import subscription_store, pro_plan_entitlement

    fake_store = _FakeMongoStore()
    backend = _MemoryBackend()
    session_store = SessionStore(client=backend)

    with patch.object(subscription_store, "_get_mongo_collection", return_value=fake_store.col), \
         patch.object(subscription_store, "_get_session_store", return_value=session_store):
        ent = pro_plan_entitlement.resolve_pro_entitlement(99999)

    assert ent is None


def test_plan_limits_resolve_from_mongodb_when_redis_flushed():
    """resolve_plan_limits must return Pro values even when Redis is empty."""
    from lumen.bot.ui import subscription_store, pro_plan_entitlement

    fake_store = _FakeMongoStore()
    backend = _MemoryBackend()
    session_store = SessionStore(client=backend)

    record = _make_pro_record(days_remaining=20)
    fake_store.col._docs[777] = {
        "owner_telegram_id": 777,
        "plan_id": "growth",
        "metadata": {"pro_subscription": record},
    }

    with patch.object(subscription_store, "_get_mongo_collection", return_value=fake_store.col), \
         patch.object(subscription_store, "_get_session_store", return_value=session_store):
        limits = pro_plan_entitlement.resolve_plan_limits(777)

    assert limits.is_pro is True
    assert limits.max_bots == 3
    assert limits.disk_mb == 2048
    assert limits.memory_mb == 512
    assert limits.cpu == 0.5


# ──────────────────────────────────────────────────────────────────────────────
# 6. drop_user_data preserves subscription via MongoDB re-hydration
# ──────────────────────────────────────────────────────────────────────────────

def test_drop_user_data_preserves_subscription():
    """drop_user_data clears Redis but re-hydrates pro_plan from MongoDB."""
    import asyncio
    from lumen.bot.ui import subscription_store
    from lumen.bot.ptb_redis_persistence import RedisPersistence

    fake_store = _FakeMongoStore()
    backend = _MemoryBackend()
    session_store = SessionStore(client=backend)

    # Write subscription to both MongoDB and Redis
    record = _make_pro_record()
    fake_store.col._docs[333] = {
        "owner_telegram_id": 333,
        "plan_id": "growth",
        "metadata": {"pro_subscription": record},
    }
    session_store.save(333, {"pro_plan": record, "lang": "ar"})

    # Verify Redis has it
    assert "pro_plan" in session_store.load(333)

    persistence = RedisPersistence(store=session_store)

    with patch.object(subscription_store, "_get_mongo_collection", return_value=fake_store.col), \
         patch.object(subscription_store, "_get_session_store", return_value=session_store):
        asyncio.run(persistence.drop_user_data(333))

    # Redis was cleared, but pro_plan should be re-hydrated from MongoDB
    redis_data = session_store.load(333)
    assert "pro_plan" in redis_data
    assert redis_data["pro_plan"]["plan_id"] == "lumen_pro"


# ──────────────────────────────────────────────────────────────────────────────
# 7. Subscription survives simulated bot deletion + re-entry
# ──────────────────────────────────────────────────────────────────────────────

def test_subscription_survives_bot_deletion_and_reentry():
    """FULL SCENARIO: user pays, deletes bot, comes back — subscription intact.

    Steps:
      1. User pays → write_subscription (MongoDB + Redis)
      2. User deletes bot → simulate by clearing Redis (drop_user_data or TTL)
      3. User re-enters with /start → hydrate from Redis (empty) → entitlement
         check falls back to MongoDB → subscription still active
    """
    from lumen.bot.ui import subscription_store, pro_plan_entitlement

    fake_store = _FakeMongoStore()
    backend = _MemoryBackend()
    session_store = SessionStore(client=backend)

    # Step 1: User pays
    record = _make_pro_record(days_remaining=30)
    with patch.object(subscription_store, "_get_mongo_collection", return_value=fake_store.col), \
         patch.object(subscription_store, "_get_session_store", return_value=session_store):
        subscription_store.write_subscription(111, record)

    # Verify both stores have it
    assert "pro_plan" in session_store.load(111)
    assert fake_store.col.find_one({"owner_telegram_id": 111}) is not None

    # Step 2: User deletes bot — Redis is cleared (simulating deletion/TTL/flush)
    session_store.clear(111)
    assert session_store.load(111) == {}  # Redis is empty

    # Step 3: User re-enters — /start calls hydrate (Redis empty → nothing loaded)
    user_data: dict[str, Any] = {}
    session_store.hydrate(111, user_data)
    assert "pro_plan" not in user_data  # Redis had nothing

    # But entitlement check falls back to MongoDB!
    with patch.object(subscription_store, "_get_mongo_collection", return_value=fake_store.col), \
         patch.object(subscription_store, "_get_session_store", return_value=session_store):
        ent = pro_plan_entitlement.resolve_pro_entitlement(111)
        limits = pro_plan_entitlement.resolve_plan_limits(111)

    assert ent is not None, "Subscription must survive bot deletion via MongoDB!"
    assert ent.plan_id == "lumen_pro"
    assert limits.is_pro is True
    assert limits.max_bots == 3
    assert limits.disk_mb == 2048

    # And Redis should now be self-healed
    redis_data = session_store.load(111)
    assert "pro_plan" in redis_data


# ──────────────────────────────────────────────────────────────────────────────
# 8. delete_subscription removes from both stores
# ──────────────────────────────────────────────────────────────────────────────

def test_delete_subscription_removes_from_both_stores():
    """delete_subscription must remove from MongoDB AND Redis."""
    from lumen.bot.ui import subscription_store

    fake_store = _FakeMongoStore()
    backend = _MemoryBackend()
    session_store = SessionStore(client=backend)

    # Write to both
    record = _make_pro_record()
    with patch.object(subscription_store, "_get_mongo_collection", return_value=fake_store.col), \
         patch.object(subscription_store, "_get_session_store", return_value=session_store):
        subscription_store.write_subscription(222, record)

    assert "pro_plan" in session_store.load(222)
    assert fake_store.col.find_one({"owner_telegram_id": 222}) is not None

    # Delete
    with patch.object(subscription_store, "_get_mongo_collection", return_value=fake_store.col), \
         patch.object(subscription_store, "_get_session_store", return_value=session_store):
        result = subscription_store.delete_subscription(222)

    assert result is True

    # Redis should not have pro_plan (but other keys preserved)
    redis_data = session_store.load(222)
    assert "pro_plan" not in redis_data

    # MongoDB should not have pro_subscription
    doc = fake_store.col.find_one({"owner_telegram_id": 222})
    assert doc is not None  # user still exists
    assert "pro_subscription" not in (doc.get("metadata") or {})
    assert doc["plan_id"] == "free"  # reverted to free


# ──────────────────────────────────────────────────────────────────────────────
# 9. Expired subscription in MongoDB does NOT grant Pro
# ──────────────────────────────────────────────────────────────────────────────

def test_expired_subscription_in_mongodb_does_not_grant_pro():
    """An expired subscription in MongoDB must not grant Pro (fail-closed)."""
    from lumen.bot.ui import subscription_store, pro_plan_entitlement

    fake_store = _FakeMongoStore()
    backend = _MemoryBackend()
    session_store = SessionStore(client=backend)

    # Expired record
    now = datetime.now(timezone.utc)
    expired_record = {
        "plan_id": "lumen_pro",
        "started_at": (now - timedelta(days=35)).isoformat(),
        "expires_at": (now - timedelta(days=5)).isoformat(),  # expired 5 days ago
        "stars_paid": 2000,
        "charge_id": "tg_charge_expired",
    }
    fake_store.col._docs[666] = {
        "owner_telegram_id": 666,
        "plan_id": "growth",
        "metadata": {"pro_subscription": expired_record},
    }

    # Redis is empty
    assert session_store.load(666) == {}

    with patch.object(subscription_store, "_get_mongo_collection", return_value=fake_store.col), \
         patch.object(subscription_store, "_get_session_store", return_value=session_store):
        ent = pro_plan_entitlement.resolve_pro_entitlement(666)
        limits = pro_plan_entitlement.resolve_plan_limits(666)

    assert ent is None, "Expired subscription must NOT grant Pro!"
    assert limits.is_pro is False


# ──────────────────────────────────────────────────────────────────────────────
# 10. Invoice description mentions database persistence
# ──────────────────────────────────────────────────────────────────────────────

def test_invoice_description_mentions_database_persistence():
    """The invoice description must mention DB persistence (user trust)."""
    from lumen.engine.services.ui_state.pro_plan import pro_plan_invoice_description

    desc = pro_plan_invoice_description()
    # Must mention database / قاعدة البيانات
    assert "قاعدة البيانات" in desc or "database" in desc.lower()
    # Must be within Telegram's 255 char limit
    assert len(desc) <= 255


def test_pro_plan_includes_mentions_persistence():
    """PRO_PLAN_INCLUDES should have a persistence item."""
    from lumen.engine.services.ui_state.pro_plan import PRO_PLAN_INCLUDES

    has_persistence = any(
        "قاعدة البيانات" in inc.label or "database" in inc.label.lower()
        for inc in PRO_PLAN_INCLUDES
    )
    assert has_persistence, "PRO_PLAN_INCLUDES must mention database persistence"


# ──────────────────────────────────────────────────────────────────────────────
# 11. has_active_subscription helper
# ──────────────────────────────────────────────────────────────────────────────

def test_has_active_subscription_true_when_record_exists():
    from lumen.bot.ui import subscription_store

    fake_store = _FakeMongoStore()
    backend = _MemoryBackend()
    session_store = SessionStore(client=backend)

    record = _make_pro_record()
    with patch.object(subscription_store, "_get_mongo_collection", return_value=fake_store.col), \
         patch.object(subscription_store, "_get_session_store", return_value=session_store):
        subscription_store.write_subscription(444, record)
        assert subscription_store.has_active_subscription(444) is True


def test_has_active_subscription_false_when_no_record():
    from lumen.bot.ui import subscription_store

    fake_store = _FakeMongoStore()
    backend = _MemoryBackend()
    session_store = SessionStore(client=backend)

    with patch.object(subscription_store, "_get_mongo_collection", return_value=fake_store.col), \
         patch.object(subscription_store, "_get_session_store", return_value=session_store):
        assert subscription_store.has_active_subscription(555) is False
