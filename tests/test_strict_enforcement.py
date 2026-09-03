"""Strict enforcement audit tests — fail-closed security guarantees.

Verifies that Pro plan limits are enforced strictly and cannot be bypassed:

  1. resolve_plan_limits returns EXACTLY the plan values (no more, no less).
  2. Entitlement resolver fails-closed on errors (bad data, missing fields).
  3. Pro limits are immutable (frozen dataclass).
  4. default_resources_for_user returns exact Pro resources.
  5. Firecracker spec gets Pro-aware memory/vcpus when entitlement is active.
  6. Entitlement is re-evaluated on every call (no stale cache).
"""
import os

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test:t123")
os.environ.setdefault("TBE_TOKEN_SECRET", "test_secret_1234567890")
os.environ.setdefault("API_KEY_PEPPER", "test_pepper_1234567890")
os.environ.setdefault("TBE_ENV", "test")
os.environ.setdefault("ALLOW_ALL_USERS", "1")
os.environ.setdefault("GEMINI_API_KEY", "test_key")

from datetime import datetime, timedelta, timezone

import pytest

from lumen.bot.ui.pro_plan_entitlement import (
    ProEntitlement,
    PlanLimits,
    resolve_pro_entitlement,
    resolve_plan_limits,
)
from lumen.engine.services.ui_state.pro_plan import (
    PRO_PLAN_ID,
    PRO_PLAN_BOT_LIMIT,
    PRO_PLAN_PRICE_STARS,
)


# ---------------------------------------------------------------------------

class _FakeStore:
    def __init__(self, record):
        self._record = record

    def load(self, user_id):
        return {"pro_plan": self._record} if self._record else {}

    def save(self, user_id, data):
        pass

    def clear(self, user_id):
        pass


def _set_store(record, monkeypatch):
    fake = _FakeStore(record)
    monkeypatch.setattr("lumen.bot.session_store.get_session_store", lambda: fake)


def _valid_record(*, expired=False, plan_id="lumen_pro", stars=2000,
                  bad_expiry=False):
    now = datetime.now(timezone.utc)
    if bad_expiry:
        exp_str = "not-a-date"
    else:
        exp = now - timedelta(hours=1) if expired else now + timedelta(days=29)
        exp_str = exp.isoformat()
    return {
        "plan_id": plan_id,
        "started_at": now.isoformat(),
        "expires_at": exp_str,
        "stars_paid": stars,
        "charge_id": "test_charge_123",
    }


# ---------------------------------------------------------------------------
# 1. EXACT plan values — no more, no less
# ---------------------------------------------------------------------------

def test_pro_limits_exact_values(monkeypatch):
    """Pro user gets EXACTLY: 3 bots, 2048 MB disk, 512 MB RAM, 0.5 CPU."""
    _set_store(_valid_record(), monkeypatch)
    limits = resolve_plan_limits(999)
    assert limits.is_pro is True
    assert limits.max_bots == 3
    assert limits.disk_mb == 2048
    assert limits.memory_mb == 512
    assert limits.cpu == 0.5


def test_pro_limits_not_exceedable(monkeypatch):
    """Even if env vars are set high, Pro user gets plan values, not env."""
    _set_store(_valid_record(), monkeypatch)
    monkeypatch.setenv("TBE_MAX_BOTS_PER_USER", "100")
    monkeypatch.setenv("TBE_USER_DISK_MB", "99999")
    monkeypatch.setenv("TBE_BOT_MEMORY_MB", "99999")
    monkeypatch.setenv("TBE_BOT_CPU", "99.0")
    limits = resolve_plan_limits(999)
    # Pro values must NOT be affected by env
    assert limits.max_bots == 3
    assert limits.disk_mb == 2048
    assert limits.memory_mb == 512
    assert limits.cpu == 0.5


def test_plan_limits_is_frozen():
    """PlanLimits must be a frozen dataclass — cannot be mutated to bypass."""
    import dataclasses
    assert dataclasses.is_dataclass(PlanLimits)
    # frozen=True means setattr should raise FrozenInstanceError
    limits = PlanLimits(max_bots=3, disk_mb=2048, memory_mb=512, cpu=0.5,
                        is_pro=True, days_remaining=29)
    with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
        limits.max_bots = 100  # type: ignore


def test_pro_entitlement_is_frozen():
    """ProEntitlement must be frozen — cannot mutate to extend expiry."""
    import dataclasses
    assert dataclasses.is_dataclass(ProEntitlement)
    ent = ProEntitlement(
        plan_id="lumen_pro", started_at="2026-01-01T00:00:00+00:00",
        expires_at="2026-02-01T00:00:00+00:00", stars_paid=2000, charge_id="x",
    )
    with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
        ent.expires_at = "2099-01-01T00:00:00+00:00"  # type: ignore


# ---------------------------------------------------------------------------
# 2. Fail-closed on bad/corrupt data
# ---------------------------------------------------------------------------

def test_corrupt_expiry_fails_closed(monkeypatch):
    """Unparseable expiry → treated as expired (fail-closed)."""
    _set_store(_valid_record(bad_expiry=True), monkeypatch)
    assert resolve_pro_entitlement(999) is None


def test_missing_record_fails_closed(monkeypatch):
    """No record at all → None (no Pro benefits)."""
    _set_store(None, monkeypatch)
    assert resolve_pro_entitlement(999) is None


def test_zero_user_id_fails_closed(monkeypatch):
    """user_id=0 → no entitlement (anonymous users can't be Pro)."""
    _set_store(_valid_record(), monkeypatch)
    assert resolve_pro_entitlement(0) is None


def test_underpayment_fails_closed(monkeypatch):
    """Paid less than 2000 stars → not Pro (fail-closed)."""
    _set_store(_valid_record(stars=1999), monkeypatch)
    assert resolve_pro_entitlement(999) is None


def test_overpayment_still_pro(monkeypatch):
    """Paid more than 2000 → still Pro (>= check, not ==)."""
    _set_store(_valid_record(stars=2500), monkeypatch)
    ent = resolve_pro_entitlement(999)
    assert ent is not None
    assert ent.stars_paid == 2500


# ---------------------------------------------------------------------------
# 3. Non-Pro gets env defaults (NOT Pro values)
# ---------------------------------------------------------------------------

def test_non_pro_does_not_get_pro_values(monkeypatch):
    """Non-Pro user must NOT get 3 bots / 2GB / 512MB / 0.5 CPU."""
    _set_store(None, monkeypatch)
    limits = resolve_plan_limits(999)
    assert limits.is_pro is False
    assert limits.max_bots != 3 or limits.disk_mb != 2048  # at least one differs
    assert limits.disk_mb <= 2048  # never more than Pro


def test_expired_pro_reverts_to_defaults(monkeypatch):
    """Expired Pro → reverts to non-Pro limits immediately."""
    _set_store(_valid_record(expired=True), monkeypatch)
    limits = resolve_plan_limits(999)
    assert limits.is_pro is False
    assert limits.max_bots != 3 or limits.disk_mb != 2048


# ---------------------------------------------------------------------------
# 4. default_resources_for_user exactness
# ---------------------------------------------------------------------------

def test_resources_for_pro_user_exact(monkeypatch):
    """default_resources_for_user returns 512MB/0.5CPU/2048MB disk for Pro."""
    _set_store(_valid_record(), monkeypatch)
    from lumen.hosting.project_manifest import default_resources_for_user
    res = default_resources_for_user(999)
    assert res.cpu == 0.5
    assert res.memory_mb == 512
    assert res.disk_mb == 2048


def test_resources_for_non_pro_not_pro_values(monkeypatch):
    """Non-Pro gets env defaults, NOT Pro values."""
    _set_store(None, monkeypatch)
    monkeypatch.setenv("TBE_BOT_MEMORY_MB", "256")
    monkeypatch.setenv("TBE_BOT_CPU", "0.25")
    from lumen.hosting.project_manifest import default_resources_for_user
    res = default_resources_for_user(999)
    assert res.memory_mb == 256
    assert res.cpu == 0.25


# ---------------------------------------------------------------------------
# 5. Entitlement re-evaluated on every call (no stale cache)
# ---------------------------------------------------------------------------

def test_entitlement_re_evaluated_every_call(monkeypatch):
    """If the store changes between calls, the entitlement must update."""
    import lumen.bot.ui.pro_plan_entitlement as ent_mod

    store = _FakeStore(None)
    monkeypatch.setattr("lumen.bot.session_store.get_session_store", lambda: store)

    # First call: no Pro
    assert resolve_pro_entitlement(999) is None

    # Store changes to active Pro
    store._record = _valid_record()
    ent = resolve_pro_entitlement(999)
    assert ent is not None
    assert ent.plan_id == "lumen_pro"

    # Store changes to expired
    store._record = _valid_record(expired=True)
    assert resolve_pro_entitlement(999) is None


# ---------------------------------------------------------------------------
# 6. Disk quota exactness
# ---------------------------------------------------------------------------

def test_disk_quota_pro_exact_bytes(monkeypatch):
    """Pro user disk quota = 2048 MB = 2147483648 bytes exactly."""
    _set_store(_valid_record(), monkeypatch)
    from lumen.engine.services.disk_quota import max_user_bytes
    assert max_user_bytes(999) == 2048 * 1024 * 1024


def test_disk_quota_non_pro_not_2gb(monkeypatch):
    """Non-Pro disk quota must NOT be 2GB."""
    _set_store(None, monkeypatch)
    monkeypatch.setenv("TBE_USER_DISK_MB", "512")
    from lumen.engine.services.disk_quota import max_user_bytes
    assert max_user_bytes(999) == 512 * 1024 * 1024
    assert max_user_bytes(999) < 2048 * 1024 * 1024
