"""Welcome / trial credits — calculated from seeded pricing, not guessed.

Aha! Moment budget (from CreditService pricing seed):
  generation_cost      = 50 credits / bot generation
  hourly_hosting       = 10 credits / hour
  telegram_message     = 1  credit  / message

Smart-trial target (Freemium growth model):
  3 generations  → 50 * 3  = 150
  24h hosting    → 10 * 24 = 240
  message buffer → 1  * 10 =  10
  ─────────────────────────────────
  INITIAL_CREDITS_COMPUTED = 400

Env overrides:
  INITIAL_CREDITS          (default 400)
  INITIAL_CREDITS_TTL_DAYS (default 14)
  INITIAL_CREDITS_ENABLED  (default 1)
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

# Exact unit costs from seeded pricing (memory_store / pg_store)
UNIT_GENERATION_COST = 50
UNIT_HOURLY_HOSTING = 10
UNIT_TELEGRAM_MESSAGE = 1

TRIAL_GENERATIONS = 3
TRIAL_HOST_HOURS = 24
TRIAL_MESSAGE_BUFFER = 10

INITIAL_CREDITS_COMPUTED = (
    UNIT_GENERATION_COST * TRIAL_GENERATIONS
    + UNIT_HOURLY_HOSTING * TRIAL_HOST_HOURS
    + UNIT_TELEGRAM_MESSAGE * TRIAL_MESSAGE_BUFFER
)  # 50*3 + 10*24 + 1*10 = 400


@dataclass(frozen=True)
class WelcomeGrantPlan:
    amount: int
    ttl_days: int
    enabled: bool
    computed_breakdown: dict[str, int]


def welcome_plan() -> WelcomeGrantPlan:
    enabled = (os.getenv("INITIAL_CREDITS_ENABLED") or "1").strip().lower() not in {
        "0", "false", "off", "no",
    }
    try:
        amount = int(os.getenv("INITIAL_CREDITS") or str(INITIAL_CREDITS_COMPUTED))
    except ValueError:
        amount = INITIAL_CREDITS_COMPUTED
    amount = max(0, amount)
    try:
        ttl = int(os.getenv("INITIAL_CREDITS_TTL_DAYS") or "14")
    except ValueError:
        ttl = 14
    ttl = max(0, ttl)
    return WelcomeGrantPlan(
        amount=amount,
        ttl_days=ttl,
        enabled=enabled and amount > 0,
        computed_breakdown={
            "generation_cost_unit": UNIT_GENERATION_COST,
            "hourly_hosting_unit": UNIT_HOURLY_HOSTING,
            "telegram_message_unit": UNIT_TELEGRAM_MESSAGE,
            "trial_generations": TRIAL_GENERATIONS,
            "trial_host_hours": TRIAL_HOST_HOURS,
            "trial_message_buffer": TRIAL_MESSAGE_BUFFER,
            "computed_total": INITIAL_CREDITS_COMPUTED,
            "configured_amount": amount,
        },
    )


def grant_welcome_credits(tenant_id: str, *, credit_service: Any = None) -> dict[str, Any]:
    """Idempotent promotional grant for a new tenant/user.

    Ledger reason: welcome_grant, metadata is_promotional=true.
    """
    plan = welcome_plan()
    if not plan.enabled:
        return {
            "ok": False,
            "reason": "welcome_disabled",
            "amount": 0,
            "breakdown": plan.computed_breakdown,
        }

    if credit_service is None:
        from b2b_platform.credits import get_credit_service

        credit_service = get_credit_service()

    tid = str(tenant_id)
    expires_at = 0.0
    if plan.ttl_days > 0:
        expires_at = time.time() + plan.ttl_days * 86400.0

    idem = f"welcome-grant-{tid}"
    result = credit_service.credit_credits(
        tid,
        plan.amount,
        reason="welcome_grant",
        reference_id=f"welcome:{tid}",
        idempotency_key=idem,
        metadata={
            "is_promotional": True,
            "promo_expires_at": expires_at,
            "ttl_days": plan.ttl_days,
            "breakdown": plan.computed_breakdown,
            "non_withdrawable": True,
        },
        promotional=True,
        promo_expires_at=expires_at,
    )
    return {
        "ok": bool(result.ok),
        "reason": getattr(result, "reason", "") or "",
        "amount": plan.amount,
        "ttl_days": plan.ttl_days,
        "promo_expires_at": expires_at,
        "wallet_balance": int(
            getattr(getattr(result, "wallet", None), "current_balance", 0) or 0
        ),
        "promotional_balance": int(
            getattr(getattr(result, "wallet", None), "promotional_balance", 0) or 0
        ),
        "breakdown": plan.computed_breakdown,
        "transaction_id": getattr(result, "transaction_id", "") or "",
    }
