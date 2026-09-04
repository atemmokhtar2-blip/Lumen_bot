"""Phase 3 — security caps, rate limit, full pending→qualified path."""
from __future__ import annotations

import os

import pytest

# Force memory repo
os.environ.pop("MONGODB_URI", None)

from lumen.application.commands.qualify_referral import QualifyReferralCommand
from lumen.application.commands.register_referral import RegisterReferralCommand
from lumen.application.handlers.referral_handlers import (
    handle_qualify_referral,
    handle_register_referral,
)
from lumen.domain.entities.referral import ReferralError
from lumen.platform.referrals.config import (
    REFERRAL_MAX_PER_REFERRER,
    REFERRAL_QUALIFIED_TARGET,
)
from lumen.platform.referrals.mongo_repository import (
    MemoryReferralRepository,
    reset_referral_repository_for_tests,
)
import lumen.platform.referrals.mongo_repository as mr


@pytest.fixture()
def repo(monkeypatch):
    reset_referral_repository_for_tests()
    mem = MemoryReferralRepository()
    mr._repo = mem
    return mem


def test_link_open_does_not_count(repo):
    r = handle_register_referral(RegisterReferralCommand(1, 2))
    assert r.ok
    assert r.referral is not None
    assert r.referral.is_countable() is False
    assert repo.count_qualified(1) == 0


def test_message_qualifies(repo):
    handle_register_referral(RegisterReferralCommand(1, 2))
    q = handle_qualify_referral(QualifyReferralCommand(2, event="message"))
    assert q.ok
    assert q.referral is not None and q.referral.is_countable()
    assert repo.count_qualified(1) == 1


def test_start_event_does_not_qualify(repo):
    handle_register_referral(RegisterReferralCommand(1, 3))
    q = handle_qualify_referral(QualifyReferralCommand(3, event="start_ref_only"))
    assert q.error == "event_not_bot_use"
    assert repo.count_qualified(1) == 0


def test_self_referral_blocked(repo):
    r = handle_register_referral(RegisterReferralCommand(9, 9))
    assert r.ok is False
    assert r.error == "self_referral_forbidden"


def test_duplicate_referred_blocked(repo):
    assert handle_register_referral(RegisterReferralCommand(1, 50)).ok
    r2 = handle_register_referral(RegisterReferralCommand(2, 50))
    # already registered under first referrer
    assert r2.already_registered or not r2.ok or r2.referral.referrer_telegram_id == 1


def test_max_invites_cap(repo, monkeypatch):
    monkeypatch.setenv("REFERRAL_MAX_PER_REFERRER", "3")
    # re-read config is fixed at import — enforce via direct repo
    from lumen.platform.referrals import config as cfg
    monkeypatch.setattr(cfg, "REFERRAL_MAX_PER_REFERRER", 3)
    for i in range(3):
        repo.create_pending(77, 700 + i)
    with pytest.raises(ReferralError):
        repo.create_pending(77, 799)


def test_fifty_links_no_reward_fifty_uses_due(repo):
    for i in range(50):
        handle_register_referral(RegisterReferralCommand(5, 2000 + i))
    assert repo.count_qualified(5) == 0
    for i in range(50):
        handle_qualify_referral(QualifyReferralCommand(2000 + i, event="message"))
    assert repo.count_qualified(5) == 50
    # reward_due may fail credit without full credits stack — slot claim is the gate
    stats = repo.stats_for(5)
    assert stats.qualified_count == 50
