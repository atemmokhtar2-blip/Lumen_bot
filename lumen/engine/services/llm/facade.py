"""LLM facade — single entry for translate/chat.

Post multi-agent architecture (deterministic catalog engine retired):

  • Chat     → Grok (xAI) first for speed, then Groq
  • Translate → residual only (Groq then Gemini); bot generation goes multi-agent
  • TBE_STRICT_LLM_ROLES is OFF by default (old Gemini=translate / Groq=chat killed)

Callers use translate_request / chat_request from this module or translator_client.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from .adapters import (
    GeminiChatAdapter,
    GeminiTranslateAdapter,
    GrokChatAdapter,
    GroqChatAdapter,
    GroqTranslateAdapter,
)
from .ports import ChatProvider, TranslateProvider

logger = logging.getLogger(__name__)

_TRANSLATE_REGISTRY: dict[str, type] = {
    "groq": GroqTranslateAdapter,
    "gemini": GeminiTranslateAdapter,
}
_CHAT_REGISTRY: dict[str, type] = {
    "xai": GrokChatAdapter,
    "grok": GrokChatAdapter,
    "groq": GroqChatAdapter,
    "gemini": GeminiChatAdapter,
}


def _env_name(value: str | None, default: str) -> str:
    raw = (value or "").strip().lower()
    return raw if raw else default


def _strict_llm_roles() -> bool:
    """Legacy split Gemini=translate / Groq=chat — DEFAULT OFF (retired)."""
    raw = (os.getenv("TBE_STRICT_LLM_ROLES") or "0").strip().lower()
    return raw in {"1", "true", "on", "yes"}


def get_translate_provider_name() -> str:
    if _strict_llm_roles():
        return "gemini"
    return _env_name(os.getenv("TRANSLATE_PROVIDER"), "groq")


def get_chat_provider_name() -> str:
    if _strict_llm_roles():
        return "groq"
    # Grok first when key present
    if (os.getenv("XAI_API_KEY") or "").strip():
        return _env_name(os.getenv("CHAT_PROVIDER"), "xai")
    return _env_name(os.getenv("CHAT_PROVIDER"), "groq")


def get_translate_provider() -> TranslateProvider:
    name = get_translate_provider_name()
    cls = _TRANSLATE_REGISTRY.get(name) or GroqTranslateAdapter
    if name not in _TRANSLATE_REGISTRY:
        logger.warning("Unknown TRANSLATE_PROVIDER=%s; using groq", name)
    return cls()  # type: ignore[return-value]


def get_chat_provider() -> ChatProvider:
    name = get_chat_provider_name()
    cls = _CHAT_REGISTRY.get(name) or GrokChatAdapter
    if name not in _CHAT_REGISTRY:
        logger.warning("Unknown CHAT_PROVIDER=%s; using xai/grok", name)
        cls = GrokChatAdapter
    return cls()  # type: ignore[return-value]


def _translate_chain() -> list:
    """Residual translate path — not required for multi-agent generation."""
    if _strict_llm_roles():
        return [GeminiTranslateAdapter()]
    primary = get_translate_provider()
    chain = [primary]
    # Prefer fast Groq before Gemini for any leftover translate calls
    if getattr(primary, "name", "") != "groq":
        chain.insert(0, GroqTranslateAdapter())
    if getattr(primary, "name", "") != "gemini":
        chain.append(GeminiTranslateAdapter())
    seen: set[str] = set()
    out = []
    for p in chain:
        n = getattr(p, "name", "")
        if n in seen:
            continue
        seen.add(n)
        out.append(p)
    return out


def _chat_chain() -> list:
    """Chat: Grok (xAI) primary for speed → Groq → optional Gemini last."""
    if _strict_llm_roles():
        return [GroqChatAdapter()]
    chain: list = []
    # Grok first when keyed
    if (os.getenv("XAI_API_KEY") or "").strip():
        chain.append(GrokChatAdapter())
    primary = get_chat_provider()
    chain.append(primary)
    chain.append(GroqChatAdapter())
    # Gemini chat only if explicitly allowed (not default product path)
    if (os.getenv("CHAT_ALLOW_GEMINI") or "").strip().lower() in {"1", "true", "yes"}:
        chain.append(GeminiChatAdapter())
    seen: set[str] = set()
    out = []
    for p in chain:
        n = getattr(p, "name", "")
        if n in seen:
            continue
        seen.add(n)
        out.append(p)
    return out


def translate_request(
    text: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Translate user bot request → structured features (residual path)."""
    try:
        from lumen.engine.services.prompt_fence import sanitize_user_text

        text = sanitize_user_text(text or "", max_len=8000)
    except Exception:
        text = (text or "")[:8000]
    last_err: Exception | None = None
    for provider in _translate_chain():
        try:
            result = provider.translate(text, context)
            if result is not None:
                logger.info(
                    "translate_request provider=%s model=%s features=%s",
                    getattr(provider, "name", "?"),
                    (result or {}).get("model"),
                    (result or {}).get("features_requested"),
                )
                return result
        except Exception as exc:
            last_err = exc
            logger.warning(
                "translate_request provider=%s failed: %s",
                getattr(provider, "name", "?"),
                exc,
            )
            continue
    if last_err:
        logger.warning("translate_request all providers failed: %s", last_err)
    return None


def chat_request(
    message: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Chat / guidance — Grok first, then Groq."""
    try:
        from lumen.engine.services.prompt_fence import sanitize_user_text

        message = sanitize_user_text(message or "", max_len=8000)
    except Exception:
        message = (message or "")[:8000]

    # Budget gate
    try:
        from lumen.engine.services.llm_budget_gate import gate_llm_call

        ok, reason = gate_llm_call(message or "", context)
        if not ok:
            return {
                "answer": "تم تجاوز حد الاستخدام مؤقتاً. حاول لاحقاً.",
                "reply": "تم تجاوز حد الاستخدام مؤقتاً. حاول لاحقاً.",
                "action": {"name": "", "requires_confirmation": False},
                "budget_blocked": True,
                "reason": reason,
            }
    except Exception as _bg_exc:
        _env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "").strip().lower()
        if _env not in {"dev", "development", "local", "test"}:
            logger.exception("llm budget gate failed — fail-closed in production")
            return {
                "answer": "خدمة الحد الأمني غير متاحة. حاول لاحقاً.",
                "reply": "خدمة الحد الأمني غير متاحة. حاول لاحقاً.",
                "action": {"name": "", "requires_confirmation": False},
                "budget_blocked": True,
                "reason": f"gate_error:{type(_bg_exc).__name__}",
            }
        logger.exception("llm budget gate failed open-check (dev only)")

    def _normalize_chat_result(result: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(result, dict):
            return result
        answer = str(result.get("answer") or "").strip()
        reply = str(result.get("reply") or "").strip()
        if not answer and reply:
            result = dict(result)
            result["answer"] = reply
        elif not reply and answer:
            result = dict(result)
            result["reply"] = answer
        return result

    last_err: Exception | None = None
    for provider in _chat_chain():
        try:
            result = provider.chat(message, context)
            if result is not None:
                result = _normalize_chat_result(result)
                if not str(result.get("answer") or "").strip() and not result.get(
                    "budget_blocked"
                ):
                    logger.warning(
                        "chat_request provider=%s empty answer — next",
                        getattr(provider, "name", "?"),
                    )
                    continue
                logger.info(
                    "chat_request provider=%s model=%s",
                    getattr(provider, "name", "?"),
                    (result or {}).get("model"),
                )
                return result
        except Exception as exc:
            last_err = exc
            logger.warning(
                "chat_request provider=%s failed: %s",
                getattr(provider, "name", "?"),
                exc,
            )
            continue
    if last_err:
        logger.warning("chat_request all providers failed: %s", last_err)
    return None


def status_snapshot() -> dict[str, Any]:
    """Observability: providers + key pool counts (never raw secrets)."""
    try:
        from lumen.engine.services.llm.key_pool import pool_status

        pool = pool_status()
    except Exception:
        pool = {}
    return {
        "translate_provider": get_translate_provider_name(),
        "chat_provider": get_chat_provider_name(),
        "strict_llm_roles": _strict_llm_roles(),
        "translate_registry": sorted(_TRANSLATE_REGISTRY.keys()),
        "chat_registry": sorted(_CHAT_REGISTRY.keys()),
        "key_pool": pool,
    }


__all__ = [
    "translate_request",
    "chat_request",
    "status_snapshot",
    "get_translate_provider",
    "get_chat_provider",
    "get_translate_provider_name",
    "get_chat_provider_name",
]
