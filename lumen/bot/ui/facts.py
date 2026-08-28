"""Gather live platform facts for engine UI render (real I/O)."""
from __future__ import annotations

import logging
from pathlib import Path
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

    # Plan from Mongo (same path as /plan)
    try:
        from lumen.bot.middlewares.mongo_sync import mongo_plan_for_user

        plan = mongo_plan_for_user(int(user_id)) or "free"
        facts.plan_id = str(plan)
        labels = {
            "free": "Free — مجاني",
            "explorer": "Free — مجاني",
            "starter": "المبادر (Starter)",
            "growth": "النمو (Growth)",
            "pro": "النمو (Growth)",
            "unlimited": "النمو (Growth)",
        }
        facts.plan_label = labels.get(str(plan), str(plan))
        try:
            from lumen.platform.plans import get_plan, public_plan_dict

            pd = public_plan_dict(get_plan(plan))
            facts.generations_per_month = str(pd.get("generations_per_month", ""))
            facts.hosted_bots_limit = str(pd.get("hosted_bots", ""))
            facts.live_preview_minutes = str(pd.get("live_preview_minutes", ""))
            facts.engine_tier = str(pd.get("engine_tier", ""))
        except Exception:
            logger.debug("plan public dict unavailable", exc_info=True)
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
