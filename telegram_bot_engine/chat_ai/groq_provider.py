"""Groq OpenAI-compatible chat provider for SpecTranslator.

Token from GROQ_API_KEY / GROQ_TOKEN at runtime — never hardcode.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODELS = (
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
    "gemma2-9b-it",
)

_TOKEN_ENVS = (
    "GROQ_API_KEY",
    "GROQ_TOKEN",
    "GROQ_KEY",
)


def get_token() -> str:
    for key in _TOKEN_ENVS:
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    return ""


def enabled() -> bool:
    if os.environ.get("GROQ_ENABLED", "1").strip().lower() in {"0", "false", "off", "no"}:
        return False
    return bool(get_token())


def models() -> tuple[str, ...]:
    raw = (os.environ.get("GROQ_MODELS") or "").strip()
    if raw:
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if parts:
            return tuple(parts)
    return DEFAULT_MODELS


def _content(response: requests.Response) -> str:
    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "".join(
            str(x.get("text", "")) for x in content if isinstance(x, dict)
        ).strip()
    return ""


def chat(
    messages: list[dict[str, Any]],
    *,
    timeout: int = 60,
    model: str | None = None,
    max_tokens: int = 2400,
    temperature: float = 0.0,
    json_mode: bool = False,
) -> tuple[str, str]:
    if not enabled():
        raise RuntimeError("GROQ_API_KEY is not configured")
    token = get_token()
    candidates = (model,) if model else models()
    payload: dict[str, Any] = {
        "model": candidates[0] if candidates else DEFAULT_MODELS[0],
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "ai_Agent_7h_bot/groq-provider",
    }
    errors: list[str] = []
    for candidate in candidates:
        payload["model"] = candidate
        try:
            response = requests.post(
                GROQ_CHAT_URL, headers=headers, json=payload, timeout=timeout
            )
            if response.ok:
                text = _content(response)
                if text:
                    return text, candidate
                errors.append(f"{candidate}:empty_response")
            else:
                try:
                    detail = response.json().get("error", response.text[:300])
                except Exception:
                    detail = response.text[:300]
                errors.append(f"{candidate}:{detail}")
                logger.warning("Groq model failed %s %s", candidate, detail)
        except requests.RequestException as exc:
            errors.append(f"{candidate}:{type(exc).__name__}:{exc}")
    raise RuntimeError("; ".join(errors)[:1200] or "all_groq_models_failed")


def healthcheck(*, timeout: int = 30) -> dict[str, Any]:
    if not enabled():
        return {"ok": False, "error": "GROQ_API_KEY not configured", "enabled": False}
    try:
        text, model = chat(
            [{"role": "user", "content": "Reply with exactly: GROQ_OK"}],
            timeout=timeout,
            max_tokens=16,
        )
        return {
            "ok": bool(text),
            "model": model,
            "content": (text or "")[:100],
            "enabled": True,
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": f"{type(exc).__name__}:{exc}"[:400],
            "enabled": True,
        }


__all__ = [
    "GROQ_CHAT_URL",
    "DEFAULT_MODELS",
    "enabled",
    "models",
    "chat",
    "healthcheck",
    "get_token",
]
