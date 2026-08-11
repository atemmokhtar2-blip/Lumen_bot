"""Bridge: Telegram channel ↔ Rasa Agent (Maestro dialogue).

Phase 0 rules:
  - Does NOT call telegram_bot_engine generation.
  - Loads a pre-trained model from dialogue/models if present.
  - If model missing or Rasa unavailable → returns None (caller keeps legacy path).
  - Feature flag: DIALOGUE_ENABLED=1 (default off until model is deployed).
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger("ai_agent_7h_bot.dialogue_bridge")

_ROOT = Path(__file__).resolve().parents[1]
_DIALOGUE_DIR = _ROOT / "dialogue"
_MODELS_DIR = _DIALOGUE_DIR / "models"

_agent = None
_agent_lock = threading.Lock()
_load_attempted = False


def dialogue_enabled() -> bool:
    v = (os.getenv("DIALOGUE_ENABLED") or "0").strip().lower()
    return v in {"1", "true", "yes", "on"}


def _latest_model() -> Path | None:
    if not _MODELS_DIR.is_dir():
        return None
    models = sorted(
        [p for p in _MODELS_DIR.glob("*.tar.gz") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return models[0] if models else None


def get_agent():
    """Lazy-load Rasa Agent once per process. Returns None if unavailable."""
    global _agent, _load_attempted
    if not dialogue_enabled():
        return None
    with _agent_lock:
        if _agent is not None:
            return _agent
        if _load_attempted:
            return None
        _load_attempted = True
        model = _latest_model()
        if model is None:
            logger.warning("dialogue: no model in %s — train with scripts/train_dialogue.sh", _MODELS_DIR)
            return None
        try:
            from rasa.core.agent import Agent

            logger.info("dialogue: loading model %s", model.name)
            _agent = Agent.load(str(model))
            logger.info("dialogue: agent ready")
            return _agent
        except Exception:
            logger.exception("dialogue: failed to load Rasa agent")
            _agent = None
            return None


async def handle_dialogue(
    text: str,
    *,
    sender_id: str,
    plan_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str | None:
    """Run one user turn through Rasa. Returns reply text or None to fall back."""
    if not text or not str(text).strip():
        return None
    agent = get_agent()
    if agent is None:
        return None
    meta = dict(metadata or {})
    if plan_id:
        meta["plan_id"] = plan_id
    try:
        # Rasa 3.x Agent.handle_text
        messages = await agent.handle_text(
            str(text).strip(),
            sender_id=str(sender_id),
        )
        if not messages:
            return None
        parts: list[str] = []
        for m in messages:
            if not isinstance(m, dict):
                continue
            t = m.get("text")
            if t:
                parts.append(str(t))
        if not parts:
            return None
        return "\n".join(parts)
    except Exception:
        logger.exception("dialogue: handle_text failed sender=%s", sender_id)
        return None


def dialogue_status() -> dict[str, Any]:
    model = _latest_model()
    return {
        "enabled_flag": dialogue_enabled(),
        "model": model.name if model else None,
        "agent_loaded": _agent is not None,
        "dialogue_dir": str(_DIALOGUE_DIR),
    }
