"""Groq-backed spec translator + Gemini chat client.

Translation runs on Groq only (no external Qwen translator service).
Gemini remains the optional chat-only path. Any unavailable external service
returns None so the deterministic spec_core path stays authoritative.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_KEY_COOLDOWN_UNTIL: dict[str, float] = {}

# Models available on the current Groq free surface (verified against the key).
# Prefer a compact model for JSON translation; fall back to larger ones.
_DEFAULT_MODELS = (
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "qwen/qwen3.6-27b",
    "allam-2-7b",
)


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _enabled() -> bool:
    raw = (os.getenv("GROQ_TRANSLATOR_ENABLED") or os.getenv("MAESTRO_TRANSLATOR_ENABLED") or "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    if raw in {"1", "true", "yes", "on"}:
        return True
    return bool(_api_keys())


def _api_keys() -> list[tuple[str, str]]:
    """Collect GROQ_API_KEY + GROQ_API_KEY_1..50 (same pattern as Gemini)."""
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    primary = (os.getenv("GROQ_API_KEY") or "").strip()
    if primary and primary not in seen:
        found.append(("GROQ_API_KEY", primary))
        seen.add(primary)
    for idx in range(1, 51):
        name = f"GROQ_API_KEY_{idx}"
        val = (os.getenv(name) or "").strip()
        if val and val not in seen:
            found.append((name, val))
            seen.add(val)
    return found


def _key_cooldown_seconds() -> float:
    try:
        return max(0.0, float(os.getenv("GROQ_KEY_COOLDOWN_SEC") or "60"))
    except ValueError:
        return 60.0


def _available_keys() -> list[tuple[str, str]]:
    keys = _api_keys()
    if not keys:
        return []
    if not _truthy(os.getenv("GROQ_KEY_FAILOVER_ENABLED") or "1"):
        return keys[:1]
    now = time.monotonic()
    ready = [(s, k) for s, k in keys if _KEY_COOLDOWN_UNTIL.get(s, 0.0) <= now]
    return ready or keys[:1]


def _cooldown_key(source: str) -> None:
    sec = _key_cooldown_seconds()
    if sec > 0:
        _KEY_COOLDOWN_UNTIL[source] = time.monotonic() + sec
        logger.warning("Groq key cooldown source=%s for %.0fs", source, sec)


def _models() -> list[str]:
    primary = (os.getenv("GROQ_TRANSLATOR_MODEL") or "").strip()
    extra = [
        x.strip()
        for x in (os.getenv("GROQ_TRANSLATOR_MODEL_FALLBACKS") or "").split(",")
        if x.strip()
    ]
    ordered: list[str] = []
    for name in ([primary] if primary else []) + extra + list(_DEFAULT_MODELS):
        if name and name not in ordered:
            ordered.append(name)
    return ordered


def _timeout() -> float:
    try:
        return max(8.0, min(60.0, float(os.getenv("GROQ_TRANSLATOR_TIMEOUT_SEC") or "25")))
    except ValueError:
        return 25.0


def _min_confidence() -> float:
    try:
        return max(0.0, min(1.0, float(os.getenv("GROQ_TRANSLATOR_MIN_CONFIDENCE") or "0.55")))
    except ValueError:
        return 0.55


def _spec_core_capabilities() -> list[str]:
    try:
        from telegram_bot_engine.spec_core.registry import CAPABILITIES
        return sorted(str(key) for key in CAPABILITIES.keys())
    except Exception as exc:
        logger.warning("spec_core capability list unavailable: %s", exc)
        return []


def _gemini_enabled() -> bool:
    try:
        from .gemini_client import enabled as gemini_enabled
        return gemini_enabled()
    except Exception:
        if (os.getenv("GEMINI_ENABLED") or "").strip():
            return _truthy(os.getenv("GEMINI_ENABLED"))
        return bool((os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip())


def _build_messages(text: str, context: dict[str, Any], capabilities: list[str]) -> list[dict[str, str]]:
    # Keep the capability list bounded so prompts stay small and cheap.
    caps = capabilities[:120]
    gemini_u = context.get("gemini_understanding") or {}
    history = list(context.get("conversation_history") or [])[-6:]
    system = (
        "You are Maestro Spec Translator for Telegram bots. "
        "Return ONE JSON object only (no markdown) with keys: "
        "purpose (string), features_requested (array of exact capability keys), "
        "flows (array of short strings), strict_spec (boolean), confidence (0..1), "
        "clarification_needed (boolean), clarification_questions (array of short strings), "
        "spec_request (string). "
        "features_requested MUST be keys that appear exactly in SPEC_CORE_CAPABILITIES. "
        "If the user intent is complete, clarification_needed=false, strict_spec=true, "
        "and spec_request must mention the word bot/بوت and the chosen feature keys. "
        "If intent is incomplete, clarification_needed=true, spec_request=\"\", "
        "and ask at most 2 short clarification_questions. "
        "Never invent capability keys."
    )
    payload = {
        "SPEC_CORE_CAPABILITIES": caps,
        "GEMINI_UNDERSTANDING": gemini_u if isinstance(gemini_u, dict) else {},
        "CONVERSATION_HISTORY": history,
        "USER_REQUEST": (text or "")[:4000],
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "Convert to JSON only:\n" + json.dumps(payload, ensure_ascii=False)},
    ]


def _extract_json(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.removeprefix("```").removeprefix("json").removesuffix("```").strip()
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("Groq response was not valid JSON")
    value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("Groq JSON root must be an object")
    return value


def _normalize_translation(body: dict[str, Any], capabilities: set[str]) -> dict[str, Any]:
    features_raw = body.get("features_requested") or []
    features: list[str] = []
    if isinstance(features_raw, list):
        for item in features_raw:
            key = str(item).strip()
            if key in capabilities and key not in features:
                features.append(key)
    flows_raw = body.get("flows") or []
    flows: list[str] = []
    if isinstance(flows_raw, list):
        for item in flows_raw:
            if isinstance(item, str) and item.strip():
                flows.append(item.strip()[:96])
            elif isinstance(item, dict):
                # Some models return structured flow objects; flatten safely.
                label = " ".join(str(v) for v in item.values() if v)[:96]
                if label:
                    flows.append(label)
    clarification = bool(body.get("clarification_needed"))
    try:
        confidence = float(body.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    spec_request = str(body.get("spec_request") or "").strip()
    if clarification:
        spec_request = ""
    elif not spec_request and features:
        spec_request = "Telegram bot for user request with " + ", ".join(features[:8])
    # Ensure capability keys appear in spec_request for downstream gates.
    if not clarification and features and not any(k in spec_request for k in features):
        spec_request = (spec_request + " " + " ".join(features[:8])).strip()
    if not clarification and "bot" not in spec_request.lower() and "بوت" not in spec_request:
        spec_request = ("Telegram bot: " + spec_request).strip()
    questions = body.get("clarification_questions") or []
    if not isinstance(questions, list):
        questions = []
    questions = [str(q).strip()[:120] for q in questions if str(q).strip()][:2]
    return {
        "purpose": str(body.get("purpose") or "")[:160],
        "features_requested": features[:8],
        "flows": flows[:6],
        "strict_spec": True if not clarification else bool(body.get("strict_spec")),
        "model": str(body.get("model") or "groq"),
        "confidence": confidence if confidence > 0 else (0.7 if features and not clarification else 0.4),
        "clarification_needed": clarification,
        "clarification_questions": questions,
        "spec_request": spec_request[:240],
    }


def _validate_translation(translation: dict[str, Any]) -> None:
    if translation.get("clarification_needed"):
        return
    features = translation.get("features_requested") or []
    if not isinstance(features, list) or not features:
        raise ValueError("completed translation requires features_requested")
    if not str(translation.get("spec_request") or "").strip():
        raise ValueError("completed translation requires spec_request")
    if float(translation.get("confidence") or 0.0) < _min_confidence():
        raise ValueError("Groq confidence below threshold")


def translate_request(text: str, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Translate user text into a validated spec_core-oriented contract via Groq."""
    if not _enabled():
        return None
    keys = _available_keys()
    if not keys:
        logger.warning("Groq translator skipped; no GROQ_API_KEY configured")
        return None

    context = dict(context or {})
    capabilities = _spec_core_capabilities()
    if not capabilities:
        capabilities = [
            "start", "help", "welcome_set", "user_ban", "user_warn", "user_mute",
            "rules", "lock_chat", "delete_message",
        ]
    cap_set = set(capabilities)
    messages = _build_messages(text or "", context, capabilities)
    models = _models()
    last_error: Exception | None = None

    for source, api_key in keys:
        for model in models:
            try:
                response = requests.post(
                    _GROQ_URL,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "temperature": float(os.getenv("GROQ_TRANSLATOR_TEMPERATURE") or "0.1"),
                        "max_tokens": int(os.getenv("GROQ_TRANSLATOR_MAX_TOKENS") or "900"),
                        "response_format": {"type": "json_object"},
                        "messages": messages,
                    },
                    timeout=_timeout(),
                )
                if response.status_code in {401, 403}:
                    _cooldown_key(source)
                    last_error = RuntimeError(f"Groq auth HTTP {response.status_code} source={source}")
                    logger.warning("%s", last_error)
                    break  # next key
                if response.status_code in {429, 503, 502}:
                    _cooldown_key(source)
                    last_error = RuntimeError(f"Groq rate/limit HTTP {response.status_code} source={source} model={model}")
                    logger.warning("%s", last_error)
                    # try next model on same key once, else next key
                    if response.status_code == 429:
                        break
                    continue
                if response.status_code == 400 and "model" in (response.text or "").lower():
                    last_error = RuntimeError(f"Groq model unavailable: {model}")
                    logger.warning("%s body=%s", last_error, response.text[:200])
                    continue
                response.raise_for_status()
                payload = response.json()
                content = (
                    ((payload.get("choices") or [{}])[0].get("message") or {}).get("content")
                    or ""
                )
                body = _extract_json(content)
                translation = _normalize_translation(body, cap_set)
                translation["model"] = str(payload.get("model") or model)
                _validate_translation(translation)
                logger.info(
                    "Groq translation ok source=%s model=%s features=%s clarification=%s",
                    source,
                    translation.get("model"),
                    translation.get("features_requested"),
                    translation.get("clarification_needed"),
                )
                return translation
            except requests.exceptions.Timeout as exc:
                last_error = exc
                logger.warning("Groq timeout source=%s model=%s", source, model)
                continue
            except Exception as exc:
                last_error = exc
                logger.warning("Groq translate failed source=%s model=%s: %s", source, model, exc)
                continue
    logger.warning("Groq translator unavailable; using deterministic spec_core fallback: %s", last_error)
    return None


def chat_request(message: str, context: dict[str, Any]) -> dict[str, Any] | None:
    """Ask Gemini for chat only; Groq is intentionally translation-only."""
    if not _gemini_enabled():
        logger.warning(
            "Gemini chat skipped; key_present=%s GEMINI_ENABLED=%s",
            bool((os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()),
            os.getenv("GEMINI_ENABLED"),
        )
        return None
    try:
        from .gemini_client import chat, status_snapshot
        logger.info("Gemini chat path active %s", status_snapshot())
        return chat(message, context or {})
    except Exception as exc:
        logger.exception("Gemini chat unavailable; continuing generation path: %s", exc)
        return None
