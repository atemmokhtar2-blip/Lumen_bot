"""Hardened phase-1 credits tests."""
from __future__ import annotations

import concurrent.futures

import pytest

from b2b_platform.credits.memory_store import MemoryCreditsStore
from b2b_platform.credits.service import CreditService


@pytest.fixture
def svc() -> CreditService:
    return CreditService(MemoryCreditsStore())


def test_credit_and_deduct(svc: CreditService):
    r = svc.credit_credits("t1", 100, reason="purchase", idempotency_key="p1")
    assert r.ok and r.wallet and r.wallet.current_balance == 100
    d = svc.deduct_credits("t1", 30, reason="generation_cost", reference_id="job1", idempotency_key="d1")
    assert d.ok and d.wallet and d.wallet.current_balance == 70
    assert d.entry and d.entry.amount == -30 and d.entry.balance_after == 70
    rep = svc.reconcile("t1")
    assert rep.ok and rep.drift_balance == 0


def test_insufficient_balance(svc: CreditService):
    svc.credit_credits("t2", 10, idempotency_key="c2")
    d = svc.deduct_credits("t2", 50, idempotency_key="d2")
    assert not d.ok
    assert "insufficient_balance" in d.reason


def test_idempotent_deduct(svc: CreditService):
    svc.credit_credits("t3", 100, idempotency_key="c3")
    a = svc.deduct_credits("t3", 20, idempotency_key="same-key")
    b = svc.deduct_credits("t3", 20, idempotency_key="same-key")
    assert a.ok and b.ok
    assert b.reason == "idempotent_replay"
    assert a.transaction_id == b.transaction_id
    assert svc.get_wallet("t3").current_balance == 80
    assert svc.reconcile("t3").ok


def test_reserve_blocks_available(svc: CreditService):
    svc.credit_credits("t4", 100, idempotency_key="c4")
    r = svc.reserve_credits("t4", 60, idempotency_key="r4")
    assert r.ok and r.entry and r.entry.reservation_delta == 60
    w = svc.get_wallet("t4")
    assert w.reserved_balance == 60 and w.available == 40
    assert not svc.deduct_credits("t4", 50, idempotency_key="d4").ok
    assert svc.deduct_credits("t4", 40, idempotency_key="d4b").ok
    svc.release_reservation("t4", 60, idempotency_key="rel4")
    assert svc.get_wallet("t4").reserved_balance == 0
    assert svc.reconcile("t4").ok


def test_capture_reservation(svc: CreditService):
    svc.credit_credits("t7", 100, idempotency_key="c7")
    assert svc.reserve_credits("t7", 40, idempotency_key="r7").ok
    cap = svc.capture_reservation("t7", 40, reason="hourly_hosting", idempotency_key="cap7")
    assert cap.ok
    w = svc.get_wallet("t7")
    assert w.current_balance == 60
    assert w.reserved_balance == 0
    assert cap.entry and cap.entry.amount == -40 and cap.entry.reservation_delta == -40
    assert svc.reconcile("t7").ok


def test_capture_without_reserve_fails(svc: CreditService):
    svc.credit_credits("t8", 50, idempotency_key="c8")
    cap = svc.capture_reservation("t8", 10, idempotency_key="cap8")
    assert not cap.ok
    assert "insufficient_reserved" in cap.reason


def test_parallel_deduct_never_negative(svc: CreditService):
    svc.credit_credits("t5", 100, idempotency_key="c5")

    def once(i: int):
        return svc.deduct_credits("t5", 10, idempotency_key=f"par-{i}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        results = list(ex.map(once, range(20)))
    ok = sum(1 for r in results if r.ok and r.reason != "idempotent_replay")
    assert ok == 10
    assert svc.get_wallet("t5").current_balance == 0
    assert svc.reconcile("t5").ok


def test_ledger_and_pricing(svc: CreditService):
    svc.credit_credits("t6", 50, idempotency_key="c6")
    svc.deduct_credits("t6", 5, reason="telegram_message", idempotency_key="d6")
    rows = svc.list_ledger("t6")
    assert len(rows) >= 2
    assert svc.cost_for("generation_cost", 2) == 100
    assert svc.reconcile("t6").ok
