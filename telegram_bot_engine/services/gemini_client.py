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
}

_KEY_ENV_NAMES = (
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GOOGLE_GENERATIVE_AI_API_KEY",
    "GENAI_API_KEY",
    "GEMINI_KEY",
    "GOOGLE_AI_API_KEY",
)

_MODEL_FALLBACKS = (
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-flash-latest",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash",
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
    return (os.getenv("GEMINI_MODEL") or "gemini-3.6-flash").strip()


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


def _api_key() -> str:
    """Resolve key from env (tolerant of name spaces/case) or secret file."""
    for name in _KEY_ENV_NAMES:
        val = _normalize_secret(os.getenv(name) or "")
        if val:
            return val
    wanted = {n.upper() for n in _KEY_ENV_NAMES}
    try:
        for k, v in list(os.environ.items()):
            if (k or "").strip().upper() in wanted:
                val = _normalize_secret(v or "")
                if val:
                    logger.info("Gemini key resolved via env name %r", k)
                    return val
    except Exception:
        logger.exception("Gemini env scan failed")
    for path in (
        (os.getenv("GEMINI_API_KEY_FILE") or "").strip(),
        (os.getenv("GOOGLE_API_KEY_FILE") or "").strip(),
        "/run/secrets/gemini_api_key",
        "/run/secrets/GEMINI_API_KEY",
    ):
        if not path:
            continue
        val = _read_key_file(path)
        if val:
            logger.info("Gemini key resolved via file %s", path)
            return val
    return ""


def enabled() -> bool:
    raw = (os.getenv("GEMINI_ENABLED") or "").strip()
    if raw:
        return _truthy(raw)
    return bool(_api_key())


def status_snapshot() -> dict[str, Any]:
    """Safe diagnostics (never logs the raw key)."""
    key = _api_key()
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
        "key_len": len(key),
        "key_prefix": (key[:4] + "...") if len(key) >= 8 else ("set" if key else ""),
        "model": model_name(),
        "gemini_enabled_env": os.getenv("GEMINI_ENABLED"),
        "env_names_seen": present_names[:20],
    }


def _timeout() -> float:
    try:
        return max(10.0, float(os.getenv("GEMINI_TIMEOUT_SEC") or "45"))
    except ValueError:
        return 45.0


def _experiment_delay() -> None:
    if _truthy(os.getenv("GEMINI_EXPERIMENT_MODE")):
        time.sleep(2)


def _prompt(mode: str, text: str, context: dict[str, Any] | None) -> str:
    context = dict(context or {})
    if not context.get("spec_core_capabilities"):
        try:
            from telegram_bot_engine.spec_core.registry import CAPABILITIES
            context["spec_core_capabilities"] = sorted(CAPABILITIES.keys())
        except Exception:
            context["spec_core_capabilities"] = []
    facts = json.dumps(context, ensure_ascii=False, sort_keys=True)
    operation = (
        "ترجمة الطلب إلى spec_core" if mode == "translate" else "الرد الطبيعي على المستخدم"
    )
    return f"""
أنت Maestro، مساعد هندسي للمشاريع والبوتات.
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
    11. إذا اكتملت المواصفات أو قال المستخدم «ابدأ/نفّذ/ولّد» بعد اكتمالها، اجعل action.name="generate_bot"، وclarification_needed=false، واكتب spec_request كطلب واحد مستقل يفهمه spec_core ويحتوي على عبارة «بوت» أو «Telegram bot» وعلى features_requested الدقيقة فقط.
    12. spec_request ليس ردًا للمستخدم؛ هو عقد داخلي لإرساله إلى spec_core.

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
    """Call Gemini with model + schema fallbacks (production path)."""
    key = _api_key()
    if not key:
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
                logger.warning("Gemini network error model=%s: %s", model, exc)
                break

            if response.status_code in {404, 429, 503}:
                logger.warning(
                    "Gemini model %s HTTP %s — fallback",
                    model,
                    response.status_code,
                )
                last_error = RuntimeError(
                    f"Gemini model {model} HTTP {response.status_code}"
                )
                break

            if response.status_code in {401, 403}:
                body_preview = (response.text or "")[:400]
                logger.error(
                    "Gemini auth HTTP %s: %s", response.status_code, body_preview
                )
                raise RuntimeError(
                    f"Gemini API key rejected (HTTP {response.status_code}): {body_preview}"
                )

            if response.status_code >= 400:
                body_preview = (response.text or "")[:400]
                logger.warning(
                    "Gemini HTTP %s model=%s schema=%s body=%s",
                    response.status_code,
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
                    "Gemini parse failed model=%s schema=%s: %s",
                    model,
                    use_schema,
                    exc,
                )
                continue

            if model != primary or not use_schema:
                logger.info("Gemini ok model=%s schema=%s", model, use_schema)
            return result

    raise RuntimeError(f"Gemini generate failed for all models: {last_error}")


def translate(text: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    return generate("translate", text, context)


def chat(message: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    return generate("chat", message, context)
