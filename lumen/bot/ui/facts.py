"""Gather live platform facts for engine UI render (real I/O).

Performance rules (hot path — every button press):
  - Never grant welcome credits more than once per process per tenant
  - Cache wallet/plan briefly (in-process TTL) to avoid Neon/Mongo RTT every click
  - Hosting list only when dashboard phase needs it
  - All network I/O is sync; callers MUST run this via asyncio.to_thread
"""
from __future__ import annotations

import logging
import time
from typing import Any

from lumen.engine.services.ui_state.render import HostRow, UiFacts

logger = logging.getLogger("lumen_bot.ui")

_WALLET_CACHE: dict[str, tuple[float, int, int, int]] = {}
_PLAN_CACHE: dict[int, tuple[float, str, str]] = {}
_WELCOME_DONE: set[str] = set()
_CACHE_TTL = 45.0


def gather_ui_facts(
    user_id: int,
    user_data: dict[str, Any] | None,
    *,
    include_hosts: bool = False,
) -> UiFacts:
    facts = UiFacts(user_id=int(user_id or 0))
    ud = user_data if isinstance(user_data, dict) else {}
    now = time.monotonic()

    active = ud.get("active_repo") if isinstance(ud.get("active_repo"), dict) else {}
    path = (active.get("path") or ud.get("last_project_path") or "").strip()
    if path:
        facts.active_project = path

    try:
        from lumen.platform.credits.onboarding import (
            UNIT_GENERATION_COST,
            UNIT_HOURLY_HOSTING,
            grant_welcome_credits,
        )
        from lumen.platform.credits import get_credit_service

        tid = f"tg:{int(user_id)}"
        facts.gen_cost_credits = int(UNIT_GENERATION_COST)
        facts.host_hourly_credits = int(UNIT_HOURLY_HOSTING)

        if tid not in _WELCOME_DONE and not ud.get("_welcome_credits_ok"):
            try:
                grant_welcome_credits(tid)
                _WELCOME_DONE.add(tid)
                ud["_welcome_credits_ok"] = True
            except Exception:
                logger.debug("welcome grant skipped", exc_info=True)

        cached = _WALLET_CACHE.get(tid)
        if cached and cached[0] > now:
            facts.credits_balance = cached[1]
            facts.credits_reserved = cached[2]
            facts.credits_available = cached[3]
        else:
            wallet = get_credit_service().get_wallet(tid)
            bal = int(getattr(wallet, "current_balance", 0) or 0)
            reserved = int(getattr(wallet, "reserved_balance", 0) or 0)
            avail = getattr(wallet, "available", None)
            if avail is None:
                avail = bal - reserved
            avail_i = max(0, int(avail or 0))
            facts.credits_balance = bal
            facts.credits_reserved = reserved
            facts.credits_available = avail_i
            _WALLET_CACHE[tid] = (now + _CACHE_TTL, bal, reserved, avail_i)
    except Exception:
        logger.debug("credits facts unavailable", exc_info=True)

    try:
        cached_p = _PLAN_CACHE.get(int(user_id))
        if cached_p and cached_p[0] > now:
            facts.plan_id = cached_p[1]
            facts.plan_label = cached_p[2]
        else:
            from lumen.bot.middlewares.mongo_sync import mongo_plan_for_user

            plan = mongo_plan_for_user(int(user_id)) or "free"
            facts.plan_id = str(plan)
            labels = {
                "free": "Free",
                "explorer": "Free",
                "starter": "Starter",
                "growth": "Growth",
                "pro": "Growth",
                "unlimited": "Growth",
            }
            facts.plan_label = labels.get(str(plan), str(plan))
            _PLAN_CACHE[int(user_id)] = (now + _CACHE_TTL, facts.plan_id, facts.plan_label)
    except Exception:
        logger.debug("mongo plan unavailable", exc_info=True)

    if include_hosts:
        try:
            from lumen.bot.config import OUTPUT_DIR
            from lumen.engine.services.hosting import get_hosting_service

            svc = get_hosting_service(OUTPUT_DIR)
            for inst in svc.list_for_user(int(user_id)):
                facts.hosts.append(
                    HostRow(
                        instance_id=str(getattr(inst, "instance_id", "") or ""),
                        status=str(getattr(inst, "status", "") or ""),
                        bot_username=str(getattr(inst, "bot_username", "") or ""),
                        backend=str(getattr(inst, "sandbox_backend", "") or ""),
                    )
                )
        except Exception:
            logger.debug("hosting list unavailable", exc_info=True)

    return facts


def invalidate_facts_cache(user_id: int | None = None) -> None:
    """Force next gather_ui_facts to hit live wallet/plan stores."""
    if user_id is None:
        _WALLET_CACHE.clear()
        _PLAN_CACHE.clear()
        return
    tid = f"tg:{int(user_id)}"
    _WALLET_CACHE.pop(tid, None)
    _PLAN_CACHE.pop(int(user_id), None)
