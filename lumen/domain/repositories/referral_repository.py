"""Referral persistence port."""
from __future__ import annotations

from typing import Optional, Protocol

from lumen.domain.entities.referral import Referral, ReferralStats


class ReferralRepository(Protocol):
    def ensure_indexes(self) -> None: ...

    def create_pending(
        self, referrer_telegram_id: int, referred_telegram_id: int
    ) -> Referral: ...

    def get_by_referred(self, referred_telegram_id: int) -> Optional[Referral]: ...

    def mark_qualified(self, referred_telegram_id: int) -> Optional[Referral]: ...

    def count_qualified(self, referrer_telegram_id: int) -> int: ...

    def stats_for(self, referrer_telegram_id: int) -> ReferralStats: ...

    def claim_reward_slot(
        self,
        referrer_telegram_id: int,
        *,
        batch_id: str,
        min_qualified: int,
    ) -> bool:
        """Atomically claim unpaid reward when qualified_count >= min_qualified.

        Returns True only for the first successful claim (race-safe).
        """
        ...

    def release_reward_slot(self, referrer_telegram_id: int) -> None:
        """Rollback claim if credit grant failed."""
        ...

    def mark_reward_paid(
        self, referrer_telegram_id: int, *, batch_id: str
    ) -> ReferralStats: ...
