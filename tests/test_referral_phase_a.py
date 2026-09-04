"""Phase A — strong domain rules for referrals."""
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
from lumen.platform.referrals.schema import REFERRAL_INDEXES, REFERRAL_STATS_INDEXES


def test_pending_does_not_count():
    r = Referral.create_pending(10, 20)
    assert r.status is ReferralStatus.PENDING
    assert r.is_countable() is False


def test_qualify_after_bot_use_counts():
    r = Referral.create_pending(10, 20)
    r.qualify()
    assert r.status is ReferralStatus.QUALIFIED
    assert r.is_countable() is True
    assert r.qualified_at and r.qualified_at > 0


def test_self_referral_forbidden():
    with pytest.raises(ReferralError):
        Referral.create_pending(10, 10)


def test_invalid_ids_forbidden():
    with pytest.raises(ReferralError):
        Referral.create_pending(0, 20)


def test_link_open_event_does_not_qualify_policy():
    assert should_count_as_bot_use("start_ref_only") is False
    assert should_count_as_bot_use("message") is True
    assert should_count_as_bot_use("generation_success") is True


def test_reward_due_only_at_target_qualified():
    s = ReferralStats(referrer_telegram_id=1, qualified_count=49, reward_paid=False)
    assert is_reward_due(s, target=50) is False
    s.qualified_count = 50
    assert is_reward_due(s, target=50) is True
    s.reward_paid = True
    assert is_reward_due(s, target=50) is False


def test_deep_link_and_public_url():
    assert referral_deep_link_payload(7631249810) == "ref_7631249810"
    assert parse_referrer_from_start_payload("ref_7631249810") == 7631249810
    assert "start=ref_7631249810" in bot_username_link("lumen_bot", 7631249810)


def test_defaults_and_indexes_declared():
    assert REFERRAL_QUALIFIED_TARGET == 50
    assert REFERRAL_REWARD_USD == 5
    assert any(i.get("unique") for i in REFERRAL_INDEXES)
    assert any(i.get("unique") for i in REFERRAL_STATS_INDEXES)
