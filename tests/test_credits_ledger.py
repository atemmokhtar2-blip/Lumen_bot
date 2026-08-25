"""Phase 1 credits ledger tests — memory store (no Postgres required)."""
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


def test_reserve_blocks_available(svc: CreditService):
    svc.credit_credits("t4", 100, idempotency_key="c4")
    r = svc.reserve_credits("t4", 60, idempotency_key="r4")
    assert r.ok
    w = svc.get_wallet("t4")
    assert w.reserved_balance == 60
    assert w.available == 40
    d = svc.deduct_credits("t4", 50, idempotency_key="d4")
    assert not d.ok  # only 40 available
    d2 = svc.deduct_credits("t4", 40, idempotency_key="d4b")
    assert d2.ok
    svc.release_reservation("t4", 60, idempotency_key="rel4")
    assert svc.get_wallet("t4").reserved_balance == 0


def test_parallel_deduct_never_negative(svc: CreditService):
    svc.credit_credits("t5", 100, idempotency_key="c5")

    def once(i: int):
        return svc.deduct_credits("t5", 10, idempotency_key=f"par-{i}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        results = list(ex.map(once, range(20)))
    ok = sum(1 for r in results if r.ok and r.reason != "idempotent_replay")
    # 100 credits / 10 = 10 successes max
    assert ok == 10
    assert svc.get_wallet("t5").current_balance == 0
    assert svc.get_wallet("t5").current_balance >= 0


def test_ledger_lists_entries(svc: CreditService):
    svc.credit_credits("t6", 50, idempotency_key="c6")
    svc.deduct_credits("t6", 5, reason="telegram_message", idempotency_key="d6")
    rows = svc.list_ledger("t6")
    assert len(rows) >= 2
    assert rows[0].tenant_id == "t6"


def test_pricing_seed(svc: CreditService):
    rules = svc.list_pricing()
    assert any(r.resource_type == "generation_cost" for r in rules)
    assert svc.cost_for("generation_cost", 2) == 100
