"""CreditService — sole gate; double-entry stores only."""
from __future__ import annotations

import logging
import os
from typing import Any, Optional, Protocol

from .types import CreditResult, LedgerEntry, PricingRule, ReconcileReport, Wallet

logger = logging.getLogger(__name__)


class CreditsStore(Protocol):
    def ensure_wallet(self, tenant_id: str) -> Wallet: ...
    def get_wallet(self, tenant_id: str) -> Wallet: ...
    def credit(self, tenant_id: str, amount: int, **kwargs: Any) -> CreditResult: ...
    def deduct(self, tenant_id: str, amount: int, **kwargs: Any) -> CreditResult: ...
    def reserve(self, tenant_id: str, amount: int, **kwargs: Any) -> CreditResult: ...
    def release_reservation(self, tenant_id: str, amount: int, **kwargs: Any) -> CreditResult: ...
    def capture_reservation(self, tenant_id: str, amount: int, **kwargs: Any) -> CreditResult: ...
    def reconcile(self, tenant_id: str) -> ReconcileReport: ...
    def list_ledger(self, tenant_id: str, *, limit: int = 100) -> list[LedgerEntry]: ...
    def get_pricing(self, resource_type: str) -> Optional[PricingRule]: ...
    def list_pricing(self) -> list[PricingRule]: ...
    def expire_promotional(self, tenant_id: str) -> CreditResult: ...


class CreditService:
    def __init__(self, store: CreditsStore) -> None:
        self._store = store

    def get_wallet(self, tenant_id: str) -> Wallet:
        # Always surface post-expiry truth (no stale promotional balance)
        return self.ensure_fresh_wallet(str(tenant_id))

    def ensure_wallet(self, tenant_id: str) -> Wallet:
        return self.ensure_fresh_wallet(str(tenant_id))

    def credit_credits(self, tenant_id, amount, *, reason="purchase", reference_id="",
                       idempotency_key="", metadata=None,
                       promotional: bool = False, promo_expires_at: float = 0.0) -> CreditResult:
        reason = str(reason or "purchase").strip() or "purchase"
        promotional = bool(promotional)
        exp = float(promo_expires_at or 0)

        # Privilege rules — close grant/expiry loopholes
        _PROMO_REASONS = {"welcome_grant", "promo_grant", "referral_bonus"}
        if promotional and reason not in _PROMO_REASONS:
            return CreditResult(
                ok=False,
                reason="promotional_requires_promo_reason",
            )
        if reason in _PROMO_REASONS and not promotional:
            return CreditResult(
                ok=False,
                reason="promo_reason_requires_promotional_flag",
            )
        if promotional and exp <= 0:
            # Fail closed: promotional without expiry is a free infinite grant
            return CreditResult(
                ok=False,
                reason="promotional_requires_expiry",
            )
        if reason == "welcome_grant":
            # Only the canonical idempotency key shape may mint welcome packs
            key = str(idempotency_key or "")
            if not key.startswith("welcome-grant-"):
                return CreditResult(ok=False, reason="welcome_grant_key_required")

        result = self._store.credit(
            str(tenant_id), int(amount), type_=reason, reference_id=reference_id,
            idempotency_key=idempotency_key, metadata=metadata,
            promotional=promotional, promo_expires_at=exp,
        )
        if result.ok:
            try:
                from lumen.platform.balance_lifecycle import get_balance_lifecycle
                get_balance_lifecycle().clear_suspension_on_credit(str(tenant_id))
                # refresh baseline for threshold % if purchase (not pure welcome promo)
                if reason in {"purchase", "topup", "stripe_credit"}:
                    w = result.wallet or self.get_wallet(str(tenant_id))
                    get_balance_lifecycle().set_baseline(str(tenant_id), int(w.current_balance))
            except Exception:
                pass
        return result

    def deduct_credits(self, tenant_id, amount, *, reason="generation_cost",
                       reference_id="", idempotency_key="", metadata=None) -> CreditResult:
        self.expire_promotional(str(tenant_id))
        return self._store.deduct(
            str(tenant_id), int(amount), type_=reason, reference_id=reference_id,
            idempotency_key=idempotency_key, metadata=metadata,
        )

    def reserve_credits(self, tenant_id, amount, *, reference_id="",
                        idempotency_key="") -> CreditResult:
        self.expire_promotional(str(tenant_id))
        return self._store.reserve(
            str(tenant_id), int(amount), reference_id=reference_id,
            idempotency_key=idempotency_key,
        )

    def release_reservation(self, tenant_id, amount, *, reference_id="",
                            idempotency_key="") -> CreditResult:
        self.expire_promotional(str(tenant_id))
        return self._store.release_reservation(
            str(tenant_id), int(amount), reference_id=reference_id,
            idempotency_key=idempotency_key,
        )

    def capture_reservation(self, tenant_id, amount, *, reason="generation_cost",
                            reference_id="", idempotency_key="", metadata=None) -> CreditResult:
        self.expire_promotional(str(tenant_id))
        return self._store.capture_reservation(
            str(tenant_id), int(amount), type_=reason, reference_id=reference_id,
            idempotency_key=idempotency_key, metadata=metadata,
        )

    def reconcile(self, tenant_id: str) -> ReconcileReport:
        return self._store.reconcile(str(tenant_id))

    def list_ledger(self, tenant_id: str, *, limit: int = 100) -> list[LedgerEntry]:
        return self._store.list_ledger(str(tenant_id), limit=limit)

    def cost_for(self, resource_type: str, units: int) -> int:
        rule = self._store.get_pricing(resource_type)
        return int(rule.cost_per_unit) * max(0, int(units)) if rule else 0

    def list_pricing(self) -> list[PricingRule]:
        return self._store.list_pricing()


    def expire_promotional(self, tenant_id: str) -> CreditResult:
        """Burn unused promotional balance past promo_expires_at."""
        return self._store.expire_promotional(str(tenant_id))

    def ensure_fresh_wallet(self, tenant_id: str) -> Wallet:
        """Expire promo if needed, then return wallet (store-level, no recurse)."""
        self.expire_promotional(str(tenant_id))
        return self._store.get_wallet(str(tenant_id))


_SVC: CreditService | None = None


def get_credit_service() -> CreditService:
    global _SVC
    if _SVC is not None:
        return _SVC
    dsn = (os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or os.getenv("POSTGRESQL_URL") or "").strip()
    if dsn:
        from .pg_store import PostgresCreditsStore
        _SVC = CreditService(PostgresCreditsStore(dsn))
        return _SVC
    from .memory_store import MemoryCreditsStore
    _SVC = CreditService(MemoryCreditsStore())
    return _SVC


def reset_credit_service_for_tests() -> None:
    global _SVC
    _SVC = None
