"""Hugging Face Inference Providers adapter.

Token is read at runtime from HF_TOKEN (or common aliases) and never persisted.
Uses the OpenAI-compatible HF router.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)

HF_CHAT_URL = "https://router.huggingface.co/v1/chat/completions"
# Models verified working on the current HF Inference Providers token.
# Order: strongest first, then cheaper fallback so the user is never left without a model.
DEFAULT_MODELS = (
    "meta-llama/Llama-3.3-70B-Instruct",
    "meta-llama/Llama-3.1-8B-Instruct",
)

_TOKEN_ENVS = (
    "HF_TOKEN",
    "HUGGINGFACE_TOKEN",
    "HUGGINGFACE_HUB_TOKEN",
    "HUGGING_FACE_HUB_TOKEN",
)


def get_token() -> str:
    for key in _TOKEN_ENVS:
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    return ""


def enabled() -> bool:
    if not get_token():
        return False
    return os.environ.get("HF_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}


def models() -> tuple[str, ...]:
    raw = (os.environ.get("HF_MODELS") or os.environ.get("HF_MODEL") or "").strip()
    configured = tuple(x.strip() for x in raw.split(",") if x.strip())
    return configured or DEFAULT_MODELS


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
        return "".join(str(x.get("text", "")) for x in content if isinstance(x, dict)).strip()
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
    """Return (content, model_used), trying configured models in order."""
    if not enabled():
        raise RuntimeError("HF_TOKEN is not configured")
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
        "User-Agent": "ai_Agent_7h_bot/huggingface-provider",
    }
    errors: list[str] = []
    for candidate in candidates:
        payload["model"] = candidate
        try:
            response = requests.post(HF_CHAT_URL, headers=headers, json=payload, timeout=timeout)
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
                logger.warning("HF model failed %s %s", candidate, detail)
        except requests.RequestException as exc:
            errors.append(f"{candidate}:{type(exc).__name__}:{exc}")
    raise RuntimeError("; ".join(errors)[:1200] or "all_hf_models_failed")


def healthcheck(*, timeout: int = 30) -> dict[str, Any]:
    if not enabled():
        return {"ok": False, "error": "HF_TOKEN not configured", "enabled": False}
    try:
        text, model = chat(
            [{"role": "user", "content": "Reply with exactly: HF_OK"}],
            timeout=timeout,
            max_tokens=16,
        )
        return {"ok": bool(text), "model": model, "content": (text or "")[:100], "enabled": True}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"[:400], "enabled": True}


__all__ = ["HF_CHAT_URL", "DEFAULT_MODELS", "enabled", "models", "chat", "healthcheck", "get_token"]
