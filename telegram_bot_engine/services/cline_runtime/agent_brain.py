"""LLM brain for the free Cline agent — Groq / Gemini / xAI / Ollama.

Env keys NEVER share names:
  GROQ_API_KEY   → api.groq.com   (gsk_...)
  GOOGLE_API_KEY / GEMINI_API_KEY → Gemini
  XAI_API_KEY    → api.x.ai       (xAI Grok)
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import requests

from .model_router import ModelChoice, select_model

logger = logging.getLogger(__name__)

ALLOWED_TOOLS = {
    "list_dir",
    "read_file",
    "write_file",
    "edit_file",
    "tree",
    "finish",
}

_JSON_SCHEMA_HINT = (
    "Respond with ONE JSON object only (no markdown fences). Schema:\n"
    '{"thought": "short plan", "tool": "list_dir|read_file|write_file|edit_file|tree|finish", '
    '"args": {}, "finish": false, "summary": ""}'
)


def _timeout() -> float:
    try:
        return max(20.0, min(180.0, float(os.getenv("CLINE_LLM_TIMEOUT_SEC") or "90")))
    except ValueError:
        return 90.0


def _gemini_key() -> str:
    for name in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_GENERATIVE_AI_API_KEY"):
        k = (os.getenv(name) or "").strip()
        if k and k.lower() not in {"none", "null", "changeme"}:
            return k
    return ""


def _xai_key() -> str:
    k = (os.getenv("XAI_API_KEY") or "").strip()
    if k and k.lower() not in {"none", "null", "changeme"}:
        return k
    return ""


def _groq_key() -> str:
    k = (os.getenv("GROQ_API_KEY") or "").strip()
    if k and k.lower() not in {"none", "null", "changeme"}:
        return k
    return ""


def _extract_json_object(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def _normalize_decision(obj: dict[str, Any] | None, raw_text: str) -> dict[str, Any]:
    if not obj:
        return {
            "thought": (raw_text or "")[:2000],
            "tool": None,
            "args": {},
            "finish": False,
            "summary": "",
            "raw": (raw_text or "")[:1500],
            "parse_ok": False,
        }
    tool = obj.get("tool") or obj.get("tool_name") or obj.get("action")
    if isinstance(tool, dict):
        tool = tool.get("name")
    tool_s = str(tool or "").strip()
    if tool_s and tool_s not in ALLOWED_TOOLS:
        tool_s = ""
    args = obj.get("args") or obj.get("tool_args") or obj.get("input") or {}
    if not isinstance(args, dict):
        args = {}
    finish = bool(obj.get("finish")) or tool_s == "finish"
    if finish:
        tool_s = "finish"
    return {
        "thought": str(obj.get("thought") or obj.get("reasoning") or "")[:2000],
        "tool": tool_s or None,
        "args": args,
        "finish": finish,
        "summary": str(obj.get("summary") or obj.get("message") or "")[:2000],
        "raw": (raw_text or "")[:1500],
        "parse_ok": True,
    }


def _system_and_user(messages: list[dict[str, Any]]) -> tuple[str, str]:
    system_parts: list[str] = []
    user_parts: list[str] = []
    for m in messages:
        role = m.get("role") or ""
        content = str(m.get("content") or "")
        if role == "system":
            system_parts.append(content)
        elif role == "tool":
            name = m.get("tool_name") or "tool"
            user_parts.append(f"[TOOL RESULT {name}]\n{content}")
        else:
            user_parts.append(f"[{role.upper()}]\n{content}")
    return "\n\n".join(system_parts), "\n\n".join(user_parts)


def _call_gemini(system: str, user: str, model_id: str) -> str:
    key = _gemini_key()
    if not key:
        raise RuntimeError("no_gemini_key")
    model = model_id or (os.getenv("GEMINI_MODEL") or "gemini-2.0-flash").strip()
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    prompt = f"{system}\n\n---\n\n{user}\n\n{_JSON_SCHEMA_HINT}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.15,
            "responseMimeType": "application/json",
            "maxOutputTokens": 8192,
        },
    }
    resp = requests.post(
        url,
        params={"key": key},
        json=payload,
        timeout=_timeout(),
        headers={"Content-Type": "application/json"},
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"gemini_http_{resp.status_code}:{(resp.text or '')[:300]}")
    body = resp.json()
    parts = ((body.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    return "".join(str(p.get("text") or "") for p in parts)


def _call_xai(system: str, user: str, model_id: str) -> str:
    key = _xai_key()
    if not key:
        raise RuntimeError("no_xai_key")
    model = model_id or (os.getenv("XAI_MODEL") or "grok-2-latest").strip()
    url = "https://api.x.ai/v1/chat/completions"
    payload = {
        "model": model,
        "temperature": 0.15,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": f"{user}\n\n{_JSON_SCHEMA_HINT}"},
        ],
    }
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload,
        timeout=_timeout(),
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"xai_http_{resp.status_code}:{(resp.text or '')[:300]}")
    body = resp.json()
    choices = body.get("choices") or []
    if not choices:
        raise RuntimeError("xai_empty_choices")
    return str((choices[0].get("message") or {}).get("content") or "")


def _call_groq(system: str, user: str, model_id: str) -> str:
    """Groq OpenAI-compatible chat — primary engine brain when GROQ_API_KEY set."""
    key = _groq_key()
    if not key:
        raise RuntimeError("no_groq_key")
    model = model_id or (os.getenv("GROQ_MODEL") or "llama-3.3-70b-versatile").strip()
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = {
        "model": model,
        "temperature": 0.15,
        "max_tokens": 8192,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": f"{user}\n\n{_JSON_SCHEMA_HINT}"},
        ],
    }
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload,
        timeout=_timeout(),
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"groq_http_{resp.status_code}:{(resp.text or '')[:300]}")
    body = resp.json()
    choices = body.get("choices") or []
    if not choices:
        raise RuntimeError("groq_empty_choices")
    return str((choices[0].get("message") or {}).get("content") or "")


def _call_ollama(system: str, user: str, model_id: str, base_url: str | None) -> str:
    base = (base_url or "http://127.0.0.1:11434").rstrip("/")
    resp = requests.post(
        f"{base}/api/chat",
        json={
            "model": model_id or "llama3.2",
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"{user}\n\n{_JSON_SCHEMA_HINT}"},
            ],
        },
        timeout=_timeout(),
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"ollama_http_{resp.status_code}")
    return str((resp.json().get("message") or {}).get("content") or "")


def decide(messages: list[dict[str, Any]], *, choice: ModelChoice | None = None) -> dict[str, Any]:
    """One reasoning step. Returns normalized decision dict."""
    choice = choice or select_model(task="build")
    system, user = _system_and_user(messages)
    if not system:
        system = "You are an autonomous coding agent building a software project."

    provider = choice.provider
    try:
        if provider == "groq":
            raw = _call_groq(system, user, choice.model_id)
        elif provider == "gemini":
            raw = _call_gemini(system, user, choice.model_id)
        elif provider == "xai":
            raw = _call_xai(system, user, choice.model_id)
        elif provider == "ollama":
            raw = _call_ollama(system, user, choice.model_id, choice.base_url)
        else:
            return {
                "thought": "",
                "tool": None,
                "args": {},
                "finish": False,
                "summary": "",
                "raw": "",
                "parse_ok": False,
                "error": "no_model_provider",
            }
    except Exception as exc:
        logger.warning("agent_brain decide failed provider=%s: %s", provider, exc)
        return {
            "thought": "",
            "tool": None,
            "args": {},
            "finish": False,
            "summary": "",
            "raw": "",
            "parse_ok": False,
            "error": f"{type(exc).__name__}:{exc}",
        }

    obj = _extract_json_object(raw)
    decision = _normalize_decision(obj, raw)
    decision["provider"] = provider
    decision["model_id"] = choice.model_id
    return decision


__all__ = ["ALLOWED_TOOLS", "decide"]
