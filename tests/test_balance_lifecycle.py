'''Hardened phase-4 lifecycle state machine tests.'''
from __future__ import annotations

import time

from b2b_platform.balance_lifecycle import (
    BalanceLifecycle,
    MemoryLifecycleStore,
)
from b2b_platform.credits.memory_store import MemoryCreditsStore
from b2b_platform.credits.service import CreditService


def _lc():
    credits = CreditService(MemoryCreditsStore())
    store = MemoryLifecycleStore()
    return credits, store, BalanceLifecycle(store, credits)


def test_threshold_alert():
    credits, store, lc = _lc()
    credits.credit_credits("t1", 100, idempotency_key="fund-t1-001")
    lc.set_baseline("t1", 100)
    credits.deduct_credits("t1", 85, idempotency_key="deduct-t1-001")
    act = lc.on_balance_changed("t1")
    assert act.action == "alert"
    assert store.get("t1").phase == "warning"
    assert store.get("t1").last_alert_pct >= 80


def test_grace_then_suspend(monkeypatch):
    credits, store, lc = _lc()
    credits.credit_credits("t2", 10, idempotency_key="fund-t2-001")
    credits.deduct_credits("t2", 10, idempotency_key="deduct-t2-001")
    act = lc.on_balance_changed("t2")
    assert act.action == "enter_grace"
    assert store.get("t2").phase == "grace"
    assert lc.on_balance_changed("t2").action == "in_grace"
    monkeypatch.setattr(
        "b2b_platform.balance_lifecycle._snapshot_and_stop",
        lambda tid: {"ok": True, "stopped": 2, "bots": [{"bot_id": "b1"}]},
    )
    st = store.get("t2")
    st.grace_until = time.time() - 1
    store.save(st)
    act3 = lc.on_balance_changed("t2")
    assert act3.action == "suspend"
    st2 = store.get("t2")
    assert st2.suspended and st2.phase == "suspended"
    assert st2.snapshot.get("bots")


def test_hosting_gate():
    credits, store, lc = _lc()
    credits.credit_credits("t3", 50, idempotency_key="fund-t3-001")
    ok, reason = lc.is_hosting_allowed("t3")
    assert ok and reason == "ok"


def test_suspend_blocks_host(monkeypatch):
    credits, store, lc = _lc()
    monkeypatch.setattr(
        "b2b_platform.balance_lifecycle._snapshot_and_stop",
        lambda tid: {"ok": True, "stopped": 0, "bots": []},
    )
    lc.suspend("t4", reason="test")
    ok, reason = lc.is_hosting_allowed("t4")
    assert not ok and reason == "suspended_due_to_balance"


def test_status_payload():
    credits, store, lc = _lc()
    credits.credit_credits("t5", 40, idempotency_key="fund-t5-001")
    st = lc.status("t5")
    assert st["available"] == 40
    assert "phase" in st


def test_clear_requires_balance(monkeypatch):
    credits, store, lc = _lc()
    monkeypatch.setattr(
        "b2b_platform.balance_lifecycle._snapshot_and_stop",
        lambda tid: {"ok": True, "stopped": 0, "bots": []},
    )
    lc.suspend("t6", reason="x")
    assert lc.clear_suspension_on_credit("t6").action == "still_empty"
    credits.credit_credits("t6", 20, idempotency_key="fund-t6-001")
    assert lc.clear_suspension_on_credit("t6").action == "unsuspended"
