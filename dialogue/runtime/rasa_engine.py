"""Rasa adapter — only active when model + flag present."""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any

from .contract import DialogueEngine, DialogueRequest, DialogueResponse

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
_MODELS = _ROOT / "dialogue" / "models"


class RasaEngine:
    name = "rasa_v1"

    def __init__(self) -> None:
        self._agent = None
        self._lock = threading.Lock()
        self._tried = False

    def available(self) -> bool:
        flag = (os.getenv("DIALOGUE_ENABLED") or "0").strip().lower() in {
            "1", "true", "yes", "on",
        }
        if not flag:
            return False
        return self._latest_model() is not None

    def _latest_model(self) -> Path | None:
        if not _MODELS.is_dir():
            return None
        models = sorted(
            [p for p in _MODELS.glob("*.tar.gz") if p.is_file()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return models[0] if models else None

    def _load(self):
        with self._lock:
            if self._agent is not None:
                return self._agent
            if self._tried:
                return None
            self._tried = True
            model = self._latest_model()
            if not model:
                return None
            try:
                from rasa.core.agent import Agent

                logger.info("RasaEngine loading %s", model.name)
                self._agent = Agent.load(str(model))
                return self._agent
            except Exception:
                logger.exception("RasaEngine load failed")
                return None

    async def handle(self, request: DialogueRequest) -> DialogueResponse | None:
        agent = self._load()
        if agent is None:
            return None
        try:
            messages = await agent.handle_text(
                request.text.strip(),
                sender_id=str(request.sender_id),
            )
        except Exception:
            logger.exception("RasaEngine handle_text failed")
            return None
        if not messages:
            return None
        parts: list[str] = []
        intent = ""
        conf = 0.0
        for m in messages:
            if not isinstance(m, dict):
                continue
            if m.get("text"):
                parts.append(str(m["text"]))
        if not parts:
            return None
        return DialogueResponse(
            text="\n".join(parts),
            intent=intent or "rasa",
            confidence=conf or 0.7,
            engine=self.name,
            slots={"plan_id": request.plan_id},
            handled=True,
        )
