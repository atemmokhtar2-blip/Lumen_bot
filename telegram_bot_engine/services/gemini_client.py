"""Gemini-backed chat and translation client.

Uses the Gemini REST API via requests. Resolves the API key from several
env names (and optional secret files) so Railway typos/spaces do not silently
disable chat. Falls back across models on 404/429/503.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

_ALLOWED_ACTIONS = {
    "",
    "clone_repo",
    "host_start",
    "host_stop",
    "host_status",
    "repo_understand",
    "generate_bot",
    "refine_bot",
}

_KEY_ENV_NAMES = (
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GOOGLE_GENERATIVE_AI_API_KEY",
    "GENAI_API_KEY",
    "GEMINI_KEY",
    "GOOGLE_AI_API_KEY",
)
_NUMBERED_KEY_ENV_NAMES = tuple(f"GEMINI_API_KEY_{idx}" for idx in range(1, 151))
_KEY_COOLDOWN_UNTIL: dict[str, float] = {}

_MODEL_FALLBACKS = (
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-flash-latest",
    "gemini-1.5-flash",
)

_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "action": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "requires_confirmation": {"type": "boolean"},
            },
            "required": ["name", "requires_confirmation"],
        },
        "translation": {
            "type": "object",
            "properties": {
                "purpose": {"type": "string"},
                "features_requested": {"type": "array", "items": {"type": "string"}},
                "flows": {"type": "array", "items": {"type": "string"}},
                "strict_spec": {"type": "boolean"},
                "model": {"type": "string"},
                "confidence": {"type": "number"},
                "clarification_needed": {"type": "boolean"},
                "clarification_questions": {"type": "array", "items": {"type": "string"}},
                "spec_request": {"type": "string"},
            },
            "required": [
                "purpose",
                "features_requested",
                "flows",
                "strict_spec",
                "model",
                "confidence",
                "clarification_needed",
                "clarification_questions",
                "spec_request",
            ],
        },
    },
    "required": ["answer", "action", "translation"],
}


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def model_name() -> str:
    return (os.getenv("GEMINI_MODEL") or "gemini-2.0-flash").strip()


def _normalize_secret(raw: str) -> str:
    key = raw or ""
    for ch in ("\ufeff", "\u200b", "\u200c", "\u200d", "\xa0"):
        key = key.replace(ch, "")
    key = key.strip()
    if len(key) >= 2 and key[0] == key[-1] and key[0] in {"'", '"'}:
        key = key[1:-1].strip()
    if any(c in key for c in (chr(10), chr(13))):
        key = next((ln.strip() for ln in key.splitlines() if ln.strip()), "")
    low = key.lower()
    if low in {"", "your_key", "changeme", "xxx", "null", "none", "undefined"}:
        return ""
    if key and set(key) <= {"*"}:
        return ""
    return key


def _read_key_file(path: str) -> str:
    try:
        p = Path(path)
        if p.is_file():
            return _normalize_secret(p.read_text(encoding="utf-8", errors="ignore"))
    except Exception as exc:
        logger.warning("Gemini key file unreadable path=%s err=%s", path, type(exc).__name__)
    return ""


def _key_cooldown_seconds() -> float:
    try:
        return max(0.0, min(3600.0, float(os.getenv("GEMINI_KEY_COOLDOWN_SEC") or "60")))
    except ValueError:
        return 60.0


def _key_failover_enabled() -> bool:
    raw = (os.getenv("GEMINI_KEY_FAILOVER_ENABLED") or "").strip()
    return _truthy(raw) if raw else True


def _api_keys() -> list[tuple[str, str]]:
    """Resolve ordered keys: primary aliases + GEMINI_API_KEY_0..150 via key_pool."""
    from telegram_bot_engine.services.llm.key_pool import gemini_keys
    return gemini_keys()



def _api_key() -> str:
    """Return the first available key for backward compatibility."""
    keys = _api_keys()
    return keys[0][1] if keys else ""


def _available_api_keys() -> list[tuple[str, str]]:
    """Keys not in cooldown; failover until exhausted then retry soonest."""
    from telegram_bot_engine.services.llm.key_pool import gemini_available
    return gemini_available()



def _cooldown_key(source: str) -> None:
    from telegram_bot_engine.services.llm.key_pool import mark_gemini_cooldown
    mark_gemini_cooldown(source)



def enabled() -> bool:
    raw = (os.getenv("GEMINI_ENABLED") or "").strip()
    if raw:
        return _truthy(raw)
    return bool(_api_keys())


def status_snapshot() -> dict[str, Any]:
    """Safe diagnostics (never logs the raw key)."""
    keys = _api_keys()
    key = keys[0][1] if keys else ""
    present_names: list[str] = []
    try:
        for k in os.environ:
            ku = (k or "").strip().upper()
            if "GEMINI" in ku or ku in {n.upper() for n in _KEY_ENV_NAMES}:
                present_names.append(k)
    except Exception:
        pass
    return {
        "enabled": enabled(),
        "key_present": bool(key),
        "key_count": len(keys),
        "key_len": len(key),
        "key_prefix": (key[:4] + "...") if len(key) >= 8 else ("set" if key else ""),
        "model": model_name(),
        "gemini_enabled_env": os.getenv("GEMINI_ENABLED"),
        "env_names_seen": present_names[:20],
    }


def _timeout() -> float:
    try:
        return max(8.0, min(30.0, float(os.getenv("GEMINI_TIMEOUT_SEC") or "18")))
    except ValueError:
        return 18.0


def _experiment_delay() -> None:
    environment = (os.getenv("ENVIRONMENT") or "").strip().lower()
    if environment in {"production", "prod"}:
        return
    if _truthy(os.getenv("GEMINI_EXPERIMENT_MODE")):
        time.sleep(2)


def _prompt(mode: str, text: str, context: dict[str, Any] | None) -> str:
    context = dict(context or {})
    if not context.get("spec_core_capabilities"):
        try:
            from telegram_bot_engine.spec_core.registry import CAPABILITIES
            # Keep the chat prompt small for speed; full registry is used by
            # the translator / spec_core path, not every chat turn.
            context["spec_core_capabilities"] = sorted(CAPABILITIES.keys())[:80]
        except Exception:
            context["spec_core_capabilities"] = []
    elif isinstance(context.get("spec_core_capabilities"), list):
        context["spec_core_capabilities"] = list(context["spec_core_capabilities"])[:80]
    facts = json.dumps(context, ensure_ascii=False, sort_keys=True)
    operation = (
        "ترجمة الطلب إلى spec_core" if mode == "translate" else "الرد الطبيعي على المستخدم"
    )
    return f"""
أنت Maestro (ميسترو): منصة توليد بوتات تيليجرام احترافية ومساعد هندسي للمشاريع.
تفهم الطلب، تترجم لقدرات spec_core، وتولّد بوت جاهز (zip/استضافة).
أنت قيد التطوير المستمر وتتطور باستمرار — كن صادقًا عند السؤال عن الحالة.
المطور المعروف الوحيد هو حاتم. لا تدّعِ وجود فريق أو شركة أو مطور آخر.
نفّذ هذه المهمة: {operation}.

قواعد صارمة:
1. أجب بالعربية الطبيعية عند الإمكان، وافهم العامية المصرية والمصطلحات الإنجليزية التقنية.
2. استخدم الحقائق الموجودة في SERVER_CONTEXT فقط عند الحديث عن خطة المستخدم أو استخدامه أو مشروعه.
3. لا تخترع أرقامًا أو حدودًا أو capabilities أو حالة مستودع غير موجودة في السياق.
4. إذا كانت المعلومة المطلوبة غير موجودة، اجعل clarification_needed=true واسأل سؤالًا محددًا.
5. لا تنفذ أي إجراء بنفسك. إذا طلب المستخدم إجراءً حساسًا، املأ action بالاسم المناسب واجعل requires_confirmation=true.
6. أعد JSON مطابقًا للمخطط المطلوب، ولا تضف Markdown خارجه.
    7. features_requested يجب أن تحتوي فقط على مفاتيح capabilities الموجودة حرفيًا في SPEC_CORE_CAPABILITIES، وليس أسماء عامة أو مترادفات مخترعة.
    8. flows يجب أن تكون مسارات مستخرجة من طلب المستخدم، وليست قائمة افتراضية.
    9. confidence رقم بين 0 و1.
    10. إذا لم يكتمل وصف البوت بعد، اجعل clarification_needed=true وspec_request فارغًا.
    11. إذا اكتملت المواصفات أو قال المستخدم «ابدأ/نفّذ/ولّد» بعد اكتمالها، اجعل action.name="generate_bot" أو "refine_bot" عند تعديل بوت موجود، وclarification_needed=false، واكتب spec_request كطلب واحد مستقل يفهمه spec_core ويحتوي على عبارة «بوت» أو «Telegram bot» وعلى features_requested الدقيقة فقط.
    12. spec_request ليس ردًا للمستخدم؛ هو عقد داخلي لإرساله إلى spec_core.
    13. إن وُجد conversation_summary أو conversation_history في SERVER_CONTEXT فأكمل منه؛ تبديل المفتاح/المزود لا يلغي سياق المستخدم.

SERVER_CONTEXT:
{facts}

SPEC_CORE_CAPABILITIES:
{json.dumps(context.get("spec_core_capabilities") or [], ensure_ascii=False)}

USER_REQUEST:
{text[:20000]}
""".strip()


def _extract_json(body: dict[str, Any]) -> dict[str, Any]:
    candidates = body.get("candidates") or []
    if not candidates:
        raise ValueError("Gemini response has no candidates")
    parts = ((candidates[0].get("content") or {}).get("parts") or [])
    raw = "".join(str(part.get("text") or "") for part in parts)
    if not raw.strip():
        raise ValueError("Gemini response has empty text")
    # Tolerate markdown fences
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("Gemini response is not a JSON object")
    return parsed


def _normalize(result: dict[str, Any]) -> dict[str, Any]:
    answer = result.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        # plain text fallback
        if isinstance(result.get("text"), str) and result["text"].strip():
            answer = result["text"]
        else:
            raise ValueError("Gemini result has no answer")

    action = result.get("action")
    if not isinstance(action, dict):
        action = {"name": "", "requires_confirmation": False}
    action_name = str(action.get("name") or "")
    if action_name not in _ALLOWED_ACTIONS:
        action = {"name": "", "requires_confirmation": False}
    else:
        action = {
            "name": action_name,
            "requires_confirmation": bool(action.get("requires_confirmation")),
        }

    translation = result.get("translation")
    if not isinstance(translation, dict):
        translation = {
            "purpose": "",
            "features_requested": [],
            "flows": [],
            "strict_spec": False,
            "model": model_name(),
            "confidence": 0.0,
            "clarification_needed": False,
            "clarification_questions": [],
            "spec_request": "",
        }

    def strings(name: str) -> list[str]:
        value = translation.get(name) or []
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()][:100]

    try:
        confidence = float(translation.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0

    normalized_translation = {
        "purpose": str(translation.get("purpose") or "").strip(),
        "features_requested": strings("features_requested"),
        "flows": strings("flows"),
        "strict_spec": bool(translation.get("strict_spec")),
        "model": model_name(),
        "confidence": max(0.0, min(1.0, confidence)),
        "clarification_needed": bool(translation.get("clarification_needed")),
        "clarification_questions": strings("clarification_questions"),
        "spec_request": str(translation.get("spec_request") or "").strip()[:20000],
    }
    return {
        "ok": True,
        "answered": True,
        "source": "gemini",
        "model": model_name(),
        "answer": answer.strip(),
        "action": action,
        "translation": normalized_translation,
    }


def validate_spec_translation(translation: dict[str, Any] | None) -> bool:
    """Return True only for an executable, non-ambiguous spec_core handoff."""
    if not isinstance(translation, dict):
        return False
    if bool(translation.get("clarification_needed")):
        return False
    spec_request = str(translation.get("spec_request") or "").strip()
    if len(spec_request) < 8:
        return False
    lowered = spec_request.lower()
    if not any(token in lowered for token in ("بوت", "bot", "telegram")):
        return False
    features = translation.get("features_requested")
    if not isinstance(features, list):
        return False
    try:
        from telegram_bot_engine.spec_core.registry import CAPABILITIES
        known = set(CAPABILITIES)
    except Exception:
        return False
    normalized = [str(item).strip() for item in features if str(item).strip()]
    if not normalized or any(item not in known for item in normalized):
        return False
    # A handoff with only core buttons is not enough to generate a bot.
    if not any(item not in {"start", "help", "about", "ping", "lang", "language"} for item in normalized):
        return False
    try:
        confidence = float(translation.get("confidence") or 0.0)
    except (TypeError, ValueError):
        return False
    return confidence >= 0.60


def generate(mode: str, text: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call Gemini with model fallback and authorized-key failover."""
    keys = _available_api_keys()
    if not keys:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    _experiment_delay()
    primary = model_name()
    candidates: list[str] = []
    for name in [primary, *_MODEL_FALLBACKS]:
        if name and name not in candidates:
            candidates.append(name)

    last_error: Exception | None = None
    base_payload = {
        "contents": [{"parts": [{"text": _prompt(mode, text, context)}]}],
    }
    schema_config = {
        "temperature": 0.2,
        "responseMimeType": "application/json",
        "responseSchema": _RESPONSE_SCHEMA,
    }
    plain_config = {
        "temperature": 0.2,
        "responseMimeType": "application/json",
    }

    for key_source, key in keys:
        rotate_key = False
        for model in candidates:
            url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent"
            )
            for use_schema in (True, False):
                payload = {
                    **base_payload,
                    "generationConfig": schema_config if use_schema else plain_config,
                }
                try:
                    response = requests.post(
                        url,
                        params={"key": key},
                        json=payload,
                        timeout=_timeout(),
                        headers={"Content-Type": "application/json"},
                    )
                except requests.RequestException as exc:
                    last_error = exc
                    logger.warning(
                        "Gemini network error source=%s model=%s: %s",
                        key_source,
                        model,
                        exc,
                    )
                    _cooldown_key(key_source)
                    rotate_key = True
                    break

                if response.status_code in {429, 503}:
                    body_preview = (response.text or "")[:240]
                    logger.warning(
                        "Gemini source=%s model=%s HTTP %s — key cooldown and failover; body=%s",
                        key_source,
                        model,
                        response.status_code,
                        body_preview,
                    )
                    last_error = RuntimeError(
                        f"Gemini source {key_source} HTTP {response.status_code}: {body_preview}"
                    )
                    _cooldown_key(key_source)
                    rotate_key = True
                    break

                if response.status_code == 404:
                    logger.warning(
                        "Gemini source=%s model=%s HTTP 404 — model fallback",
                        key_source,
                        model,
                    )
                    last_error = RuntimeError(f"Gemini model {model} HTTP 404")
                    break

                if response.status_code in {401, 403}:
                    body_preview = (response.text or "")[:240]
                    logger.error(
                        "Gemini source=%s auth HTTP %s; key cooldown and failover: %s",
                        key_source,
                        response.status_code,
                        body_preview,
                    )
                    last_error = RuntimeError(
                        f"Gemini source {key_source} auth HTTP {response.status_code}: {body_preview}"
                    )
                    _cooldown_key(key_source)
                    rotate_key = True
                    break

                if response.status_code >= 400:
                    body_preview = (response.text or "")[:400]
                    logger.warning(
                        "Gemini HTTP %s source=%s model=%s schema=%s body=%s",
                        response.status_code,
                        key_source,
                        model,
                        use_schema,
                        body_preview,
                    )
                    last_error = RuntimeError(
                        f"Gemini HTTP {response.status_code}: {body_preview}"
                    )
                    continue

                try:
                    result = _normalize(_extract_json(response.json()))
                except Exception as exc:
                    last_error = exc
                    logger.warning(
                        "Gemini parse failed source=%s model=%s schema=%s: %s",
                        key_source,
                        model,
                        use_schema,
                        exc,
                    )
                    continue

                if model != primary or not use_schema or key_source != keys[0][0]:
                    logger.info(
                        "Gemini ok source=%s model=%s schema=%s",
                        key_source,
                        model,
                        use_schema,
                    )
                return result
            if rotate_key:
                break

    raise RuntimeError(f"Gemini generate failed for all authorized keys/models: {last_error}")


def translate(text: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    return generate("translate", text, context)


def _compact_retry_allowed(exc: Exception) -> bool:
    message = str(exc).lower()
    blocked = ("401", "403", "429", "503", "not configured", "api key rejected")
    return not any(token in message for token in blocked)


def _compact_chat_context(context: dict[str, Any] | None) -> dict[str, Any]:
    compact = dict(context or {})
    history = compact.get("conversation_history")
    if isinstance(history, list):
        compact["conversation_history"] = history[-4:]
    compact["compact_retry"] = True
    return compact


def chat(message: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        return generate("chat", message, context)
    except Exception as first_error:
        enabled_retry = _truthy(os.getenv("GEMINI_COMPACT_RETRY_ENABLED") or "1")
        if not enabled_retry or not _compact_retry_allowed(first_error):
            raise
        logger.warning(
            "Gemini chat compact retry after %s: %s",
            type(first_error).__name__,
            str(first_error)[:240],
        )
        return generate("chat", message, _compact_chat_context(context))
