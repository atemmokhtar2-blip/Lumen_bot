"""Phase A — referral domain + config (no I/O)."""
from __future__ import annotations

from lumen.domain.entities.referral import Referral, ReferralStats
from lumen.domain.value_objects.referral_status import ReferralStatus
from lumen.platform.referrals.config import (
    REFERRAL_QUALIFIED_TARGET,
    REFERRAL_REWARD_USD,
    parse_referrer_from_start_payload,
    referral_deep_link_payload,
)


def test_status_pending_does_not_count():
    r = Referral(referrer_telegram_id=1, referred_telegram_id=2, status=ReferralStatus.PENDING)
    assert r.is_countable() is False


def test_status_qualified_counts():
    r = Referral(referrer_telegram_id=1, referred_telegram_id=2, status=ReferralStatus.QUALIFIED)
    assert r.is_countable() is True


def test_deep_link_roundtrip():
    payload = referral_deep_link_payload(7631249810)
    assert payload == "ref_7631249810"
    assert parse_referrer_from_start_payload(payload) == 7631249810
    assert parse_referrer_from_start_payload("conversation_abc") is None
    assert parse_referrer_from_start_payload("ref_0") is None


def test_reward_target_defaults():
    assert REFERRAL_QUALIFIED_TARGET == 50
    assert REFERRAL_REWARD_USD == 5


def test_stats_shape():
    s = ReferralStats(referrer_telegram_id=1, total_invited=10, qualified_count=3, pending_count=7)
    d = s.public_dict()
    assert d["qualified_count"] == 3
    assert d["pending_count"] == 7
