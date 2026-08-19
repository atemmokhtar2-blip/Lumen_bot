"""Gemini-backed chat and translation client.

The client is intentionally small and synchronous to match the existing
translator_client contract. It uses the Gemini REST API through requests,
keeps the API key in the environment, and validates the generated envelope
before the bot can consume it.
"""
from __future__ import annotations

import json
import logging
import os
import time
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
}

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
                "features_requested": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "flows": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "strict_spec": {"type": "boolean"},
                "model": {"type": "string"},
                "confidence": {"type": "number"},
                "clarification_needed": {"type": "boolean"},
                "clarification_questions": {
                    "type": "array",
                    "items": {"type": "string"},
                },
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
            ],
        },
    },
    "required": ["answer", "action", "translation"],
}


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def enabled() -> bool:
    """On when a key exists, unless GEMINI_ENABLED is explicitly false.

    Empty GEMINI_ENABLED must not disable a valid key.
    """
    raw = (os.getenv("GEMINI_ENABLED") or "").strip()
    if raw:
        return _truthy(raw)
    return bool((os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip())


_MODEL_FALLBACKS = (
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-flash-latest",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash",
)


def model_name() -> str:
    # Default to a current flash model; override with GEMINI_MODEL if needed.
    return (os.getenv("GEMINI_MODEL") or "gemini-3.6-flash").strip()


def _api_key() -> str:
    """Accept GEMINI_API_KEY or GOOGLE_API_KEY; strip paste artifacts."""
    key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "")
    # strip BOM / zero-width / nbsp
    key = key.replace("\ufeff", "").replace("\u200b", "").replace("\xa0", " ")
    key = key.strip()
    if len(key) >= 2 and key[0] == key[-1] and key[0] in ("'", '"'):
        key = key[1:-1].strip()
    if any(c in key for c in (chr(10), chr(13))):
        key = next((ln.strip() for ln in key.splitlines() if ln.strip()), "")
    return key

def status_snapshot() -> dict[str, Any]:
    """Safe diagnostics for logs (never includes the raw API key)."""
    key = _api_key()
    return {
        "enabled": enabled(),
        "key_present": bool(key),
        "key_len": len(key),
        "key_prefix": (key[:4] + "…") if len(key) >= 8 else ("set" if key else ""),
        "model": model_name(),
        "gemini_enabled_env": (os.getenv("GEMINI_ENABLED") if os.getenv("GEMINI_ENABLED") is not None else None),
    }


def _timeout() -> float:
    try:
        return max(10.0, float(os.getenv("GEMINI_TIMEOUT_SEC") or "45"))
    except ValueError:
        return 45.0


def _experiment_delay() -> None:
    """Apply the requested two-second pause only during experiments."""
    if _truthy(os.getenv("GEMINI_EXPERIMENT_MODE")):
        # Deliberate fixed delay required by the experiment instructions.
        time.sleep(2)


def _prompt(mode: str, text: str, context: dict[str, Any] | None) -> str:
    facts = json.dumps(context or {}, ensure_ascii=False, sort_keys=True)
    operation = "ترجمة الطلب إلى spec_core" if mode == "translate" else "الرد الطبيعي على المستخدم"
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
7. features_requested وflows يجب أن تكونا مستخرجتين من طلب المستخدم، لا قائمة افتراضية.
8. confidence رقم بين 0 و1.

SERVER_CONTEXT:
{facts}

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
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Gemini response is not a JSON object")
    return parsed


def _normalize(result: dict[str, Any]) -> dict[str, Any]:
    answer = result.get("answer")
    if not isinstance(answer, str) or not answer.strip():
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
        # Chat-only answers may omit translation; keep conversation alive
        translation = {
            "purpose": "",
            "features_requested": [],
            "flows": [],
            "strict_spec": False,
            "model": model_name(),
            "confidence": 0.0,
            "clarification_needed": False,
            "clarification_questions": [],
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


def generate(mode: str, text: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call Gemini with model fallbacks — same path proven against live API keys.

    Strategy:
      1. Primary model from GEMINI_MODEL (default gemini-3.6-flash).
      2. On 404/429/503 or parse failure → next model in _MODEL_FALLBACKS.
      3. If structured JSON schema is rejected → retry once without responseSchema.
    """
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
                break  # next model

            if response.status_code in {404, 429, 503}:
                logger.warning(
                    "Gemini model %s HTTP %s — fallback",
                    model,
                    response.status_code,
                )
                last_error = RuntimeError(
                    f"Gemini model {model} HTTP {response.status_code}"
                )
                break  # next model

            if response.status_code in {401, 403}:
                body_preview = (response.text or "")[:400]
                logger.error("Gemini auth/permission HTTP %s: %s", response.status_code, body_preview)
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
                # schema may be the problem — try without schema on same model
                continue

            try:
                result = _normalize(_extract_json(response.json()))
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Gemini parse/normalize failed model=%s schema=%s: %s",
                    model,
                    use_schema,
                    exc,
                )
                continue

            if model != primary or not use_schema:
                logger.info(
                    "Gemini ok model=%s schema=%s",
                    model,
                    use_schema,
                )
            return result

    raise RuntimeError(f"Gemini generate failed for all models: {last_error}")



def translate(text: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    return generate("translate", text, context)


def chat(message: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    return generate("chat", message, context)
