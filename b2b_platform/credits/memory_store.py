"""In-memory double-entry credits store."""
from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from typing import Any, Optional

from .accounts import (
    SYSTEM_HOLDS,
    SYSTEM_REVENUE,
    SYSTEM_TREASURY,
    user_wallet_account,
    validate_amount,
    validate_idempotency_key,
)
from .types import CreditResult, LedgerEntry, LedgerLeg, PricingRule, ReconcileReport, Wallet


def _hash_entry(prev: str, payload: dict) -> str:
    raw = prev + json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


class MemoryCreditsStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._wallets: dict[str, Wallet] = {}
        self._entries: list[LedgerEntry] = []
        self._idem: dict[str, LedgerEntry] = {}
        self._pricing: dict[str, PricingRule] = {}
        self._last_hash = ""
        self._seed_pricing()
        # system accounts exist implicitly

    def _seed_pricing(self) -> None:
        for rt, cost, desc in [
            ("docker_ram_mb_per_hour", 1, "RAM MB × hour"),
            ("llm_output_token", 1, "per output token unit"),
            ("telegram_message", 1, "per processed message"),
            ("generation_cost", 50, "bot generation job"),
            ("hourly_hosting", 10, "base host hour"),
        ]:
            self._pricing[rt] = PricingRule(rt, cost, True, 1, desc)

    def ensure_wallet(self, tenant_id: str) -> Wallet:
        with self._lock:
            tid = str(tenant_id)
            if tid not in self._wallets:
                self._wallets[tid] = Wallet(
                    tenant_id=tid, account_id=user_wallet_account(tid), updated_at=time.time()
                )
            return self._wallets[tid]

    def get_wallet(self, tenant_id: str) -> Wallet:
        return self.ensure_wallet(tenant_id)

    def _replay(self, key: str, tenant_id: str) -> Optional[CreditResult]:
        if key in self._idem:
            e = self._idem[key]
            return CreditResult(
                ok=True, reason="idempotent_replay",
                wallet=Wallet(**self.get_wallet(tenant_id).__dict__),
                entry=e, transaction_id=e.transaction_id,
            )
        return None

    def _balanced(self, legs: list[LedgerLeg]) -> bool:
        deb = sum(x.amount for x in legs if x.side == "debit")
        cre = sum(x.amount for x in legs if x.side == "credit")
        return deb == cre and deb > 0

    def _commit(
        self,
        *,
        tenant_id: str,
        type_: str,
        legs: list[LedgerLeg],
        reference_id: str,
        idempotency_key: str,
        metadata: dict[str, Any],
        wallet: Wallet,
    ) -> LedgerEntry:
        if not self._balanced(legs):
            raise RuntimeError("unbalanced_double_entry")
        tid = str(tenant_id)
        tx_id = f"tx_{uuid.uuid4().hex}"
        now = time.time()
        payload = {
            "transaction_id": tx_id,
            "tenant_id": tid,
            "type": type_,
            "legs": [{"a": x.account_id, "s": x.side, "n": x.amount} for x in legs],
            "reference_id": reference_id,
            "idempotency_key": idempotency_key,
            "created_at": now,
        }
        prev = self._last_hash
        h = _hash_entry(prev, payload)
        entry = LedgerEntry(
            transaction_id=tx_id,
            tenant_id=tid,
            type=type_,
            legs=list(legs),
            balance_after=int(wallet.current_balance),
            reserved_after=int(wallet.reserved_balance),
            reference_id=str(reference_id or ""),
            idempotency_key=str(idempotency_key),
            prev_hash=prev,
            entry_hash=h,
            metadata=dict(metadata or {}),
            created_at=now,
        )
        self._entries.append(entry)
        self._idem[idempotency_key] = entry
        self._last_hash = h
        return entry

    def credit(
        self, tenant_id: str, amount: int, *, type_: str = "purchase",
        reference_id: str = "", idempotency_key: str = "",
        metadata: Optional[dict[str, Any]] = None,
        promotional: bool = False, promo_expires_at: float = 0.0,
    ) -> CreditResult:
        err = validate_amount(amount)
        if err:
            return CreditResult(ok=False, reason=err)
        key = idempotency_key or f"credit:{tenant_id}:{uuid.uuid4().hex}"
        err = validate_idempotency_key(key)
        if err:
            return CreditResult(ok=False, reason=err)
        with self._lock:
            hit = self._replay(key, tenant_id)
            if hit:
                return hit
            w = self.ensure_wallet(tenant_id)
            wa = user_wallet_account(tenant_id)
            # Purchase: debit treasury, credit user wallet
            legs = [
                LedgerLeg(SYSTEM_TREASURY, "debit", int(amount)),
                LedgerLeg(wa, "credit", int(amount)),
            ]
            w.current_balance += int(amount)
            if promotional:
                w.promotional_balance = int(w.promotional_balance) + int(amount)
                if promo_expires_at and float(promo_expires_at) > 0:
                    # keep the earliest non-zero expiry if already set
                    if not w.promo_expires_at or float(promo_expires_at) < float(w.promo_expires_at):
                        w.promo_expires_at = float(promo_expires_at)
            w.updated_at = time.time()
            e = self._commit(
                tenant_id=tenant_id, type_=type_, legs=legs,
                reference_id=reference_id, idempotency_key=key,
                metadata=metadata or {}, wallet=w,
            )
            return CreditResult(ok=True, wallet=Wallet(**w.__dict__), entry=e, transaction_id=e.transaction_id)

    def deduct(
        self, tenant_id: str, amount: int, *, type_: str = "generation_cost",
        reference_id: str = "", idempotency_key: str = "",
        metadata: Optional[dict[str, Any]] = None,
        allow_from_reserved: bool = False,
    ) -> CreditResult:
        err = validate_amount(amount)
        if err:
            return CreditResult(ok=False, reason=err)
        key = idempotency_key or f"deduct:{tenant_id}:{uuid.uuid4().hex}"
        err = validate_idempotency_key(key)
        if err:
            return CreditResult(ok=False, reason=err)
        with self._lock:
            hit = self._replay(key, tenant_id)
            if hit:
                return hit
            w = self.ensure_wallet(tenant_id)
            # Auto-expire unused promo before spend
            self._expire_promotional_unlocked(w, tenant_id)
            if w.available < amount:
                return CreditResult(
                    ok=False, reason=f"insufficient_balance:{w.available}",
                    wallet=Wallet(**w.__dict__),
                )
            wa = user_wallet_account(tenant_id)
            # Usage: debit user wallet, credit revenue
            legs = [
                LedgerLeg(wa, "debit", int(amount)),
                LedgerLeg(SYSTEM_REVENUE, "credit", int(amount)),
            ]
            w.current_balance -= int(amount)
            # Deduction priority: promotional first
            promo_take = min(int(w.promotional_balance), int(amount))
            if promo_take:
                w.promotional_balance = int(w.promotional_balance) - promo_take
            w.updated_at = time.time()
            e = self._commit(
                tenant_id=tenant_id, type_=type_, legs=legs,
                reference_id=reference_id, idempotency_key=key,
                metadata=metadata or {}, wallet=w,
            )
            return CreditResult(ok=True, wallet=Wallet(**w.__dict__), entry=e, transaction_id=e.transaction_id)

    def reserve(
        self, tenant_id: str, amount: int, *, reference_id: str = "",
        idempotency_key: str = "",
    ) -> CreditResult:
        err = validate_amount(amount)
        if err:
            return CreditResult(ok=False, reason=err)
        key = idempotency_key or f"reserve:{tenant_id}:{uuid.uuid4().hex}"
        err = validate_idempotency_key(key)
        if err:
            return CreditResult(ok=False, reason=err)
        with self._lock:
            hit = self._replay(key, tenant_id)
            if hit:
                return hit
            w = self.ensure_wallet(tenant_id)
            if w.available < amount:
                return CreditResult(
                    ok=False, reason=f"insufficient_balance_for_reserve:{w.available}",
                    wallet=Wallet(**w.__dict__),
                )
            wa = user_wallet_account(tenant_id)
            # Hold: debit wallet available path → credit holds (still owned by user economically)
            legs = [
                LedgerLeg(wa, "debit", int(amount)),
                LedgerLeg(SYSTEM_HOLDS, "credit", int(amount)),
            ]
            # Projection: reserved up, current unchanged for "available" math
            # Double-entry moved value to holds; wallet current stays, reserved increases
            # Adjust model: on reserve we only bump reserved without changing current
            # so legs for reserve are memorandum: balanced via holds contra user_hold account
            # Simpler world model used here:
            # reserve does NOT move current_balance; internal reserved only + memorandum legs
            # balanced: debit user_hold_memo, credit system_holds with same amount without touching current
            legs = [
                LedgerLeg(f"hold:{tenant_id}", "debit", int(amount)),
                LedgerLeg(SYSTEM_HOLDS, "credit", int(amount)),
            ]
            w.reserved_balance += int(amount)
            w.updated_at = time.time()
            e = self._commit(
                tenant_id=tenant_id, type_="reserve", legs=legs,
                reference_id=reference_id, idempotency_key=key,
                metadata={"reserved": int(amount)}, wallet=w,
            )
            return CreditResult(ok=True, wallet=Wallet(**w.__dict__), entry=e, transaction_id=e.transaction_id)

    def release_reservation(
        self, tenant_id: str, amount: int, *, reference_id: str = "",
        idempotency_key: str = "",
    ) -> CreditResult:
        err = validate_amount(amount)
        if err:
            return CreditResult(ok=False, reason=err)
        key = idempotency_key or f"release:{tenant_id}:{uuid.uuid4().hex}"
        err = validate_idempotency_key(key)
        if err:
            return CreditResult(ok=False, reason=err)
        with self._lock:
            hit = self._replay(key, tenant_id)
            if hit:
                return hit
            w = self.ensure_wallet(tenant_id)
            release = min(int(amount), int(w.reserved_balance))
            if release <= 0:
                return CreditResult(ok=False, reason="nothing_reserved", wallet=Wallet(**w.__dict__))
            legs = [
                LedgerLeg(SYSTEM_HOLDS, "debit", release),
                LedgerLeg(f"hold:{tenant_id}", "credit", release),
            ]
            w.reserved_balance -= release
            w.updated_at = time.time()
            e = self._commit(
                tenant_id=tenant_id, type_="release_reservation", legs=legs,
                reference_id=reference_id, idempotency_key=key,
                metadata={"released": release}, wallet=w,
            )
            return CreditResult(ok=True, wallet=Wallet(**w.__dict__), entry=e, transaction_id=e.transaction_id)

    def capture_reservation(
        self, tenant_id: str, amount: int, *, type_: str = "generation_cost",
        reference_id: str = "", idempotency_key: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> CreditResult:
        err = validate_amount(amount)
        if err:
            return CreditResult(ok=False, reason=err)
        key = idempotency_key or f"capture:{tenant_id}:{uuid.uuid4().hex}"
        err = validate_idempotency_key(key)
        if err:
            return CreditResult(ok=False, reason=err)
        with self._lock:
            hit = self._replay(key, tenant_id)
            if hit:
                return hit
            w = self.ensure_wallet(tenant_id)
            if w.reserved_balance < amount:
                return CreditResult(
                    ok=False, reason=f"insufficient_reserved:{w.reserved_balance}",
                    wallet=Wallet(**w.__dict__),
                )
            if w.current_balance < amount:
                return CreditResult(
                    ok=False, reason=f"insufficient_balance:{w.current_balance}",
                    wallet=Wallet(**w.__dict__),
                )
            wa = user_wallet_account(tenant_id)
            # Release hold + recognize revenue
            legs = [
                LedgerLeg(SYSTEM_HOLDS, "debit", int(amount)),
                LedgerLeg(f"hold:{tenant_id}", "credit", int(amount)),
                LedgerLeg(wa, "debit", int(amount)),
                LedgerLeg(SYSTEM_REVENUE, "credit", int(amount)),
            ]
            w.reserved_balance -= int(amount)
            w.current_balance -= int(amount)
            w.updated_at = time.time()
            meta = dict(metadata or {})
            meta["captured"] = int(amount)
            e = self._commit(
                tenant_id=tenant_id, type_=type_, legs=legs,
                reference_id=reference_id, idempotency_key=key,
                metadata=meta, wallet=w,
            )
            return CreditResult(ok=True, wallet=Wallet(**w.__dict__), entry=e, transaction_id=e.transaction_id)


    def _expire_promotional_unlocked(self, w: Wallet, tenant_id: str) -> Optional[LedgerEntry]:
        """If promo expired, burn remaining promotional_balance (already under lock)."""
        if int(w.promotional_balance) <= 0:
            return None
        exp = float(w.promo_expires_at or 0)
        if exp <= 0 or time.time() < exp:
            return None
        amount = int(w.promotional_balance)
        if amount > int(w.current_balance):
            amount = int(w.current_balance)
        if amount <= 0:
            w.promotional_balance = 0
            w.promo_expires_at = 0.0
            return None
        wa = user_wallet_account(tenant_id)
        legs = [
            LedgerLeg(wa, "debit", amount),
            LedgerLeg(SYSTEM_REVENUE, "credit", amount),
        ]
        w.current_balance -= amount
        w.promotional_balance = 0
        w.promo_expires_at = 0.0
        w.updated_at = time.time()
        key = f"promo-expire-{tenant_id}-{int(exp)}"
        if key in self._idem:
            return self._idem[key]
        return self._commit(
            tenant_id=tenant_id, type_="promo_expired", legs=legs,
            reference_id=f"promo_expire:{tenant_id}", idempotency_key=key,
            metadata={"is_promotional": True, "expired_amount": amount}, wallet=w,
        )

    def expire_promotional(self, tenant_id: str) -> CreditResult:
        with self._lock:
            w = self.ensure_wallet(tenant_id)
            e = self._expire_promotional_unlocked(w, tenant_id)
            if e is None:
                return CreditResult(ok=True, reason="nothing_to_expire", wallet=Wallet(**w.__dict__))
            return CreditResult(ok=True, reason="promo_expired", wallet=Wallet(**w.__dict__),
                                entry=e, transaction_id=e.transaction_id)

    def reconcile(self, tenant_id: str) -> ReconcileReport:
        with self._lock:
            w = self.ensure_wallet(tenant_id)
            wa = user_wallet_account(tenant_id)
            net = 0
            unbalanced = 0
            for e in self._entries:
                deb = sum(x.amount for x in e.legs if x.side == "debit")
                cre = sum(x.amount for x in e.legs if x.side == "credit")
                if deb != cre:
                    unbalanced += 1
                if e.tenant_id != str(tenant_id):
                    continue
                for leg in e.legs:
                    if leg.account_id == wa:
                        net += leg.amount if leg.side == "credit" else -leg.amount
            return ReconcileReport(
                ok=(net == w.current_balance and unbalanced == 0),
                tenant_id=str(tenant_id),
                wallet_balance=w.current_balance,
                ledger_wallet_net=net,
                wallet_reserved=w.reserved_balance,
                unbalanced_transactions=unbalanced,
                drift_balance=w.current_balance - net,
            )

    def list_ledger(self, tenant_id: str, *, limit: int = 100) -> list[LedgerEntry]:
        with self._lock:
            rows = [e for e in self._entries if e.tenant_id == str(tenant_id)]
            return list(reversed(rows[-limit:]))

    def get_pricing(self, resource_type: str) -> Optional[PricingRule]:
        r = self._pricing.get(resource_type)
        return r if r and r.is_active else None

    def list_pricing(self) -> list[PricingRule]:
        return [r for r in self._pricing.values() if r.is_active]
