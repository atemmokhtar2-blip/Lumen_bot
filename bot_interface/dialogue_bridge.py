"""Telegram ↔ Maestro dialogue runtime (Phase 0 hardened).

Never steals bot-generation requests from the legacy pipeline.
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("ai_agent_7h_bot.dialogue_bridge")

# Intents that are platform FAQ — safe for Rasa to answer.
_FAQ_INTENTS = frozenset({
    "greet",
    "goodbye",
    "bot_challenge",
    "affirm",
    "deny",
    "ask_help",
    "ask_capabilities",
    "ask_plan",
    "ask_pricing",
    "ask_how_to_generate",
    "ask_limitations",
    "ask_support",
    "how_platform_works",
    "how_to_upgrade",
    "ask_about_hosting",
    "ask_about_preview",
    "ask_about_watermark",
    "ask_about_free",
    "ask_about_starter",
    "ask_about_growth",
    "project_identity",
    "project_capabilities",
    "project_workflow",
    "ask_current_plan",
    "ask_plan_details",
    "ask_plan_comparison",
    "ask_plan_limits",
    "ask_hosting",
    "ask_preview",
    "ask_generation",
    "ask_billing_support",
    "ask_project_component",
})

# Generation / product-spec signals — must go to telegram_bot_engine, not Rasa.
_GEN_MARKERS = (
    "بوت",
    "bot",
    "telegram",
    "تيليجرام",
    "تليجرام",
    "/start",
    "/help",
    "أمر",
    "اوامر",
    "أوامر",
    "توليد",
    "generate",
    "متجر",
    "مهام",
    "ملاحظات",
    "تذاكر",
    "سلة",
    "كتالوج",
    "feature",
    "command",
)


def dialogue_enabled() -> bool:
    """Backward-compatible name used by messages.py."""
    try:
        from dialogue.runtime.registry import dialogue_runtime_enabled
        return dialogue_runtime_enabled()
    except Exception:
        return False


def looks_like_generation_request(text: str) -> bool:
    """True when the user is describing a bot to build (not asking FAQ)."""
    t = (text or "").strip()
    if not t:
        return False
    low = t.lower()
    # Explicit generation phrasing
    if any(k in low for k in ("ولّد", "ولد بوت", "generate", "اعمل بوت", "اعمل لي بوت", "عايز بوت", "أريد بوت", "اريد بوت")):
        return True
    # Spec-like: mentions bot + structure / commands
    has_bot = any(k in low for k in ("بوت", "bot", "telegram", "تيليجرام", "تليجرام"))
    has_structure = any(
        k in low
        for k in (
            "/start",
            "/help",
            "أمر",
            "اوامر",
            "أوامر",
            "فيه",
            "فيه ",
            "مهام",
            "متجر",
            "ملاحظات",
            "تذاكر",
            "سلة",
            "كتالوج",
        )
    )
    if has_bot and has_structure and len(t) >= 12:
        return True
    # Long message with multiple command-like tokens
    if len(t) >= 40 and sum(1 for m in _GEN_MARKERS if m in low) >= 2:
        return True
    # Slash commands embedded in free text (not a platform /cmd)
    if re.search(r"(^|\s)/[a-zA-Z_]{2,}", t) and has_bot:
        return True
    return False


async def handle_dialogue(
    text: str,
    *,
    sender_id: str,
    plan_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str | None:
    """Return a FAQ reply, or None to let the generation / legacy path run."""
    text = (text or "").strip()
    if not text:
        return None
    if looks_like_generation_request(text):
        logger.info("dialogue skip — generation-like request")
        return None
    try:
        from dialogue.runtime import handle_turn
        resp = await handle_turn(
            text,
            sender_id=str(sender_id),
            plan_id=plan_id or "free",
            metadata=metadata,
        )
        if resp is None or not resp.handled or not (resp.text or "").strip():
            return None
        # Never let Rasa swallow bot-idea / out-of-scope as a final answer
        intent = (getattr(resp, "intent", None) or "").strip()
        if intent in {"describe_bot_idea", "out_of_scope", "nlu_fallback", ""}:
            logger.info("dialogue defer intent=%s to legacy", intent)
            return None
        if intent and intent not in _FAQ_INTENTS:
            logger.info("dialogue defer non-FAQ intent=%s to legacy", intent)
            return None
        return resp.text.strip()
    except Exception:
        logger.exception("dialogue_bridge failure")
        return None


def dialogue_status() -> dict[str, Any]:
    try:
        from dialogue.runtime.registry import runtime_status
        return runtime_status()
    except Exception as exc:
        return {"error": type(exc).__name__}
