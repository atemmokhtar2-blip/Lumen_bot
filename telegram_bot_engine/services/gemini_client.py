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
    raw = os.getenv("GEMINI_ENABLED")
    if raw is not None:
        return _truthy(raw)
    return bool((os.getenv("GEMINI_API_KEY") or "").strip())


def model_name() -> str:
    # Kept configurable so the requested legacy model can be changed without
    # a code edit if Google retires or renames the endpoint.
    return (os.getenv("GEMINI_MODEL") or "gemini-1.5-flash").strip()


def _api_key() -> str:
    return (os.getenv("GEMINI_API_KEY") or "").strip()


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
        raise ValueError("Gemini result has no translation object")

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
    key = _api_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    _experiment_delay()
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model_name()}:generateContent"
    )
    payload = {
        "contents": [{"parts": [{"text": _prompt(mode, text, context)}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
            "responseSchema": _RESPONSE_SCHEMA,
        },
    }
    response = requests.post(
        url,
        params={"key": key},
        json=payload,
        timeout=_timeout(),
    )
    response.raise_for_status()
    return _normalize(_extract_json(response.json()))


def translate(text: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    return generate("translate", text, context)


def chat(message: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    return generate("chat", message, context)
