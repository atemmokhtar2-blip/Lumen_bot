"""Referral persistence port — implementations live in infrastructure/platform."""
from __future__ import annotations

from typing import Optional, Protocol

from lumen.domain.entities.referral import Referral, ReferralStats


class ReferralRepository(Protocol):
    def create_pending(
        self, referrer_telegram_id: int, referred_telegram_id: int
    ) -> Referral:
        """Register a new invite (link accepted). Fails on self/duplicate."""
        ...

    def get_by_referred(self, referred_telegram_id: int) -> Optional[Referral]:
        ...

    def mark_qualified(self, referred_telegram_id: int) -> Optional[Referral]:
        """Mark referred user as having used the bot (counts toward target)."""
        ...

    def count_qualified(self, referrer_telegram_id: int) -> int:
        ...

    def stats_for(self, referrer_telegram_id: int) -> ReferralStats:
        ...

    def mark_reward_paid(
        self, referrer_telegram_id: int, *, batch_id: str
    ) -> ReferralStats:
        ...
