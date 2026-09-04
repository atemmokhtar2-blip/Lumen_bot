"""Phase 3 — caps, multi-worker rate-limit keying, pending vs qualified."""
from __future__ import annotations

import os

import pytest

os.environ.pop("MONGODB_URI", None)
os.environ.setdefault("ENVIRONMENT", "test")

from lumen.application.commands.qualify_referral import QualifyReferralCommand
from lumen.application.commands.register_referral import RegisterReferralCommand
from lumen.application.handlers.referral_handlers import (
    handle_qualify_referral,
    handle_register_referral,
)
from lumen.domain.entities.referral import ReferralError
from lumen.platform.referrals import config as cfg
from lumen.platform.referrals.mongo_repository import (
    MemoryReferralRepository,
    reset_referral_repository_for_tests,
)
import lumen.platform.referrals.mongo_repository as mr


@pytest.fixture()
def repo():
    reset_referral_repository_for_tests()
    mem = MemoryReferralRepository()
    mr._repo = mem
    return mem


def test_pending_not_countable(repo):
    r = handle_register_referral(RegisterReferralCommand(1, 2))
    assert r.ok and r.referral is not None
    assert r.referral.is_countable() is False
    assert repo.count_qualified(1) == 0


def test_message_qualifies_only(repo):
    handle_register_referral(RegisterReferralCommand(1, 2))
    assert handle_qualify_referral(QualifyReferralCommand(2, event="start_ref_only")).error == "event_not_bot_use"
    q = handle_qualify_referral(QualifyReferralCommand(2, event="message"))
    assert q.ok and q.referral is not None and q.referral.is_countable()
    assert repo.count_qualified(1) == 1


def test_self_referral_blocked(repo):
    r = handle_register_referral(RegisterReferralCommand(9, 9))
    assert r.ok is False and r.error == "self_referral_forbidden"


def test_invite_cap_enforced(repo, monkeypatch):
    monkeypatch.setattr(cfg, "REFERRAL_MAX_PER_REFERRER", 3)
    for i in range(3):
        repo.create_pending(77, 700 + i)
    with pytest.raises(ReferralError) as ei:
        repo.create_pending(77, 799)
    assert "cap" in str(ei.value)


def test_duplicate_referred_single_referrer(repo):
    assert handle_register_referral(RegisterReferralCommand(1, 50)).ok
    r2 = handle_register_referral(RegisterReferralCommand(99, 50))
    # second referrer cannot steal — already registered
    assert r2.already_registered or (r2.referral and r2.referral.referrer_telegram_id == 1)


def test_fifty_links_zero_qualified(repo):
    for i in range(50):
        handle_register_referral(RegisterReferralCommand(5, 2000 + i))
    assert repo.count_qualified(5) == 0
    for i in range(50):
        handle_qualify_referral(QualifyReferralCommand(2000 + i, event="message"))
    assert repo.count_qualified(5) == 50


def test_rate_limiter_key_shape():
    """Platform limiter key used for referral register (Redis-safe across workers)."""
    from lumen.platform.rate_limit import get_rate_limiter
    from lumen.platform.referrals.config import REFERRAL_REGISTER_RATE_PER_MIN

    rl = get_rate_limiter()
    key = "referral_register:424242"
    # Should not raise; returns bool
    assert isinstance(
        rl.allow(key, limit=max(1, int(REFERRAL_REGISTER_RATE_PER_MIN)), window_sec=60.0),
        bool,
    )
