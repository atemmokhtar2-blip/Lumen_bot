from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RegisterReferralCommand:
    """Record that referred_telegram_id opened a referral link from referrer."""

    referrer_telegram_id: int
    referred_telegram_id: int
