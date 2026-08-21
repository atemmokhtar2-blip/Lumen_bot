"""Groq-backed chat for Maestro (same JSON contract as Gemini chat).

Returns the normalized shape expected by message_router:
  {answer, action: {name, requires_confirmation}, translation: {...}|None, model}
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_KEY_COOLDOWN_UNTIL: dict[str, float] = {}

_ALLOWED_ACTIONS = {
    "",
    "clone_repo",
    "host_start",
    "host_stop",
    "host_status",
    "repo_understand",
    "generate_bot",
    "refine_bot",
    "repo_inspect",
}

# Fast chat models first
_CHAT_MODELS = (
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "allam-2-7b",
    "qwen/qwen3.6-27b",
)


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _api_keys() -> list[tuple[str, str]]:
    from telegram_bot_engine.services.llm.key_pool import groq_keys
    return groq_keys()



def _enabled() -> bool:
    raw = (os.getenv("GROQ_CHAT_ENABLED") or os.getenv("GROQ_TRANSLATOR_ENABLED") or "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    if raw in {"1", "true", "yes", "on"}:
        return True
    return bool(_api_keys())


def _cooldown_sec() -> float:
    try:
        return max(0.0, float(os.getenv("GROQ_KEY_COOLDOWN_SEC") or "60"))
    except ValueError:
        return 60.0


def _available_keys() -> list[tuple[str, str]]:
    from telegram_bot_engine.services.llm.key_pool import groq_available
    return groq_available()



def _models() -> list[str]:
    raw = (os.getenv("GROQ_CHAT_MODELS") or os.getenv("GROQ_MODELS") or "").strip()
    if raw:
        return [m.strip() for m in raw.split(",") if m.strip()]
    return list(_CHAT_MODELS)


def _timeout() -> float:
    try:
        return max(8.0, float(os.getenv("GROQ_CHAT_TIMEOUT_SEC") or "45"))
    except ValueError:
        return 45.0


def _product_brief() -> str:
    try:
        from telegram_bot_engine.services.platform_status import system_prompt_block
        status_block = system_prompt_block()
    except Exception:
        status_block = (
            "حالة المنتج: أنت قيد التطوير المستمر — عند شكوى المستخدم من أخطاء "
            "أقرّ بذلك وقل إن المنصة قيد التطوير والمشاكل تُصلح مع التحديثات."
        )
    parts = [
        "أنت Maestro (ميسترو): منصة توليد بوتات تيليجرام احترافية.",
        (
            "ماذا تفعل: تفهم طلب المستخدم بالعربي/الإنجليزي، تترجم المواصفات لقدرات حقيقية "
            "(spec_core)، تولّد مشروع بوت جاهز (handlers + services + zip)، ويمكن استضافته."
        ),
        (
            "دورك: تفهم نية المستخدم وتختار أداة من قائمة الأدوات فقط. "
            "لا تسحب مستودعات ولا تعدّل ملفات بنفسك — التنفيذ دائمًا على محركات Maestro. "
            "الأدوات: clone_repo, repo_inspect, repo_understand, generate_bot, refine_bot, "
            "host_status, host_start, host_stop. "
            "عند الحاجة املأ action.name باسم الأداة وaction.params بالوسائط (مثل url). "
            "لتحليل بوت موجود استخدم active_bot_brief أو action=repo_inspect. "
            "للتعديل action=refine_bot مع translation.spec_request."
        ),
        status_block,
        (
            "الخطط والحدود والاستخدام: فقط من SERVER_CONTEXT (plan، usage، quotas). "
            "إن لم توجد المعلومة قل ذلك بصراحة ولا تخترع أرقامًا."
        ),
    ]
    return "\n".join(parts) + "\n"



def _build_system(context: dict[str, Any]) -> str:
    caps: list[str] = []
    try:
        from telegram_bot_engine.spec_core.registry import CAPABILITIES

        caps = sorted(CAPABILITIES.keys())[:80]
    except Exception:
        caps = list(context.get("spec_core_capabilities") or [])[:80]
    context = dict(context or {})
    context["spec_core_capabilities"] = caps
    try:
        from telegram_bot_engine.services.platform_status import to_context_dict
        context.update({k: v for k, v in to_context_dict().items() if v is not None})
    except Exception:
        context.setdefault("platform_under_development", True)
        context.setdefault("platform_status", "قيد التطوير المستمر")
    facts = json.dumps(context, ensure_ascii=False, sort_keys=True)[:12000]
    try:
        from telegram_bot_engine.services.tool_runtime.registry import tool_catalog_for_prompt
        tool_cat = tool_catalog_for_prompt()
    except Exception:
        tool_cat = "clone_repo, repo_inspect, generate_bot, refine_bot"
    return (

        _product_brief()
        + "\nقواعد الرد:\n"
        "1) أجب بالعربية الطبيعية (افهم العامية المصرية والإنجليزي التقني).\n"
        "2) استخدم SERVER_CONTEXT فقط لخطة المستخدم/الاستخدام/المشروع/المستودع.\n"
        "3) لا تنفّذ إجراءات بنفسك. للإجراءات الحساسة املأ action مع requires_confirmation=true.\n"
        "4) أعد JSON فقط (بدون markdown) بالمفاتيح: answer, action, translation.\n"
        "5) action.name واحد من: \"\" | generate_bot | clone_repo | host_start | host_stop | "
        "host_status | repo_understand | repo_inspect | repo_modify | refine_bot\n"
        "6) إذا طلب المستخدم بناء بوت واكتملت المواصفات أو قال ابدأ/نفّذ/ولّد: "
        "action.name=generate_bot و translation.clarification_needed=false و "
        "translation.spec_request عقد واضح يحتوي بوت/Telegram bot و features_requested من القائمة فقط.\n"
        "7) features_requested مفاتيح حرفية من SPEC_CORE_CAPABILITIES فقط.\n"
        "8) إن نقصت المواصفات: clarification_needed=true واسأل سؤالًا محددًا.\n"
        "9) translation يمكن أن يكون null في الدردشة العادية؛ answer مطلوب دائمًا.\n"
        "10) إذا وُجد conversation_summary أو conversation_history في السياق فأكمل منه — "
        "قد يتبدل مزود/مفتاح الشات بين الرسائل ولا تنسَ ما سبق.\n"
        f"\nSERVER_CONTEXT:\n{facts}\n"
        f"\nSPEC_CORE_CAPABILITIES:\n{json.dumps(caps, ensure_ascii=False)}\n"
        f"\nAVAILABLE_TOOLS:\n{tool_cat}\n"
    )


def _extract_json(content: str) -> dict[str, Any]:
    cleaned = (content or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
    # find outermost object
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        cleaned = cleaned[start : end + 1]
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("chat response is not a JSON object")
    return data


def _normalize(result: dict[str, Any], *, model: str) -> dict[str, Any]:
    answer = result.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        if isinstance(result.get("text"), str) and result["text"].strip():
            answer = result["text"]
        else:
            raise ValueError("chat result has no answer")

    action = result.get("action")
    if not isinstance(action, dict):
        action = {"name": "", "requires_confirmation": False}
    action_name = str(action.get("name") or "")
    if action_name not in _ALLOWED_ACTIONS:
        action = {"name": "", "requires_confirmation": False}
    else:
        cleaned = {
            "name": action_name,
            "requires_confirmation": bool(action.get("requires_confirmation")),
        }
        if isinstance(action.get("params"), dict):
            cleaned["params"] = {
                str(k)[:64]: (str(v)[:2000] if not isinstance(v, (int, float, bool)) else v)
                for k, v in list(action["params"].items())[:20]
            }
        action = cleaned

    translation = result.get("translation")
    if translation is not None and not isinstance(translation, dict):
        translation = None

    out: dict[str, Any] = {
        "answer": answer.strip(),
        "action": action,
        "translation": translation,
        "model": model,
        "provider": "groq",
    }
    return out


def chat_via_groq(
    message: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Maestro chat via Groq. Returns None if disabled/unavailable."""
    if not _enabled():
        logger.warning("Groq chat skipped (disabled or no GROQ_API_KEY)")
        return None
    keys = _available_keys()
    if not keys:
        logger.warning("Groq chat: no API keys")
        return None

    system = _build_system(context or {})
    user_content = (message or "")[:8000]
    last_error: Exception | None = None

    for source, key in keys:
        for model in _models():
            try:
                resp = requests.post(
                    _GROQ_URL,
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
                if resp.status_code in {401, 403, 429}:
                    from telegram_bot_engine.services.llm.key_pool import mark_groq_cooldown
                    mark_groq_cooldown(source)
                    logger.warning(
                        "Groq chat HTTP %s source=%s model=%s — cooldown",
                        resp.status_code,
                        source,
                        model,
                    )
                    last_error = RuntimeError(f"HTTP {resp.status_code}")
                    if resp.status_code in {401, 403}:
                        break  # next key
                    continue
                if resp.status_code >= 400:
                    last_error = RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                    logger.warning(
                        "Groq chat HTTP %s source=%s model=%s body=%s",
                        resp.status_code,
                        source,
                        model,
                        resp.text[:180],
                    )
                    continue
                body = resp.json()
                content = (
                    ((body.get("choices") or [{}])[0].get("message") or {}).get("content")
                    or ""
                )
                parsed = _extract_json(content)
                normalized = _normalize(parsed, model=model)
                logger.info(
                    "Groq chat ok source=%s model=%s action=%s",
                    source,
                    model,
                    (normalized.get("action") or {}).get("name"),
                )
                return normalized
            except requests.exceptions.Timeout as exc:
                last_error = exc
                logger.warning("Groq chat timeout source=%s model=%s", source, model)
                continue
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Groq chat failed source=%s model=%s: %s",
                    source,
                    model,
                    exc,
                )
                continue
    logger.warning("Groq chat unavailable: %s", last_error)
    return None


__all__ = ["chat_via_groq"]
