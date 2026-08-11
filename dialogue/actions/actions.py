"""Custom actions — Phase 0.

Connects Rasa dialogue to platform plan identity (Mongo) without touching
the generation engine. Safe if Mongo/env is absent (returns guided defaults).
"""
from __future__ import annotations

import logging
import os
from typing import Any

from rasa_sdk import Action, Tracker
from rasa_sdk.events import SlotSet
from rasa_sdk.executor import CollectingDispatcher

logger = logging.getLogger(__name__)


def _resolve_plan(tracker: Tracker) -> str:
    """Best-effort plan from metadata or platform store."""
    # sender_id is telegram user id when bridge sets it
    sender = str(tracker.sender_id or "")
    meta_plan = (tracker.latest_message or {}).get("metadata") or {}
    if isinstance(meta_plan, dict) and meta_plan.get("plan_id"):
        return str(meta_plan["plan_id"])
    try:
        if (os.getenv("MONGODB_URI") or "").strip() and sender.isdigit():
            # Import only when needed; actions process may not have full app on path
            import sys
            root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            if root not in sys.path:
                sys.path.insert(0, root)
            from b2b_platform.plan_gate import resolve_user_plan
            return resolve_user_plan(user_id=int(sender))
    except Exception as exc:
        logger.debug("plan resolve skipped: %s", type(exc).__name__)
    return "free"


class ActionSessionStart(Action):
    def name(self) -> str:
        return "action_session_start"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: dict[str, Any],
    ) -> list:
        plan = _resolve_plan(tracker)
        return [SlotSet("plan_id", plan)]


class ActionReportPlan(Action):
    def name(self) -> str:
        return "action_report_plan"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: dict[str, Any],
    ) -> list:
        plan = _resolve_plan(tracker)
        labels = {
            "free": "Free — مجاني",
            "starter": "المبادر (Starter) — $8/شهر",
            "growth": "النمو (Growth) — $30/شهر",
        }
        try:
            import sys
            root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            if root not in sys.path:
                sys.path.insert(0, root)
            from b2b_platform.plans import get_plan, public_plan_dict
            pd = public_plan_dict(get_plan(plan))
            text = (
                f"👤 خطتك الحالية: {labels.get(plan, plan)}\n"
                f"• التوليد: {pd['generations_per_month']}/شهر\n"
                f"• الاستضافة 24/7: {pd['hosted_bots']} بوت\n"
                f"• معاينة حية: {pd['live_preview_minutes']} دقيقة\n"
                f"• المحرك: {pd['engine_tier']}"
            )
        except Exception:
            text = f"👤 خطتك الحالية: {labels.get(plan, plan)}\n(للتفاصيل اكتب /plan من تيليجرام)"
        dispatcher.utter_message(text=text)
        return [SlotSet("plan_id", plan)]


class ActionNoteBotIdea(Action):
    def name(self) -> str:
        return "action_note_bot_idea"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: dict[str, Any],
    ) -> list:
        text = (tracker.latest_message or {}).get("text") or ""
        return [SlotSet("last_bot_idea", text[:500])]


class ActionDefaultFallback(Action):
    def name(self) -> str:
        return "action_default_fallback"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: dict[str, Any],
    ) -> list:
        dispatcher.utter_message(response="utter_default")
        return []
