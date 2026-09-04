"""Reward claim is atomic; only bot-use counts toward target."""
from __future__ import annotations

import os

import pytest

os.environ.pop("MONGODB_URI", None)

from lumen.application.commands.qualify_referral import QualifyReferralCommand
from lumen.application.commands.register_referral import RegisterReferralCommand
from lumen.application.handlers.referral_handlers import (
    handle_qualify_referral,
    handle_register_referral,
)
from lumen.platform.referrals import config as cfg
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
    # small target for test speed
    monkeypatch.setattr(cfg, "REFERRAL_QUALIFIED_TARGET", 3)
    return mem


def test_claim_slot_only_once(repo):
    for i in range(3):
        handle_register_referral(RegisterReferralCommand(1, 10 + i))
        handle_qualify_referral(QualifyReferralCommand(10 + i, event="message"))
    assert repo.count_qualified(1) == 3
    # First claim wins
    assert repo.claim_reward_slot(1, batch_id="b1", min_qualified=3) is True
    assert repo.claim_reward_slot(1, batch_id="b2", min_qualified=3) is False
    stats = repo.stats_for(1)
    assert stats.reward_paid is True


def test_release_allows_reclaim(repo):
    for i in range(3):
        handle_register_referral(RegisterReferralCommand(2, 20 + i))
        handle_qualify_referral(QualifyReferralCommand(20 + i, event="message"))
    assert repo.claim_reward_slot(2, batch_id="x", min_qualified=3) is True
    repo.release_reward_slot(2)
    assert repo.claim_reward_slot(2, batch_id="y", min_qualified=3) is True
