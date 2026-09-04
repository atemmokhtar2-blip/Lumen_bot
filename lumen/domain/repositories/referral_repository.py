"""Referral persistence port."""
from __future__ import annotations

from typing import Optional, Protocol

from lumen.domain.entities.referral import Referral, ReferralStats


class ReferralRepository(Protocol):
    def ensure_indexes(self) -> None:
        """Create unique referred_telegram_id + referrer/status indexes."""
        ...

    def create_pending(
        self, referrer_telegram_id: int, referred_telegram_id: int
    ) -> Referral:
        """Insert pending invite. Raises on self-referral or duplicate referred."""
        ...

    def get_by_referred(self, referred_telegram_id: int) -> Optional[Referral]:
        ...

    def mark_qualified(self, referred_telegram_id: int) -> Optional[Referral]:
        """pending → qualified after bot use. No-op if already qualified."""
        ...

    def count_qualified(self, referrer_telegram_id: int) -> int:
        ...

    def stats_for(self, referrer_telegram_id: int) -> ReferralStats:
        ...

    def mark_reward_paid(
        self, referrer_telegram_id: int, *, batch_id: str
    ) -> ReferralStats:
        ...
