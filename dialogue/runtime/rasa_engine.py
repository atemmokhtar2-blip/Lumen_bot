"""Rasa adapter — only active when model + flag present."""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any

from .contract import DialogueEngine, DialogueRequest, DialogueResponse
from .dynamic_answers import answer_for_intent

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
            parsed = await agent.parse_message(request.text.strip())
        except Exception:
            logger.exception("RasaEngine parse_message failed")
            return None

        intent_data = parsed.get("intent") or {}
        intent = str(intent_data.get("name") or "")
        confidence = float(intent_data.get("confidence") or 0.0)
        entities = parsed.get("entities") or []
        requested_plan = next(
            (
                str(entity.get("value"))
                for entity in entities
                if isinstance(entity, dict) and entity.get("entity") == "plan_name"
            ),
            None,
        )
        response_text = answer_for_intent(
            intent,
            sender_id=str(request.sender_id),
            fallback_plan_id=request.plan_id,
            requested_plan_id=requested_plan,
        )
        if not response_text:
            return None
        return DialogueResponse(
            text=response_text,
            intent=intent,
            confidence=confidence,
            engine=self.name,
            slots={"plan_id": request.plan_id, "resolved_intent": intent},
            handled=True,
        )
