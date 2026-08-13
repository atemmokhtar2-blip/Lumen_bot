"""Dialogue engine selection.

DIALOGUE_ENABLED=1:
  1) Rasa Agent if model loads and TF inference works
  2) else lightweight FAQ engine (domain/nlu keywords, no TensorFlow)
Otherwise → None (Telegram legacy generation path only)
"""
from __future__ import annotations

import logging
import os
from typing import Any

from .contract import DialogueRequest, DialogueResponse
from .faq_engine import FaqEngine
from .rasa_engine import RasaEngine

logger = logging.getLogger(__name__)

_rasa = RasaEngine()
_faq = FaqEngine()


def _flag(name: str, default: str = "0") -> bool:
    return (os.getenv(name) or default).strip().lower() in {"1", "true", "yes", "on"}


def dialogue_runtime_enabled() -> bool:
    return _flag("DIALOGUE_ENABLED", "0")


def get_dialogue_engine():
    """Preferred engine for status display (Rasa if healthy else FAQ)."""
    if not dialogue_runtime_enabled():
        return None
    if _rasa.available():
        return _rasa
    return _faq


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
    # Try Rasa first when it claims availability
    if _rasa.available():
        try:
            resp = await _rasa.handle(req)
            if resp is not None and resp.handled and (resp.text or "").strip():
                return resp
        except Exception:
            logger.exception("Rasa dialogue failed — trying FAQ")
    # FAQ always available when dialogue is enabled
    try:
        return await _faq.handle(req)
    except Exception:
        logger.exception("FAQ dialogue failed")
        return None


def runtime_status() -> dict[str, Any]:
    eng = get_dialogue_engine()
    st = {
        "DIALOGUE_ENABLED": dialogue_runtime_enabled(),
        "rasa_available": _rasa.available(),
        "active_engine": eng.name if eng else None,
        "faq_fallback": True,
    }
    try:
        st.update(_rasa.status())
    except Exception:
        pass
    try:
        st.update(_faq.status())
    except Exception:
        pass
    return st
