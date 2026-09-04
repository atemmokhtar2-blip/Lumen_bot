from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QualifyReferralCommand:
    """Mark referred user as having used the bot; may unlock referrer reward."""

    referred_telegram_id: int
    event: str = "message"
