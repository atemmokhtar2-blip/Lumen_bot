"""Lumen Pro entitlement resolver — secure, server-side, tamper-resistant.

This is the SINGLE source of truth for "does this user have active Pro, and what
are their limits?"  It reads the persisted subscription from the durable session
store (Redis in production) — never from client-supplied data alone.

Security properties:
  - Source of truth is server-side Redis (SessionStore), not client user_data.
  - Expiry is checked server-side (expires_at < now → not active).
  - Currency / payload / amount are verified at payment time (payment_handlers).
  - Entitlement is re-evaluated on every enforcement check (no stale cache).
  - If Redis is unavailable, entitlement defaults to None (fail-closed for
    limits that *increase* capacity; fail-open for base access so the bot still
    works for free users).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from lumen.engine.services.ui_state.pro_plan import (
    PRO_PLAN_ID,
    PRO_PLAN_BOT_LIMIT,
    PRO_PLAN_PRICE_STARS,
)

logger = logging.getLogger("lumen_bot.entitlement")


@dataclass(frozen=True)
class ProEntitlement:
    """Active Pro entitlement for a user, or None if not active."""

    plan_id: str
    started_at: str  # ISO 8601 UTC
    expires_at: str  # ISO 8601 UTC
    stars_paid: int
    charge_id: str

    @property
    def is_expired(self) -> bool:
        try:
            exp = datetime.fromisoformat(self.expires_at)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) >= exp
        except Exception:
            logger.warning("pro entitlement bad expires_at=%s", self.expires_at)
            return True  # fail-closed: treat unparseable expiry as expired

    @property
    def days_remaining(self) -> int:
        try:
            exp = datetime.fromisoformat(self.expires_at)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            delta = exp - datetime.now(timezone.utc)
            return max(0, int(delta.total_seconds() // 86400))
        except Exception:
            return 0


def _load_pro_record(user_id: int) -> dict[str, Any] | None:
    """Load the pro_plan record from the durable subscription store.

    Reads from Redis first (fast path), then falls back to MongoDB (permanent
    source of truth) if Redis has no record (flush / TTL expiry / drop_user_data).
    On MongoDB fallback, Redis is self-healed (re-populated).

    We do NOT trust caller-supplied user_data because a client cannot forge a
    MongoDB or Redis write.  If both stores are down we return None
    (fail-closed: no Pro benefits, but base bot access still works).
    """
    if not user_id:
        return None
    try:
        from lumen.bot.ui.subscription_store import read_subscription
        rec = read_subscription(int(user_id))
        return rec if isinstance(rec, dict) else None
    except Exception:
        logger.debug("pro entitlement load failed uid=%s", user_id, exc_info=True)
        return None


def resolve_pro_entitlement(user_id: int) -> ProEntitlement | None:
    """Return the active ProEntitlement for user_id, or None if not Pro.

    Checks:
      1. Record exists in durable store (Redis).
      2. plan_id == PRO_PLAN_ID.
      3. stars_paid == PRO_PLAN_PRICE_STARS (2000).
      4. Not expired (expires_at > now).
    """
    rec = _load_pro_record(user_id)
    if not rec:
        return None

    plan_id = str(rec.get("plan_id") or "")
    if plan_id != PRO_PLAN_ID:
        logger.warning("pro entitlement plan_id mismatch uid=%s plan_id=%s", user_id, plan_id)
        return None

    stars_paid = int(rec.get("stars_paid") or 0)
    if stars_paid < PRO_PLAN_PRICE_STARS:
        logger.warning("pro entitlement underpaid uid=%s paid=%s expected=%s", user_id, stars_paid, PRO_PLAN_PRICE_STARS)
        return None

    entitlement = ProEntitlement(
        plan_id=plan_id,
        started_at=str(rec.get("started_at") or ""),
        expires_at=str(rec.get("expires_at") or ""),
        stars_paid=stars_paid,
        charge_id=str(rec.get("charge_id") or ""),
    )

    if entitlement.is_expired:
        logger.info("pro entitlement expired uid=%s expires_at=%s", user_id, entitlement.expires_at)
        return None

    return entitlement


# ── Limit resolvers — these are what enforcement code calls ──────────────────


@dataclass(frozen=True)
class PlanLimits:
    """Concrete limits for a user based on their entitlement."""

    max_bots: int
    disk_mb: int
    memory_mb: int
    cpu: float
    is_pro: bool
    days_remaining: int  # 0 if not pro


def resolve_plan_limits(user_id: int) -> PlanLimits:
    """Resolve concrete resource limits for a user.

    Pro users get the Pro plan limits.  Non-Pro / expired users get the platform
    defaults (read from env so ops can tune without code changes).
    """
    import os

    ent = resolve_pro_entitlement(user_id)
    if ent is not None:
        return PlanLimits(
            max_bots=PRO_PLAN_BOT_LIMIT,  # 3
            disk_mb=2048,  # 2 GB
            memory_mb=512,  # 512 MB
            cpu=0.5,  # 0.5 core
            is_pro=True,
            days_remaining=ent.days_remaining,
        )

    # Defaults (non-Pro) — read from env so they remain ops-tunable.
    try:
        _max_bots = int(os.environ.get("TBE_MAX_BOTS_PER_USER") or "50")
    except ValueError:
        _max_bots = 50
    try:
        _disk_mb = int(os.environ.get("TBE_USER_DISK_MB") or "512")
    except ValueError:
        _disk_mb = 512
    try:
        _mem_mb = int(os.environ.get("TBE_BOT_MEMORY_MB") or os.environ.get("TBE_DOCKER_MEMORY") or "256")
    except ValueError:
        _mem_mb = 256
    try:
        _cpu = float(os.environ.get("TBE_BOT_CPU") or "0.5")
    except ValueError:
        _cpu = 0.5

    return PlanLimits(
        max_bots=max(1, _max_bots),
        disk_mb=max(64, _disk_mb),
        memory_mb=max(64, _mem_mb),
        cpu=max(0.1, _cpu),
        is_pro=False,
        days_remaining=0,
    )


__all__ = [
    "ProEntitlement",
    "PlanLimits",
    "resolve_pro_entitlement",
    "resolve_plan_limits",
]
