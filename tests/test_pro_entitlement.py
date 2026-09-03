"""Tests for Lumen Pro entitlement resolution and hard limit enforcement.

Verifies:
  - resolve_plan_limits returns Pro limits (3 bots, 2GB, 512MB, 0.5 CPU) when
    a valid, non-expired subscription is in the session store.
  - resolve_plan_limits returns env defaults when no subscription / expired / wrong plan.
  - Expiry is checked server-side (expired → not Pro).
  - Underpayment / wrong plan_id → not Pro.
  - max_user_bytes returns 2GB for Pro, 512MB default otherwise.
  - default_resources_for_user returns 512MB/0.5 CPU for Pro, env defaults otherwise.
  - Bot limit: resolve_plan_limits().max_bots == 3 for Pro.
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


# ---------------------------------------------------------------------------
# Helpers — inject a fake session store for deterministic tests
# ---------------------------------------------------------------------------

class _FakeStore:
    """Minimal session store stub that returns a canned record."""

    def __init__(self, record: dict | None):
        self._record = record

    def load(self, user_id: int) -> dict:
        return {"pro_plan": self._record} if self._record else {}

    def save(self, user_id: int, data: dict) -> None:
        pass

    def clear(self, user_id: int) -> None:
        pass


def _set_store(record: dict | None, monkeypatch: pytest.MonkeyPatch):
    """Patch get_session_store to return a fake with the given record."""
    import lumen.bot.ui.pro_plan_entitlement as ent_mod

    fake = _FakeStore(record)
    # The entitlement module imports get_session_store lazily inside the function;
    # patch at the source module so the lazy import picks it up.
    monkeypatch.setattr(
        "lumen.bot.session_store.get_session_store",
        lambda: fake,
    )


def _valid_record(*, expired: bool = False, plan_id: str = "lumen_pro",
                  stars: int = 2000) -> dict:
    now = datetime.now(timezone.utc)
    exp = now - timedelta(hours=1) if expired else now + timedelta(days=29)
    return {
        "plan_id": plan_id,
        "started_at": now.isoformat(),
        "expires_at": exp.isoformat(),
        "stars_paid": stars,
        "charge_id": "test_charge_123",
    }


# ---------------------------------------------------------------------------
# resolve_pro_entitlement
# ---------------------------------------------------------------------------

def test_active_pro_entitlement(monkeypatch):
    _set_store(_valid_record(), monkeypatch)
    ent = resolve_pro_entitlement(999)
    assert ent is not None
    assert ent.plan_id == "lumen_pro"
    assert ent.stars_paid == 2000
    assert not ent.is_expired
    assert ent.days_remaining > 0


def test_expired_pro_not_active(monkeypatch):
    _set_store(_valid_record(expired=True), monkeypatch)
    assert resolve_pro_entitlement(999) is None


def test_wrong_plan_id_not_active(monkeypatch):
    _set_store(_valid_record(plan_id="something_else"), monkeypatch)
    assert resolve_pro_entitlement(999) is None


def test_underpayment_not_active(monkeypatch):
    _set_store(_valid_record(stars=100), monkeypatch)
    assert resolve_pro_entitlement(999) is None


def test_no_record_not_active(monkeypatch):
    _set_store(None, monkeypatch)
    assert resolve_pro_entitlement(999) is None


# ---------------------------------------------------------------------------
# resolve_plan_limits — the core enforcement contract
# ---------------------------------------------------------------------------

def test_pro_limits(monkeypatch):
    _set_store(_valid_record(), monkeypatch)
    limits = resolve_plan_limits(999)
    assert limits.is_pro is True
    assert limits.max_bots == 3, "Pro must allow exactly 3 bots"
    assert limits.disk_mb == 2048, "Pro must get 2 GB (2048 MB) storage"
    assert limits.memory_mb == 512, "Pro must get 512 MB RAM"
    assert limits.cpu == 0.5, "Pro must get 0.5 CPU"
    assert limits.days_remaining > 0


def test_non_pro_limits_env_defaults(monkeypatch):
    monkeypatch.setenv("TBE_MAX_BOTS_PER_USER", "50")
    monkeypatch.setenv("TBE_USER_DISK_MB", "512")
    monkeypatch.setenv("TBE_BOT_MEMORY_MB", "256")
    monkeypatch.setenv("TBE_BOT_CPU", "0.5")
    _set_store(None, monkeypatch)
    limits = resolve_plan_limits(888)
    assert limits.is_pro is False
    assert limits.max_bots == 50
    assert limits.disk_mb == 512
    assert limits.memory_mb == 256
    assert limits.cpu == 0.5
    assert limits.days_remaining == 0


def test_expired_pro_reverts_to_defaults(monkeypatch):
    _set_store(_valid_record(expired=True), monkeypatch)
    monkeypatch.setenv("TBE_MAX_BOTS_PER_USER", "50")
    limits = resolve_plan_limits(999)
    assert limits.is_pro is False
    assert limits.max_bots == 50, "expired Pro must revert to default bot limit"


# ---------------------------------------------------------------------------
# disk_quota integration
# ---------------------------------------------------------------------------

def test_disk_quota_pro_2gb(monkeypatch):
    _set_store(_valid_record(), monkeypatch)
    from lumen.engine.services.disk_quota import max_user_bytes
    assert max_user_bytes(user_id=999) == 2048 * 1024 * 1024


def test_disk_quota_non_pro_default(monkeypatch):
    _set_store(None, monkeypatch)
    monkeypatch.setenv("TBE_USER_DISK_MB", "512")
    from lumen.engine.services.disk_quota import max_user_bytes
    assert max_user_bytes(user_id=888) == 512 * 1024 * 1024


# ---------------------------------------------------------------------------
# project_manifest resources integration
# ---------------------------------------------------------------------------

def test_resources_pro(monkeypatch):
    _set_store(_valid_record(), monkeypatch)
    from lumen.hosting.project_manifest import default_resources_for_user
    res = default_resources_for_user(999)
    assert res.memory_mb == 512
    assert res.cpu == 0.5


def test_resources_non_pro_env(monkeypatch):
    _set_store(None, monkeypatch)
    monkeypatch.setenv("TBE_BOT_MEMORY_MB", "256")
    monkeypatch.setenv("TBE_BOT_CPU", "0.5")
    from lumen.hosting.project_manifest import default_resources_for_user
    res = default_resources_for_user(888)
    assert res.memory_mb == 256
    assert res.cpu == 0.5
