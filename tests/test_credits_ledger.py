"""Double-entry credits — phase 1 hardened tests."""
from __future__ import annotations

import concurrent.futures
import pytest
from b2b_platform.credits.memory_store import MemoryCreditsStore
from b2b_platform.credits.service import CreditService


@pytest.fixture
def svc() -> CreditService:
    return CreditService(MemoryCreditsStore())


def test_credit_deduct_reconcile(svc: CreditService):
    assert svc.credit_credits("t1", 100, idempotency_key="purchase-t1-001").ok
    d = svc.deduct_credits("t1", 30, idempotency_key="deduct-t1-001")
    assert d.ok and d.wallet.current_balance == 70
    assert d.entry and len(d.entry.legs) == 2
    deb = sum(x.amount for x in d.entry.legs if x.side == "debit")
    cre = sum(x.amount for x in d.entry.legs if x.side == "credit")
    assert deb == cre == 30
    assert svc.reconcile("t1").ok


def test_insufficient(svc: CreditService):
    svc.credit_credits("t2", 10, idempotency_key="purchase-t2-001")
    r = svc.deduct_credits("t2", 50, idempotency_key="deduct-t2-001")
    assert not r.ok and "insufficient_balance" in r.reason


def test_idempotent(svc: CreditService):
    svc.credit_credits("t3", 100, idempotency_key="purchase-t3-001")
    a = svc.deduct_credits("t3", 20, idempotency_key="deduct-t3-same")
    b = svc.deduct_credits("t3", 20, idempotency_key="deduct-t3-same")
    assert a.ok and b.reason == "idempotent_replay"
    assert a.transaction_id == b.transaction_id
    assert svc.get_wallet("t3").current_balance == 80
    assert svc.reconcile("t3").ok


def test_short_idempotency_rejected(svc: CreditService):
    r = svc.credit_credits("t9", 10, idempotency_key="short")
    assert not r.ok and "idempotency_key" in r.reason


def test_reserve_capture(svc: CreditService):
    svc.credit_credits("t4", 100, idempotency_key="purchase-t4-001")
    assert svc.reserve_credits("t4", 40, idempotency_key="reserve-t4-001").ok
    assert svc.get_wallet("t4").available == 60
    assert not svc.deduct_credits("t4", 70, idempotency_key="deduct-t4-fail").ok
    cap = svc.capture_reservation("t4", 40, idempotency_key="capture-t4-001")
    assert cap.ok
    assert svc.get_wallet("t4").current_balance == 60
    assert svc.get_wallet("t4").reserved_balance == 0
    assert len(cap.entry.legs) == 4  # hold release + revenue
    assert svc.reconcile("t4").ok


def test_hash_chain(svc: CreditService):
    svc.credit_credits("t5", 50, idempotency_key="purchase-t5-001")
    svc.deduct_credits("t5", 5, idempotency_key="deduct-t5-001")
    rows = list(reversed(svc.list_ledger("t5")))
    assert rows[0].entry_hash
    assert rows[1].prev_hash == rows[0].entry_hash


def test_parallel_deduct(svc: CreditService):
    svc.credit_credits("t6", 100, idempotency_key="purchase-t6-001")
    def once(i: int):
        return svc.deduct_credits("t6", 10, idempotency_key=f"parallel-t6-{i:03d}")
    with concurrent.futures.ThreadPoolExecutor(20) as ex:
        results = list(ex.map(once, range(20)))
    assert sum(1 for r in results if r.ok and r.reason != "idempotent_replay") == 10
    assert svc.get_wallet("t6").current_balance == 0
    assert svc.reconcile("t6").ok


def test_amount_cap(svc: CreditService):
    r = svc.credit_credits("t7", 10**15, idempotency_key="purchase-t7-huge")
    assert not r.ok and "exceeds" in r.reason
