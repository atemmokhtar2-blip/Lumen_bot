"""Referral persistence port."""
from __future__ import annotations

from typing import Any, Optional, Protocol

from lumen.domain.entities.referral import Referral, ReferralStats


class ReferralRepository(Protocol):
    def ensure_indexes(self) -> None: ...

    def create_pending(
        self, referrer_telegram_id: int, referred_telegram_id: int
    ) -> Referral: ...

    def get_by_referred(self, referred_telegram_id: int) -> Optional[Referral]: ...

    def mark_qualified(self, referred_telegram_id: int) -> Optional[Referral]: ...

    def count_qualified(self, referrer_telegram_id: int) -> int: ...

    def count_for_referrer(self, referrer_telegram_id: int) -> int: ...

    def stats_for(self, referrer_telegram_id: int) -> ReferralStats: ...

    def system_stats(self) -> dict[str, int]: ...

    def top_referrers(self, *, limit: int = 10) -> list[dict[str, Any]]: ...

    def claim_reward_slot(
        self,
        referrer_telegram_id: int,
        *,
        batch_id: str,
        min_qualified: int,
    ) -> bool: ...

    def release_reward_slot(self, referrer_telegram_id: int) -> None: ...

    def mark_reward_paid(
        self, referrer_telegram_id: int, *, batch_id: str
    ) -> ReferralStats: ...
