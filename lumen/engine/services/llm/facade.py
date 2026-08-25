"""LLM facade — single entry for translate/chat.

Product rule (hard separation — do not mix):
  • Chat / guidance     → Groq only   (GROQ_API_KEY / GROQ_API_KEYS)
  • Translate / spec    → Gemini only (GEMINI_API_KEY / GEMINI_API_KEYS)

  TBE_STRICT_LLM_ROLES=1 (default ON) enforces the split:
    translate chain = GeminiTranslateAdapter only
    chat chain      = GroqChatAdapter only
  No cross-provider failover between Groq and Gemini.

Callers must use ``translate_request`` / ``chat_request`` from this module
or from ``translator_client`` (re-exports). Do not import Groq/Gemini
clients from routers or generation code.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from .adapters import (
    GeminiChatAdapter,
    GeminiTranslateAdapter,
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
    "gemini": GeminiChatAdapter,
    "groq": GroqChatAdapter,
}


def _env_name(value: str | None, default: str) -> str:
    raw = (value or "").strip().lower()
    return raw if raw else default


def _strict_llm_roles() -> bool:
    """Product rule: Gemini=translate only, Groq=chat only (default ON)."""
    raw = (os.getenv("TBE_STRICT_LLM_ROLES") or "1").strip().lower()
    return raw not in {"0", "false", "off", "no"}


def get_translate_provider_name() -> str:
    if _strict_llm_roles():
        return "gemini"
    return _env_name(os.getenv("TRANSLATE_PROVIDER"), "gemini")


def get_chat_provider_name() -> str:
    if _strict_llm_roles():
        return "groq"
    return _env_name(os.getenv("CHAT_PROVIDER"), "groq")


def get_translate_provider() -> TranslateProvider:
    name = get_translate_provider_name()
    cls = _TRANSLATE_REGISTRY.get(name) or GeminiTranslateAdapter
    if name not in _TRANSLATE_REGISTRY:
        logger.warning("Unknown TRANSLATE_PROVIDER=%s; using gemini", name)
    return cls()  # type: ignore[return-value]


def get_chat_provider() -> ChatProvider:
    name = get_chat_provider_name()
    cls = _CHAT_REGISTRY.get(name) or GroqChatAdapter
    if name not in _CHAT_REGISTRY:
        logger.warning("Unknown CHAT_PROVIDER=%s; using groq", name)
    return cls()  # type: ignore[return-value]



def _translate_chain() -> list:
    """Translate providers: Gemini only when strict roles; else primary+fallback."""
    primary = get_translate_provider()
    if _strict_llm_roles():
        # Force Gemini for translation — never Groq
        return [GeminiTranslateAdapter()]
    chain = [primary]
    if getattr(primary, "name", "") == "gemini":
        chain.append(GroqTranslateAdapter())
    else:
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
    """Chat providers — Groq only under product rule (strict roles default ON).

    Key rotation stays inside the Groq pool (GROQ_API_KEYS). Gemini is never
    used for chat when TBE_STRICT_LLM_ROLES is enabled.
    """
    if _strict_llm_roles():
        return [GroqChatAdapter()]
    primary = get_chat_provider()
    chain = [primary]
    # Non-strict only: allow configured primary; still no automatic Gemini tail
    # unless CHAT_PROVIDER explicitly selects gemini.
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
    """Translate user bot request → structured features (provider-agnostic)."""
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
    """Chat reply for Lumen UX (provider-agnostic + fallback)."""
    try:
        from lumen.engine.services.llm_budget_gate import gate_llm_call
        ok, reason = gate_llm_call(message or "", context)
        if not ok:
            logger.warning("chat_request blocked by llm budget: %s", reason)
            return {
                "answer": "تم بلوغ الحد اليومي لاستخدام الذكاء الاصطناعي. حاول لاحقاً.",
                "reply": "تم بلوغ الحد اليومي لاستخدام الذكاء الاصطناعي. حاول لاحقاً.",
                "action": {"name": "", "requires_confirmation": False},
                "budget_blocked": True,
                "reason": reason,
            }
    except Exception as _bg_exc:
        import os as _os
        _env = (_os.getenv("ENVIRONMENT") or _os.getenv("TBE_ENV") or "").strip().lower()
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
        """Router reads ``answer``; some paths only set ``reply`` — unify."""
        if not isinstance(result, dict):
            return result
        answer = str(result.get("answer") or "").strip()
        reply = str(result.get("reply") or "").strip()
        if not answer and reply:
            result = dict(result)
            result["answer"] = reply
        return result

    last_err: Exception | None = None
    for provider in _chat_chain():
        try:
            result = provider.chat(message, context)
            if result is not None:
                result = _normalize_chat_result(result)
                # Empty answer is treated as soft failure → try next provider
                if not str(result.get("answer") or "").strip() and not result.get("budget_blocked"):
                    logger.warning(
                        "chat_request provider=%s returned empty answer — next provider",
                        getattr(provider, "name", "?"),
                    )
                    continue
                logger.info(
                    "chat_request provider=%s keys=%s",
                    getattr(provider, "name", "?"),
                    list((result or {}).keys())[:8],
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
        "translate_registry": sorted(_TRANSLATE_REGISTRY.keys()),
        "chat_registry": sorted(_CHAT_REGISTRY.keys()),
        "key_pool": pool,
    }


__all__ = [
    "get_translate_provider",
    "get_chat_provider",
    "get_translate_provider_name",
    "get_chat_provider_name",
    "translate_request",
    "chat_request",
    "status_snapshot",
]
