"""Dialogue engine selection — Rasa only (no rule-based fake intelligence).

DIALOGUE_ENABLED=1 + models/*.tar.gz → Rasa Agent
Otherwise → None (Telegram keeps legacy path; no phrase-memory bot)
"""
from __future__ import annotations

import logging
import os
from typing import Any

from .contract import DialogueRequest, DialogueResponse
from .rasa_engine import RasaEngine

logger = logging.getLogger(__name__)

_rasa = RasaEngine()


def _flag(name: str, default: str = "0") -> bool:
    return (os.getenv(name) or default).strip().lower() in {"1", "true", "yes", "on"}


def dialogue_runtime_enabled() -> bool:
    """True only when Rasa dialogue is intentionally enabled."""
    return _flag("DIALOGUE_ENABLED", "0")


def get_dialogue_engine():
    if dialogue_runtime_enabled() and _rasa.available():
        return _rasa
    return None


async def handle_turn(
    text: str,
    *,
    sender_id: str,
    plan_id: str = "free",
    metadata: dict[str, Any] | None = None,
) -> DialogueResponse | None:
    engine = get_dialogue_engine()
    if engine is None:
        return None
    req = DialogueRequest(
        text=text or "",
        sender_id=str(sender_id),
        plan_id=plan_id or "free",
        metadata=dict(metadata or {}),
    )
    try:
        return await engine.handle(req)
    except Exception:
        logger.exception("Rasa dialogue failed")
        return None


def runtime_status() -> dict[str, Any]:
    eng = get_dialogue_engine()
    return {
        "DIALOGUE_ENABLED": dialogue_runtime_enabled(),
        "rasa_available": _rasa.available(),
        "active_engine": eng.name if eng else None,
        "rule_engine": "disabled",
    }
