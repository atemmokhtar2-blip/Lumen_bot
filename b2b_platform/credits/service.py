"""CreditService — sole application gate for credit mutations (hardened phase 1)."""
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


class CreditService:
    def __init__(self, store: CreditsStore) -> None:
        self._store = store

    def get_wallet(self, tenant_id: str) -> Wallet:
        return self._store.get_wallet(str(tenant_id))

    def ensure_wallet(self, tenant_id: str) -> Wallet:
        return self._store.ensure_wallet(str(tenant_id))

    def credit_credits(
        self, tenant_id: str, amount: int, *, reason: str = "purchase",
        reference_id: str = "", idempotency_key: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> CreditResult:
        return self._store.credit(
            str(tenant_id), int(amount), type_=reason,
            reference_id=reference_id, idempotency_key=idempotency_key, metadata=metadata,
        )

    def deduct_credits(
        self, tenant_id: str, amount: int, *, reason: str = "generation_cost",
        reference_id: str = "", idempotency_key: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> CreditResult:
        return self._store.deduct(
            str(tenant_id), int(amount), type_=reason,
            reference_id=reference_id, idempotency_key=idempotency_key, metadata=metadata,
        )

    def reserve_credits(
        self, tenant_id: str, amount: int, *, reference_id: str = "",
        idempotency_key: str = "",
    ) -> CreditResult:
        return self._store.reserve(
            str(tenant_id), int(amount),
            reference_id=reference_id, idempotency_key=idempotency_key,
        )

    def release_reservation(
        self, tenant_id: str, amount: int, *, reference_id: str = "",
        idempotency_key: str = "",
    ) -> CreditResult:
        return self._store.release_reservation(
            str(tenant_id), int(amount),
            reference_id=reference_id, idempotency_key=idempotency_key,
        )

    def capture_reservation(
        self, tenant_id: str, amount: int, *, reason: str = "generation_cost",
        reference_id: str = "", idempotency_key: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> CreditResult:
        """Spend a prior hold: atomic reserved_balance + current_balance reduction."""
        return self._store.capture_reservation(
            str(tenant_id), int(amount), type_=reason,
            reference_id=reference_id, idempotency_key=idempotency_key, metadata=metadata,
        )

    def reconcile(self, tenant_id: str) -> ReconcileReport:
        return self._store.reconcile(str(tenant_id))

    def list_ledger(self, tenant_id: str, *, limit: int = 100) -> list[LedgerEntry]:
        return self._store.list_ledger(str(tenant_id), limit=limit)

    def cost_for(self, resource_type: str, units: int) -> int:
        rule = self._store.get_pricing(resource_type)
        if not rule:
            return 0
        return int(rule.cost_per_unit) * max(0, int(units))

    def list_pricing(self) -> list[PricingRule]:
        return self._store.list_pricing()


_SVC: CreditService | None = None


def get_credit_service() -> CreditService:
    global _SVC
    if _SVC is not None:
        return _SVC
    dsn = (
        (os.getenv("DATABASE_URL") or "")
        or (os.getenv("POSTGRES_URL") or "")
        or (os.getenv("POSTGRESQL_URL") or "")
    ).strip()
    if dsn:
        from .pg_store import PostgresCreditsStore
        _SVC = CreditService(PostgresCreditsStore(dsn))
        logger.info("CreditService using PostgreSQL")
        return _SVC
    from .memory_store import MemoryCreditsStore
    _SVC = CreditService(MemoryCreditsStore())
    logger.info("CreditService using in-memory store (set DATABASE_URL for production)")
    return _SVC


def reset_credit_service_for_tests() -> None:
    global _SVC
    _SVC = None
