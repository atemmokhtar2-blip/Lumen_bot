"""xAI Grok chat — primary fast path for user conversation.

Uses XAI_API_KEY → https://api.x.ai/v1/chat/completions
Same response contract as groq_chat (answer/reply/action).
"""
from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)

_XAI_URL = "https://api.x.ai/v1/chat/completions"


def _enabled() -> bool:
    if (os.getenv("XAI_CHAT_DISABLED") or "").strip().lower() in {"1", "true", "yes"}:
        return False
    return bool((os.getenv("XAI_API_KEY") or "").strip())


def _models() -> list[str]:
    raw = (os.getenv("XAI_CHAT_MODEL") or os.getenv("GROK_MODEL") or "grok-2-latest").strip()
    # allow comma-separated fallbacks
    return [m.strip() for m in raw.split(",") if m.strip()] or ["grok-2-latest"]


def _timeout() -> float:
    try:
        return float(os.getenv("XAI_CHAT_TIMEOUT") or "45")
    except Exception:
        return 45.0


def chat_via_grok(
    message: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Lumen chat via xAI Grok. Returns None if unavailable."""
    try:
        from lumen.engine.services.llm_budget_gate import gate_llm_call

        ok, reason = gate_llm_call(message or "", context)
        if not ok:
            logger.warning("chat_via_grok blocked by llm budget: %s", reason)
            return None
    except Exception as exc:
        if (os.getenv("ENVIRONMENT") or "").strip().lower() not in {
            "dev",
            "development",
            "local",
            "test",
        }:
            logger.exception("chat_via_grok budget gate fail-closed: %s", exc)
            return None

    if not _enabled():
        return None
    key = (os.getenv("XAI_API_KEY") or "").strip()
    if not key:
        return None

    system = (
        "You are Lumen, a helpful Arabic/English assistant for building bots and software. "
        "Answer clearly and briefly. When the user wants to generate a bot, set action "
        "generate_bot and put a clean English or Arabic spec in translation.spec_request."
    )
    try:
        from lumen.engine.services.prompt_fence import (
            safe_user_message,
            system_prompt_injection_rules,
        )

        system = system + system_prompt_injection_rules()
        user_content = safe_user_message(message or "", context)
    except Exception:
        user_content = (message or "")[:8000]

    last_error: Exception | None = None
    for model in _models():
        try:
            resp = requests.post(
                _XAI_URL,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "temperature": 0.3,
                    "max_tokens": 2048,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_content},
                    ],
                },
                timeout=_timeout(),
            )
            if resp.status_code >= 400:
                logger.warning("Grok chat HTTP %s model=%s", resp.status_code, model)
                last_error = RuntimeError(f"http_{resp.status_code}")
                continue
            data = resp.json()
            content = (
                ((data.get("choices") or [{}])[0].get("message") or {}).get("content")
                or ""
            ).strip()
            if not content:
                continue
            return {
                "answer": content,
                "reply": content,
                "action": {"name": "", "requires_confirmation": False},
                "model": model,
                "source": "xai_grok",
                "provider": "xai",
            }
        except Exception as exc:
            last_error = exc
            logger.warning("Grok chat failed model=%s: %s", model, exc)
            continue
    if last_error:
        logger.warning("Grok chat exhausted models: %s", last_error)
    return None


__all__ = ["chat_via_grok"]
