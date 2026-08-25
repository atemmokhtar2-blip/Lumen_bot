"""Welcome / trial credits — exact Aha! Moment math + promo rules."""
from __future__ import annotations

import time

import pytest

from b2b_platform.credits.memory_store import MemoryCreditsStore
from b2b_platform.credits.onboarding import (
    INITIAL_CREDITS_COMPUTED,
    TRIAL_GENERATIONS,
    TRIAL_HOST_HOURS,
    TRIAL_MESSAGE_BUFFER,
    UNIT_GENERATION_COST,
    UNIT_HOURLY_HOSTING,
    UNIT_TELEGRAM_MESSAGE,
    grant_welcome_credits,
    welcome_plan,
)
from b2b_platform.credits.service import CreditService


def test_aha_moment_math_exact():
    """Must match seeded pricing: 50*3 + 10*24 + 1*10 = 400."""
    assert UNIT_GENERATION_COST == 50
    assert UNIT_HOURLY_HOSTING == 10
    assert UNIT_TELEGRAM_MESSAGE == 1
    assert TRIAL_GENERATIONS == 3
    assert TRIAL_HOST_HOURS == 24
    assert TRIAL_MESSAGE_BUFFER == 10
    expected = 50 * 3 + 10 * 24 + 1 * 10
    assert expected == 400
    assert INITIAL_CREDITS_COMPUTED == expected
    plan = welcome_plan()
    assert plan.amount == 400
    assert plan.ttl_days == 14
    assert plan.enabled is True
    assert plan.computed_breakdown["computed_total"] == 400


def test_welcome_grant_idempotent():
    svc = CreditService(MemoryCreditsStore())
    a = grant_welcome_credits("tenant-welcome-1", credit_service=svc)
    assert a["ok"] is True
    assert a["amount"] == 400
    assert a["promotional_balance"] == 400
    assert a["wallet_balance"] == 400
    assert a["promo_expires_at"] > time.time()
    # second call same idempotency key → replay, balance stays 400
    b = grant_welcome_credits("tenant-welcome-1", credit_service=svc)
    assert b["ok"] is True
    assert svc.get_wallet("tenant-welcome-1").current_balance == 400
    assert svc.reconcile("tenant-welcome-1").ok


def test_deduct_promotional_first():
    svc = CreditService(MemoryCreditsStore())
    grant_welcome_credits("tenant-promo-2", credit_service=svc)
    # paid top-up
    assert svc.credit_credits(
        "tenant-promo-2", 100, reason="purchase", idempotency_key="paid-topup-0001"
    ).ok
    w = svc.get_wallet("tenant-promo-2")
    assert w.current_balance == 500
    assert w.promotional_balance == 400
    assert w.paid_balance == 100
    # spend 50 → should come from promo first
    d = svc.deduct_credits("tenant-promo-2", 50, idempotency_key="spend-promo-0001")
    assert d.ok
    w2 = svc.get_wallet("tenant-promo-2")
    assert w2.current_balance == 450
    assert w2.promotional_balance == 350
    assert w2.paid_balance == 100
    assert svc.reconcile("tenant-promo-2").ok


def test_promo_expiration_burns_remaining():
    svc = CreditService(MemoryCreditsStore())
    # grant with already-expired promo
    r = svc.credit_credits(
        "tenant-exp-3",
        200,
        reason="welcome_grant",
        idempotency_key="welcome-expired-0001",
        promotional=True,
        promo_expires_at=time.time() - 10,
        metadata={"is_promotional": True},
    )
    assert r.ok
    assert svc.get_wallet("tenant-exp-3").promotional_balance == 200
    exp = svc.expire_promotional("tenant-exp-3")
    assert exp.ok
    assert exp.reason == "promo_expired"
    w = svc.get_wallet("tenant-exp-3")
    assert w.current_balance == 0
    assert w.promotional_balance == 0
    assert svc.reconcile("tenant-exp-3").ok


def test_deduct_auto_expires_before_spend():
    svc = CreditService(MemoryCreditsStore())
    svc.credit_credits(
        "tenant-exp-4",
        100,
        reason="welcome_grant",
        idempotency_key="welcome-expired-0002",
        promotional=True,
        promo_expires_at=time.time() - 5,
    )
    # paid credits remain after auto-expire on deduct attempt
    svc.credit_credits(
        "tenant-exp-4", 30, reason="purchase", idempotency_key="paid-keep-0001"
    )
    # available should drop expired promo on deduct path
    d = svc.deduct_credits("tenant-exp-4", 20, idempotency_key="after-expire-0001")
    assert d.ok
    w = svc.get_wallet("tenant-exp-4")
    assert w.current_balance == 10  # 30 paid - 20; 100 promo burned
    assert w.promotional_balance == 0


def test_welcome_disabled_env(monkeypatch):
    monkeypatch.setenv("INITIAL_CREDITS_ENABLED", "0")
    plan = welcome_plan()
    assert plan.enabled is False
    svc = CreditService(MemoryCreditsStore())
    r = grant_welcome_credits("tenant-off", credit_service=svc)
    assert r["ok"] is False
    assert r["reason"] == "welcome_disabled"
    assert svc.get_wallet("tenant-off").current_balance == 0


def test_three_generations_fit_in_trial():
    """400 credits must cover 3 generations at 50 each (+ host buffer)."""
    svc = CreditService(MemoryCreditsStore())
    grant_welcome_credits("tenant-gens", credit_service=svc)
    for i in range(3):
        r = svc.deduct_credits(
            "tenant-gens",
            UNIT_GENERATION_COST,
            reason="generation_cost",
            idempotency_key=f"gen-trial-{i:04d}",
        )
        assert r.ok, r.reason
    w = svc.get_wallet("tenant-gens")
    assert w.current_balance == 400 - 150  # 250 left for hosting/messages
    assert w.promotional_balance == 250
