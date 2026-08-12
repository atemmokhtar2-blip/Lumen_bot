"""Rasa adapter — only active when model + flag present."""
from __future__ import annotations

import asyncio
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
        self._load_error: str | None = None

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
            [p for p in _MODELS.glob("*.tar.gz") if p.is_file() and p.stat().st_size > 1000],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return models[0] if models else None

    def _load_sync(self):
        """Load agent in worker thread — never call from the asyncio event loop thread directly."""
        with self._lock:
            if self._agent is not None:
                return self._agent
            if self._tried:
                return None
            self._tried = True
            model = self._latest_model()
            if not model:
                self._load_error = "no_model"
                return None
            try:
                from rasa.core.agent import Agent

                logger.info("RasaEngine loading %s (%.1f MB)", model.name, model.stat().st_size / 1e6)
                self._agent = Agent.load(str(model))
                self._load_error = None
                logger.info("RasaEngine ready")
                return self._agent
            except Exception as exc:
                self._load_error = f"{type(exc).__name__}: {exc}"[:300]
                logger.exception("RasaEngine load failed: %s", self._load_error)
                self._agent = None
                return None

    async def _load(self):
        loop = asyncio.get_running_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, self._load_sync),
                timeout=float(os.getenv("RASA_LOAD_TIMEOUT_SEC") or "120"),
            )
        except asyncio.TimeoutError:
            self._load_error = "load_timeout"
            logger.error("RasaEngine load timed out")
            return None

    async def handle(self, request: DialogueRequest) -> DialogueResponse | None:
        text = (request.text or "").strip()
        if not text:
            return None
        agent = await self._load()
        if agent is None:
            return None
        try:
            parse_fn = getattr(agent, "parse_message", None)
            if parse_fn is None:
                return None
            if asyncio.iscoroutinefunction(parse_fn):
                parsed = await parse_fn(text)
            else:
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(None, parse_fn, text)
                if asyncio.iscoroutine(result):
                    parsed = await result
                else:
                    parsed = result
        except Exception:
            logger.exception("RasaEngine parse_message failed")
            return None

        if not isinstance(parsed, dict):
            return None

        intent_data = parsed.get("intent") or {}
        intent = str(intent_data.get("name") or "")
        confidence = float(intent_data.get("confidence") or 0.0)
        min_conf = float(os.getenv("RASA_MIN_CONFIDENCE") or "0.35")
        if confidence < min_conf and intent not in {"greet", "goodbye", "bot_challenge", "ask_help"}:
            logger.info(
                "Rasa low confidence intent=%s conf=%.3f — defer to legacy",
                intent,
                confidence,
            )
            return None

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
            logger.info("Rasa intent=%s has no answer mapping — defer to legacy", intent)
            return None
        return DialogueResponse(
            text=response_text,
            intent=intent,
            confidence=confidence,
            engine=self.name,
            slots={"plan_id": request.plan_id, "resolved_intent": intent},
            handled=True,
        )

    def status(self) -> dict[str, Any]:
        model = self._latest_model()
        return {
            "available": self.available(),
            "model": model.name if model else None,
            "loaded": self._agent is not None,
            "load_error": self._load_error,
            "tried": self._tried,
        }
