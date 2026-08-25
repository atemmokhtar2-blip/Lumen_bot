"""Phase 4 balance lifecycle tests."""
from __future__ import annotations

import time

from b2b_platform.balance_lifecycle import (
    BalanceLifecycle,
    MemoryLifecycleStore,
)
from b2b_platform.credits.memory_store import MemoryCreditsStore
from b2b_platform.credits.service import CreditService


def test_threshold_alert():
    credits = CreditService(MemoryCreditsStore())
    lc = BalanceLifecycle(MemoryLifecycleStore(), credits)
    credits.credit_credits("t1", 100, idempotency_key="fund-t1-001")
    lc.set_baseline("t1", 100)
    credits.deduct_credits("t1", 85, idempotency_key="deduct-t1-001")
    act = lc.on_balance_changed("t1")
    assert act.action == "alert"
    assert act.state and act.state.last_alert_pct >= 80


def test_grace_then_suspend(monkeypatch):
    credits = CreditService(MemoryCreditsStore())
    store = MemoryLifecycleStore()
    lc = BalanceLifecycle(store, credits)
    credits.credit_credits("t2", 10, idempotency_key="fund-t2-001")
    credits.deduct_credits("t2", 10, idempotency_key="deduct-t2-001")
    act = lc.on_balance_changed("t2")
    assert act.action == "enter_grace"
    state = store.get("t2")
    assert state.grace_until > time.time()
    state.grace_until = time.time() - 1
    store.save(state)
    monkeypatch.setattr(
        "b2b_platform.balance_lifecycle._suspend_tenant_bots",
        lambda tid: {"ok": True, "stopped": 0},
    )
    act2 = lc.on_balance_changed("t2")
    assert act2.action == "suspend"
    assert store.get("t2").suspended


def test_hosting_blocked_when_suspended(monkeypatch):
    credits = CreditService(MemoryCreditsStore())
    store = MemoryLifecycleStore()
    lc = BalanceLifecycle(store, credits)
    monkeypatch.setattr(
        "b2b_platform.balance_lifecycle._suspend_tenant_bots",
        lambda tid: {"ok": True, "stopped": 0},
    )
    lc.suspend("t3", reason="test")
    ok, reason = lc.is_hosting_allowed("t3")
    assert not ok and reason == "suspended_due_to_balance"


def test_topup_clears_suspension(monkeypatch):
    credits = CreditService(MemoryCreditsStore())
    store = MemoryLifecycleStore()
    lc = BalanceLifecycle(store, credits)
    monkeypatch.setattr(
        "b2b_platform.balance_lifecycle._suspend_tenant_bots",
        lambda tid: {"ok": True, "stopped": 0},
    )
    lc.suspend("t4", reason="test")
    act = lc.clear_suspension_on_credit("t4")
    assert act.action == "unsuspended"
    assert not store.get("t4").suspended


def test_rating_failure_enters_grace():
    credits = CreditService(MemoryCreditsStore())
    lc = BalanceLifecycle(MemoryLifecycleStore(), credits)
    act = lc.on_rating_failure("t5", "insufficient_balance:0")
    assert act.action == "enter_grace"
