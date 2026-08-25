"""In-memory credits store — identical semantics for unit tests (no Postgres)."""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Optional

from .types import CreditResult, LedgerEntry, PricingRule, Wallet


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
            ("llm_output_token", 1, "per output token unit (scaled)"),
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

    def _append(
        self,
        *,
        tenant_id: str,
        amount: int,
        type_: str,
        reference_id: str,
        idempotency_key: str,
        metadata: dict[str, Any],
        wallet: Wallet,
    ) -> LedgerEntry:
        entry = LedgerEntry(
            transaction_id=f"tx_{uuid.uuid4().hex}",
            tenant_id=str(tenant_id),
            amount=int(amount),
            balance_after=int(wallet.current_balance),
            type=str(type_),
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
            if key in self._idem:
                e = self._idem[key]
                return CreditResult(
                    ok=True, reason="idempotent_replay", wallet=self.get_wallet(tenant_id),
                    entry=e, transaction_id=e.transaction_id,
                )
            w = self.ensure_wallet(tenant_id)
            w.current_balance += int(amount)
            w.updated_at = time.time()
            e = self._append(
                tenant_id=tenant_id, amount=int(amount), type_=type_,
                reference_id=reference_id, idempotency_key=key,
                metadata=metadata or {}, wallet=w,
            )
            return CreditResult(ok=True, wallet=w, entry=e, transaction_id=e.transaction_id)

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
            if key in self._idem:
                e = self._idem[key]
                return CreditResult(
                    ok=True, reason="idempotent_replay", wallet=self.get_wallet(tenant_id),
                    entry=e, transaction_id=e.transaction_id,
                )
            w = self.ensure_wallet(tenant_id)
            available = w.current_balance - w.reserved_balance
            if available < amount:
                return CreditResult(ok=False, reason=f"insufficient_balance:{available}", wallet=w)
            w.current_balance -= int(amount)
            w.updated_at = time.time()
            e = self._append(
                tenant_id=tenant_id, amount=-int(amount), type_=type_,
                reference_id=reference_id, idempotency_key=key,
                metadata=metadata or {}, wallet=w,
            )
            return CreditResult(ok=True, wallet=w, entry=e, transaction_id=e.transaction_id)

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
            # reservations are not ledger rows by default; track via metadata ledger optional
            if key in self._idem:
                e = self._idem[key]
                return CreditResult(ok=True, reason="idempotent_replay", wallet=self.get_wallet(tenant_id), entry=e, transaction_id=e.transaction_id)
            w = self.ensure_wallet(tenant_id)
            if (w.current_balance - w.reserved_balance) < amount:
                return CreditResult(
                    ok=False,
                    reason=f"insufficient_balance_for_reserve:{w.current_balance - w.reserved_balance}",
                    wallet=w,
                )
            w.reserved_balance += int(amount)
            w.updated_at = time.time()
            e = self._append(
                tenant_id=tenant_id, amount=0, type_="reserve",
                reference_id=reference_id, idempotency_key=key,
                metadata={"reserved": int(amount)}, wallet=w,
            )
            # amount 0 reserve marker — balance_after unchanged
            return CreditResult(ok=True, wallet=w, entry=e, transaction_id=e.transaction_id)

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
            if key in self._idem:
                e = self._idem[key]
                return CreditResult(ok=True, reason="idempotent_replay", wallet=self.get_wallet(tenant_id), entry=e, transaction_id=e.transaction_id)
            w = self.ensure_wallet(tenant_id)
            release = min(int(amount), int(w.reserved_balance))
            w.reserved_balance -= release
            w.updated_at = time.time()
            e = self._append(
                tenant_id=tenant_id, amount=0, type_="release_reservation",
                reference_id=reference_id, idempotency_key=key,
                metadata={"released": release}, wallet=w,
            )
            return CreditResult(ok=True, wallet=w, entry=e, transaction_id=e.transaction_id)

    def list_ledger(self, tenant_id: str, *, limit: int = 100) -> list[LedgerEntry]:
        with self._lock:
            rows = [e for e in self._ledger if e.tenant_id == str(tenant_id)]
            return list(reversed(rows[-limit:]))

    def get_pricing(self, resource_type: str) -> Optional[PricingRule]:
        r = self._pricing.get(resource_type)
        if r and r.is_active:
            return r
        return None

    def list_pricing(self) -> list[PricingRule]:
        return [r for r in self._pricing.values() if r.is_active]
