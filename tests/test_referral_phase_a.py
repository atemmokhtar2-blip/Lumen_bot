"""Referral phase A — domain + in-memory repository behaviour."""
from __future__ import annotations

import pytest

from lumen.domain.entities.referral import Referral, ReferralError, ReferralStats
from lumen.domain.services.referral_policy import is_reward_due, should_count_as_bot_use
from lumen.domain.value_objects.referral_status import ReferralStatus
from lumen.platform.referrals.config import (
    REFERRAL_QUALIFIED_TARGET,
    REFERRAL_REWARD_USD,
    bot_username_link,
    parse_referrer_from_start_payload,
    referral_deep_link_payload,
)
from lumen.platform.referrals.mongo_repository import MemoryReferralRepository
from lumen.platform.referrals.schema import REFERRAL_INDEXES


def test_create_pending_and_duplicate():
    repo = MemoryReferralRepository()
    r = repo.create_pending(100, 200)
    assert r.status is ReferralStatus.PENDING
    assert r.is_countable() is False
    with pytest.raises(ReferralError):
        repo.create_pending(100, 200)
    with pytest.raises(ReferralError):
        repo.create_pending(9, 9)


def test_only_bot_use_qualification_counts():
    repo = MemoryReferralRepository()
    repo.create_pending(1, 2)
    repo.create_pending(1, 3)
    # still pending — 0 qualified
    assert repo.count_qualified(1) == 0
    assert should_count_as_bot_use("start_ref_only") is False
    # simulate bot use
    if should_count_as_bot_use("message"):
        repo.mark_qualified(2)
    assert repo.count_qualified(1) == 1
    st = repo.stats_for(1)
    assert st.qualified_count == 1
    assert st.pending_count == 1


def test_reward_gate_fifty_qualified_not_fifty_links():
    repo = MemoryReferralRepository()
    for i in range(50):
        repo.create_pending(7, 1000 + i)
    # 50 link opens only
    assert repo.count_qualified(7) == 0
    assert is_reward_due(repo.stats_for(7), target=50) is False
    for i in range(50):
        repo.mark_qualified(1000 + i)
    assert repo.count_qualified(7) == 50
    assert is_reward_due(repo.stats_for(7), target=50) is True
    repo.mark_reward_paid(7, batch_id="batch-1")
    assert is_reward_due(repo.stats_for(7), target=50) is False


def test_defaults_and_unique_index_declared():
    assert REFERRAL_QUALIFIED_TARGET == 50
    assert REFERRAL_REWARD_USD == 5
    assert any(i.get("unique") for i in REFERRAL_INDEXES)
    assert "start=ref_1" in bot_username_link("lumen_bot", 1)
    assert parse_referrer_from_start_payload(referral_deep_link_payload(42)) == 42
