"""Engine selection — Rasa if ready, else solid RuleEngine."""
from __future__ import annotations

import logging
import os
from typing import Any

from .contract import DialogueEngine, DialogueRequest, DialogueResponse
from .rule_engine import RuleEngine
from .rasa_engine import RasaEngine

logger = logging.getLogger(__name__)

_rule = RuleEngine()
_rasa = RasaEngine()


def dialogue_runtime_enabled() -> bool:
    """Master switch for dialogue layer in Telegram.

    DIALOGUE_RUNTIME=1 → use RuleEngine and/or Rasa (default ON for Phase 0 solid chat).
    DIALOGUE_ENABLED=1 → prefer Rasa when model exists.
    Set DIALOGUE_RUNTIME=0 only to force full legacy messages.py behaviour.
    """
    v = (os.getenv("DIALOGUE_RUNTIME") or "1").strip().lower()
    return v in {"1", "true", "yes", "on"}


def get_dialogue_engine() -> DialogueEngine:
    if _rasa.available():
        return _rasa
    return _rule


async def handle_turn(
    text: str,
    *,
    sender_id: str,
    plan_id: str = "free",
    metadata: dict[str, Any] | None = None,
) -> DialogueResponse | None:
    if not dialogue_runtime_enabled():
        return None
    req = DialogueRequest(
        text=text or "",
        sender_id=str(sender_id),
        plan_id=plan_id or "free",
        metadata=dict(metadata or {}),
    )
    engine = get_dialogue_engine()
    try:
        resp = await engine.handle(req)
    except Exception:
        logger.exception("dialogue engine %s failed — trying rule fallback", getattr(engine, "name", "?"))
        if engine is not _rule:
            try:
                resp = await _rule.handle(req)
            except Exception:
                logger.exception("rule fallback failed")
                return None
        else:
            return None
    # If Rasa returns nothing useful, fall back to rules
    if resp is None and engine is not _rule:
        try:
            resp = await _rule.handle(req)
        except Exception:
            return None
    return resp


def runtime_status() -> dict[str, Any]:
    return {
        "runtime_enabled": dialogue_runtime_enabled(),
        "active_engine": get_dialogue_engine().name if dialogue_runtime_enabled() else None,
        "rasa_available": _rasa.available(),
        "rule_available": _rule.available(),
    }
