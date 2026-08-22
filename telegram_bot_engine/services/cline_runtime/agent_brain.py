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
import time
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
    "run_shell",
    "finish",
}

_JSON_SCHEMA_HINT = (
    "Respond with ONE JSON object only (no markdown fences). Schema:\n"
    '{"thought": "short plan", "tool": "list_dir|read_file|write_file|edit_file|tree|run_shell|finish", '
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



def _extract_json_object(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    # strip model reasoning tags (qwen etc.)
    raw = re.sub(r"<think>[\s\S]*?</think>", "", raw, flags=re.I).strip()
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
    """Compact history to fit low TPM tiers (e.g. Groq on_demand ~8k)."""
    system_parts: list[str] = []
    user_parts: list[str] = []
    for m in messages:
        role = m.get("role") or ""
        content = str(m.get("content") or "")
        if role == "system":
            system_parts.append(content[:3500])
        elif role == "tool":
            name = m.get("tool_name") or "tool"
            # keep tool results short
            user_parts.append(f"[TOOL RESULT {name}]\n{content[:2500]}")
        else:
            user_parts.append(f"[{role.upper()}]\n{content[:2000]}")
    # keep only last N non-system chunks to control TPM
    try:
        keep = max(4, min(16, int(os.getenv("CLINE_HISTORY_KEEP") or "10")))
    except ValueError:
        keep = 10
    if len(user_parts) > keep:
        user_parts = user_parts[-keep:]
    system = "\n\n".join(system_parts)
    user = "\n\n".join(user_parts)
    # hard cap combined chars (~4 chars/token rough)
    max_chars = int(os.getenv("CLINE_PROMPT_MAX_CHARS") or "12000")
    if len(system) + len(user) > max_chars:
        budget = max(2000, max_chars - len(system))
        user = user[-budget:]
    return system, user


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
            "maxOutputTokens": 2048,
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
    """Groq chat with key pool rotation (up to 100 keys).

    On 429/401/403/503 the failing key is cooled down and the next key is used
    immediately — the agent loop continues without aborting the whole run.
    """
    from telegram_bot_engine.services.llm.key_pool import (
        groq_available,
        mark_groq_cooldown,
        pool_status,
    )

    model = model_id or (os.getenv("GROQ_MODEL") or "qwen/qwen3.6-27b").strip()
    url = "https://api.groq.com/openai/v1/chat/completions"
    anti = (
        "CRITICAL: Do NOT call provider built-in tools (container.exec, browser, etc.). "
        "You only communicate by returning ONE JSON object describing our custom tools."
    )
    base_messages = [
        {"role": "system", "content": anti + "\n\n" + system},
        {"role": "user", "content": f"{user}\n\n{_JSON_SCHEMA_HINT}"},
    ]

    last_error = ""
    # Pull a fresh ready list each outer attempt so cooled keys drop out
    tried_sources: set[str] = set()
    max_key_tries = 100

    for _ in range(max_key_tries):
        ready = groq_available()
        if not ready:
            break
        # skip already-tried in this call
        candidate = None
        for source, key in ready:
            if source not in tried_sources:
                candidate = (source, key)
                break
        if candidate is None:
            # all ready keys already tried this round — stop
            break
        source, key = candidate
        tried_sources.add(source)

        payload = {
            "model": model,
            "temperature": 0.15,
            "max_tokens": 2048,
            "messages": base_messages,
            "response_format": {"type": "json_object"},
        }
        try:
            resp = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=_timeout(),
            )
        except requests.RequestException as exc:
            last_error = f"groq_network:{type(exc).__name__}:{exc}"
            mark_groq_cooldown(source)
            logger.warning("groq network source=%s err=%s — rotate", source, exc)
            continue

        if resp.status_code in {401, 403, 429, 503}:
            body = (resp.text or "")[:240]
            last_error = f"groq_http_{resp.status_code}:{body}"
            if resp.status_code == 429:
                from telegram_bot_engine.services.llm.key_pool import mark_cooldown
                # rate-limit: cool this key longer, immediately try next
                mark_cooldown(source, seconds=float(
                    __import__("os").getenv("GROQ_KEY_COOLDOWN_SEC") or "90"
                ), env_name="GROQ_KEY_COOLDOWN_SEC")
            elif resp.status_code in {401, 403}:
                from telegram_bot_engine.services.llm.key_pool import mark_cooldown
                # bad key: long cool-down
                mark_cooldown(source, seconds=float(
                    __import__("os").getenv("GROQ_BAD_KEY_COOLDOWN_SEC") or "600"
                ))
            else:
                mark_groq_cooldown(source)
            logger.warning(
                "groq rotate source=%s status=%s pool=%s",
                source,
                resp.status_code,
                pool_status().get("groq_keys_ready"),
            )
            continue

        if resp.status_code >= 400:
            body = (resp.text or "")[:300]
            last_error = f"groq_http_{resp.status_code}:{body}"
            # 400 tool_use etc — do not burn the whole pool; retry next key once pattern is model issue
            if "tool_use_failed" in body or "Request too large" in body:
                mark_groq_cooldown(source)
                continue
            raise RuntimeError(last_error)

        body = resp.json()
        choices = body.get("choices") or []
        if not choices:
            last_error = "groq_empty_choices"
            mark_groq_cooldown(source)
            continue
        content = str((choices[0].get("message") or {}).get("content") or "")
        if not content.strip():
            last_error = "groq_empty_content"
            continue
        logger.info("groq ok source=%s model=%s", source, model)
        return content

    status = {}
    try:
        status = pool_status()
    except Exception:
        pass
    raise RuntimeError(
        last_error
        or f"no_groq_key_available pool={status}"
    )



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
    """One reasoning step with smart retries (parse fail / transient HTTP)."""
    choice = choice or select_model(task="build")
    system, user = _system_and_user(messages)
    if not system:
        system = "You are an autonomous coding agent building a software project."

    try:
        max_attempts = max(1, min(4, int(os.getenv("CLINE_LLM_RETRIES") or "3")))
    except ValueError:
        max_attempts = 3

    provider = choice.provider
    last_error = ""
    raw = ""

    for attempt in range(1, max_attempts + 1):
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
            last_error = f"{type(exc).__name__}:{exc}"
            logger.warning(
                "agent_brain attempt %s/%s provider=%s failed: %s",
                attempt,
                max_attempts,
                provider,
                exc,
            )
            # transient? retry
            if attempt < max_attempts and any(
                tok in last_error.lower()
                for tok in ("timeout", "429", "503", "502", "connection", "temporar")
            ):
                delay = 2.0 * attempt
                if "429" in last_error:
                    delay = max(delay, 3.0 * attempt)
                time.sleep(delay)
                continue
            if attempt < max_attempts:
                continue
            return {
                "thought": "",
                "tool": None,
                "args": {},
                "finish": False,
                "summary": "",
                "raw": "",
                "parse_ok": False,
                "error": last_error,
                "attempts": attempt,
            }

        obj = _extract_json_object(raw)
        decision = _normalize_decision(obj, raw)
        decision["provider"] = provider
        decision["model_id"] = choice.model_id
        decision["attempts"] = attempt
        if decision.get("parse_ok") or decision.get("tool"):
            return decision
        # parse failed — nudge and retry with stronger instruction injected once
        logger.info("agent_brain parse fail attempt %s — retry", attempt)
        user = user + "\n\nIMPORTANT: Previous reply was invalid JSON. Output ONLY one JSON object."
        last_error = "parse_fail"

    decision = _normalize_decision(_extract_json_object(raw), raw)
    decision["provider"] = provider
    decision["model_id"] = choice.model_id
    decision["attempts"] = max_attempts
    if not decision.get("parse_ok"):
        decision["error"] = last_error or "parse_fail"
    return decision



__all__ = ["ALLOWED_TOOLS", "decide"]
