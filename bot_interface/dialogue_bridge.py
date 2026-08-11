"""Telegram ↔ Maestro dialogue runtime (Phase 0 hardened).

Never invokes telegram_bot_engine generation.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("ai_agent_7h_bot.dialogue_bridge")


def dialogue_enabled() -> bool:
    """Backward-compatible name used by messages.py."""
    try:
        from dialogue.runtime.registry import dialogue_runtime_enabled
        return dialogue_runtime_enabled()
    except Exception:
        return False


async def handle_dialogue(
    text: str,
    *,
    sender_id: str,
    plan_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str | None:
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
