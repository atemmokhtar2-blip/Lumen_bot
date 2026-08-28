"""Gather live platform facts for engine UI render (real I/O)."""
from __future__ import annotations

import logging
from typing import Any

from lumen.engine.services.ui_state.render import HostRow, UiFacts

logger = logging.getLogger("lumen_bot.ui")


def gather_ui_facts(user_id: int, user_data: dict[str, Any] | None) -> UiFacts:
    facts = UiFacts(user_id=int(user_id or 0))
    ud = user_data if isinstance(user_data, dict) else {}

    # Active project from session (same keys hosting router uses)
    active = ud.get("active_repo") if isinstance(ud.get("active_repo"), dict) else {}
    path = (active.get("path") or ud.get("last_project_path") or "").strip()
    if path:
        facts.active_project = path

    # Credits-first (primary economy surface)
    try:
        from lumen.platform.credits import get_credit_service
        from lumen.platform.credits.onboarding import (
            UNIT_GENERATION_COST,
            UNIT_HOURLY_HOSTING,
            grant_welcome_credits,
        )

        tid = f"tg:{int(user_id)}"
        # Ensure welcome pack exists (idempotent)
        try:
            grant_welcome_credits(tid)
        except Exception:
            logger.debug("welcome grant skipped", exc_info=True)
        wallet = get_credit_service().get_wallet(tid)
        facts.credits_balance = int(getattr(wallet, "current_balance", 0) or 0)
        facts.credits_reserved = int(getattr(wallet, "reserved_balance", 0) or 0)
        avail = getattr(wallet, "available", None)
        if avail is None:
            avail = facts.credits_balance - facts.credits_reserved
        facts.credits_available = max(0, int(avail or 0))
        facts.gen_cost_credits = int(UNIT_GENERATION_COST)
        facts.host_hourly_credits = int(UNIT_HOURLY_HOSTING)
    except Exception:
        logger.debug("credits facts unavailable", exc_info=True)

    # Plan label kept as secondary metadata only
    try:
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
    except Exception:
        logger.debug("mongo plan unavailable", exc_info=True)

    # Hosting instances (real HostService)
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
