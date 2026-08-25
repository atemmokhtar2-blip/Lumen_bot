"""In-memory credits store — hardened semantics matching Postgres store."""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Optional

from .types import CreditResult, LedgerEntry, PricingRule, ReconcileReport, Wallet


class MemoryCreditsStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._wallets: dict[str, Wallet] = {}
        self._ledger: list[LedgerEntry] = []
        self._idem: dict[str, LedgerEntry] = {}
        self._pricing: dict[str, PricingRule] = {}
        self._seed_pricing()

    def _seed_pricing(self) -> None:
        defaults = [
            ("docker_ram_mb_per_hour", 1, "RAM MB × hour"),
            ("llm_output_token", 1, "per output token unit"),
            ("telegram_message", 1, "per processed message"),
            ("generation_cost", 50, "bot generation job"),
            ("hourly_hosting", 10, "base host hour"),
        ]
        for rt, cost, desc in defaults:
            self._pricing[rt] = PricingRule(rt, cost, True, 1, desc)

    def ensure_wallet(self, tenant_id: str) -> Wallet:
        with self._lock:
            tid = str(tenant_id)
            if tid not in self._wallets:
                self._wallets[tid] = Wallet(tenant_id=tid, updated_at=time.time())
            return self._wallets[tid]

    def get_wallet(self, tenant_id: str) -> Wallet:
        return self.ensure_wallet(tenant_id)

    def _replay(self, key: str, tenant_id: str) -> Optional[CreditResult]:
        if key in self._idem:
            e = self._idem[key]
            return CreditResult(
                ok=True,
                reason="idempotent_replay",
                wallet=self.get_wallet(tenant_id),
                entry=e,
                transaction_id=e.transaction_id,
            )
        return None

    def _append(
        self,
        *,
        tenant_id: str,
        amount: int,
        reservation_delta: int,
        type_: str,
        reference_id: str,
        idempotency_key: str,
        metadata: dict[str, Any],
        wallet: Wallet,
    ) -> LedgerEntry:
        if amount == 0 and reservation_delta == 0:
            raise ValueError("ledger entry must change balance or reservation")
        entry = LedgerEntry(
            transaction_id=f"tx_{uuid.uuid4().hex}",
            tenant_id=str(tenant_id),
            amount=int(amount),
            reservation_delta=int(reservation_delta),
            balance_after=int(wallet.current_balance),
            reserved_after=int(wallet.reserved_balance),
            type=str(type_),
            counterparty="system",
            reference_id=str(reference_id or ""),
            idempotency_key=str(idempotency_key),
            metadata=dict(metadata or {}),
            created_at=time.time(),
        )
        self._ledger.append(entry)
        self._idem[entry.idempotency_key] = entry
        return entry

    def credit(
        self,
        tenant_id: str,
        amount: int,
        *,
        type_: str = "purchase",
        reference_id: str = "",
        idempotency_key: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> CreditResult:
        if amount <= 0:
            return CreditResult(ok=False, reason="amount_must_be_positive")
        key = idempotency_key or f"credit:{tenant_id}:{uuid.uuid4().hex}"
        with self._lock:
            hit = self._replay(key, tenant_id)
            if hit:
                return hit
            w = self.ensure_wallet(tenant_id)
            w.current_balance += int(amount)
            w.updated_at = time.time()
            e = self._append(
                tenant_id=tenant_id, amount=int(amount), reservation_delta=0,
                type_=type_, reference_id=reference_id, idempotency_key=key,
                metadata=metadata or {}, wallet=w,
            )
            return CreditResult(ok=True, wallet=Wallet(**w.__dict__), entry=e, transaction_id=e.transaction_id)

    def deduct(
        self,
        tenant_id: str,
        amount: int,
        *,
        type_: str = "generation_cost",
        reference_id: str = "",
        idempotency_key: str = "",
        metadata: Optional[dict[str, Any]] = None,
        allow_from_reserved: bool = False,
    ) -> CreditResult:
        if amount <= 0:
            return CreditResult(ok=False, reason="amount_must_be_positive")
        key = idempotency_key or f"deduct:{tenant_id}:{uuid.uuid4().hex}"
        with self._lock:
            hit = self._replay(key, tenant_id)
            if hit:
                return hit
            w = self.ensure_wallet(tenant_id)
            available = w.current_balance - w.reserved_balance
            if available < amount:
                return CreditResult(
                    ok=False,
                    reason=f"insufficient_balance:{available}",
                    wallet=Wallet(**w.__dict__),
                )
            w.current_balance -= int(amount)
            w.updated_at = time.time()
            e = self._append(
                tenant_id=tenant_id, amount=-int(amount), reservation_delta=0,
                type_=type_, reference_id=reference_id, idempotency_key=key,
                metadata=metadata or {}, wallet=w,
            )
            return CreditResult(ok=True, wallet=Wallet(**w.__dict__), entry=e, transaction_id=e.transaction_id)

    def reserve(
        self,
        tenant_id: str,
        amount: int,
        *,
        reference_id: str = "",
        idempotency_key: str = "",
    ) -> CreditResult:
        if amount <= 0:
            return CreditResult(ok=False, reason="amount_must_be_positive")
        key = idempotency_key or f"reserve:{tenant_id}:{uuid.uuid4().hex}"
        with self._lock:
            hit = self._replay(key, tenant_id)
            if hit:
                return hit
            w = self.ensure_wallet(tenant_id)
            if w.available < amount:
                return CreditResult(
                    ok=False,
                    reason=f"insufficient_balance_for_reserve:{w.available}",
                    wallet=Wallet(**w.__dict__),
                )
            w.reserved_balance += int(amount)
            w.updated_at = time.time()
            e = self._append(
                tenant_id=tenant_id, amount=0, reservation_delta=int(amount),
                type_="reserve", reference_id=reference_id, idempotency_key=key,
                metadata={"reserved": int(amount)}, wallet=w,
            )
            return CreditResult(ok=True, wallet=Wallet(**w.__dict__), entry=e, transaction_id=e.transaction_id)

    def release_reservation(
        self,
        tenant_id: str,
        amount: int,
        *,
        reference_id: str = "",
        idempotency_key: str = "",
    ) -> CreditResult:
        if amount <= 0:
            return CreditResult(ok=False, reason="amount_must_be_positive")
        key = idempotency_key or f"release:{tenant_id}:{uuid.uuid4().hex}"
        with self._lock:
            hit = self._replay(key, tenant_id)
            if hit:
                return hit
            w = self.ensure_wallet(tenant_id)
            release = min(int(amount), int(w.reserved_balance))
            if release <= 0:
                return CreditResult(ok=False, reason="nothing_reserved", wallet=Wallet(**w.__dict__))
            w.reserved_balance -= release
            w.updated_at = time.time()
            e = self._append(
                tenant_id=tenant_id, amount=0, reservation_delta=-release,
                type_="release_reservation", reference_id=reference_id,
                idempotency_key=key, metadata={"released": release}, wallet=w,
            )
            return CreditResult(ok=True, wallet=Wallet(**w.__dict__), entry=e, transaction_id=e.transaction_id)

    def capture_reservation(
        self,
        tenant_id: str,
        amount: int,
        *,
        type_: str = "generation_cost",
        reference_id: str = "",
        idempotency_key: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> CreditResult:
        """Atomic: reduce reserved AND current_balance by amount (spend the hold)."""
        if amount <= 0:
            return CreditResult(ok=False, reason="amount_must_be_positive")
        key = idempotency_key or f"capture:{tenant_id}:{uuid.uuid4().hex}"
        with self._lock:
            hit = self._replay(key, tenant_id)
            if hit:
                return hit
            w = self.ensure_wallet(tenant_id)
            if w.reserved_balance < amount:
                return CreditResult(
                    ok=False,
                    reason=f"insufficient_reserved:{w.reserved_balance}",
                    wallet=Wallet(**w.__dict__),
                )
            if w.current_balance < amount:
                return CreditResult(
                    ok=False,
                    reason=f"insufficient_balance:{w.current_balance}",
                    wallet=Wallet(**w.__dict__),
                )
            w.reserved_balance -= int(amount)
            w.current_balance -= int(amount)
            w.updated_at = time.time()
            e = self._append(
                tenant_id=tenant_id, amount=-int(amount), reservation_delta=-int(amount),
                type_=type_, reference_id=reference_id, idempotency_key=key,
                metadata=dict(metadata or {}, captured=int(amount)), wallet=w,
            )
            return CreditResult(ok=True, wallet=Wallet(**w.__dict__), entry=e, transaction_id=e.transaction_id)

    def reconcile(self, tenant_id: str) -> ReconcileReport:
        with self._lock:
            w = self.ensure_wallet(tenant_id)
            rows = [e for e in self._ledger if e.tenant_id == str(tenant_id)]
            bal_sum = sum(e.amount for e in rows)
            res_sum = sum(e.reservation_delta for e in rows)
            return ReconcileReport(
                ok=(bal_sum == w.current_balance and res_sum == w.reserved_balance),
                tenant_id=str(tenant_id),
                wallet_balance=w.current_balance,
                ledger_sum=bal_sum,
                wallet_reserved=w.reserved_balance,
                ledger_reservation_sum=res_sum,
                drift_balance=w.current_balance - bal_sum,
                drift_reserved=w.reserved_balance - res_sum,
            )

    def list_ledger(self, tenant_id: str, *, limit: int = 100) -> list[LedgerEntry]:
        with self._lock:
            rows = [e for e in self._ledger if e.tenant_id == str(tenant_id)]
            return list(reversed(rows[-limit:]))

    def get_pricing(self, resource_type: str) -> Optional[PricingRule]:
        r = self._pricing.get(resource_type)
        return r if r and r.is_active else None

    def list_pricing(self) -> list[PricingRule]:
        return [r for r in self._pricing.values() if r.is_active]
