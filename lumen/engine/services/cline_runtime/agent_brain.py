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
    raw = re.sub(r"<thinking>[\s\S]*?</thinking>", "", raw, flags=re.I).strip()
    # strip all fenced blocks content preference
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, flags=re.I)
    if fence:
        raw = fence.group(1).strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    for candidate in (raw,):
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    # find balanced-ish JSON objects containing "tool" or "thought"
    for m in re.finditer(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", raw):
        frag = m.group(0)
        try:
            obj = json.loads(frag)
            if isinstance(obj, dict) and (
                "tool" in obj or "thought" in obj or "finish" in obj or "args" in obj
            ):
                return obj
        except json.JSONDecodeError:
            continue
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        # last resort: trailing commas
        cleaned = re.sub(r",\s*}", "}", m.group(0))
        cleaned = re.sub(r",\s*]", "]", cleaned)
        try:
            obj = json.loads(cleaned)
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

    Avoid strict response_format=json_object (causes HTTP 400
    'Failed to generate JSON' on several Groq models). We ask for JSON
    in the prompt and parse it ourselves.

    On 429/401/403/503 the failing key is cooled down and the next key is used.
    """
    from lumen.engine.services.llm.key_pool import (
        groq_available,
        mark_groq_cooldown,
        mark_cooldown,
        pool_status,
    )

    model = model_id or (os.getenv("GROQ_MODEL") or "qwen/qwen3.6-27b").strip()
    url = "https://api.groq.com/openai/v1/chat/completions"
    anti = (
        "CRITICAL: Do NOT call provider built-in tools (container.exec, browser, etc.). "
        "You only communicate by returning ONE JSON object describing our custom tools. "
        "No markdown, no explanation outside JSON."
    )
    base_messages = [
        {"role": "system", "content": anti + "\n\n" + system},
        {"role": "user", "content": f"{user}\n\n{_JSON_SCHEMA_HINT}"},
    ]

    last_error = ""
    tried_sources: set[str] = set()
    max_key_tries = 100
    # Prefer plain chat; optional json_object only if GROQ_JSON_MODE=1
    use_json_mode = (os.getenv("GROQ_JSON_MODE") or "0").strip().lower() in {
        "1", "true", "yes", "on",
    }

    for _ in range(max_key_tries):
        ready = groq_available()
        if not ready:
            break
        candidate = None
        for source, key in ready:
            if source not in tried_sources:
                candidate = (source, key)
                break
        if candidate is None:
            break
        source, key = candidate
        tried_sources.add(source)

        # Two attempts per key: optional json_mode then plain
        modes = [True, False] if use_json_mode else [False]
        for with_json in modes:
            payload: dict[str, Any] = {
                "model": model,
                "temperature": 0.2,
                "max_tokens": 2048,
                "messages": base_messages,
            }
            if with_json:
                payload["response_format"] = {"type": "json_object"}

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
                break  # next key

            if resp.status_code in {401, 403, 429, 503}:
                body = (resp.text or "")[:240]
                last_error = f"groq_http_{resp.status_code}:{body}"
                if resp.status_code == 429:
                    mark_cooldown(
                        source,
                        seconds=float(os.getenv("GROQ_KEY_COOLDOWN_SEC") or "90"),
                        env_name="GROQ_KEY_COOLDOWN_SEC",
                    )
                elif resp.status_code in {401, 403}:
                    mark_cooldown(
                        source,
                        seconds=float(os.getenv("GROQ_BAD_KEY_COOLDOWN_SEC") or "600"),
                    )
                else:
                    mark_groq_cooldown(source)
                logger.warning(
                    "groq rotate source=%s status=%s pool=%s",
                    source,
                    resp.status_code,
                    pool_status().get("groq_keys_ready"),
                )
                break  # next key

            if resp.status_code >= 400:
                body = (resp.text or "")[:400]
                last_error = f"groq_http_{resp.status_code}:{body}"
                # Failed to generate JSON → retry same key without json_object
                if with_json and (
                    "Failed to generate JSON" in body
                    or "failed to generate json" in body.lower()
                    or "json_validate" in body.lower()
                ):
                    logger.warning(
                        "groq json_mode failed source=%s — retry plain", source
                    )
                    continue  # try plain mode same key
                if "tool_use_failed" in body or "Request too large" in body:
                    mark_groq_cooldown(source)
                    break
                # other 400: try next key, don't kill whole run
                logger.warning("groq 400 source=%s body=%s — rotate", source, body[:120])
                mark_groq_cooldown(source)
                break

            body_j = resp.json()
            choices = body_j.get("choices") or []
            if not choices:
                last_error = "groq_empty_choices"
                mark_groq_cooldown(source)
                break
            content = str((choices[0].get("message") or {}).get("content") or "")
            if not content.strip():
                last_error = "groq_empty_content"
                continue
            logger.info(
                "groq ok source=%s model=%s json_mode=%s", source, model, with_json
            )
            return content

    status = {}
    try:
        status = pool_status()
    except Exception:
        pass
    raise RuntimeError(last_error or f"no_groq_key_available pool={status}")




def _call_qwen(system: str, user: str, model_id: str, base_url: str | None = None) -> str:
    """Alibaba DashScope compatible-mode (sk-ws- keys) with key pool + region failover.

    sk-ws keys from international console only work on dashscope-intl.
    On 401 we automatically try the alternate region before rotating keys.
    """
    from lumen.engine.services.llm.key_pool import (
        qwen_available,
        mark_qwen_cooldown,
        mark_cooldown,
        pool_status,
    )

    model = model_id or (os.getenv("QWEN_MODEL") or "qwen-plus").strip()
    preferred = (
        base_url
        or os.getenv("QWEN_BASE_URL")
        or os.getenv("DASHSCOPE_BASE_URL")
        or "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    ).rstrip("/")
    alt = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    intl = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    # Always try preferred first, then the other region
    bases: list[str] = []
    for b in (preferred, intl, alt):
        b = b.rstrip("/")
        if b not in bases:
            bases.append(b)

    anti = (
        "CRITICAL: Return ONE JSON object only for our custom tools. "
        "No markdown fences, no built-in tool calls."
    )
    messages = [
        {"role": "system", "content": anti + "\n\n" + system},
        {"role": "user", "content": f"{user}\n\n{_JSON_SCHEMA_HINT}"},
    ]
    last_error = ""
    tried: set[str] = set()
    for _ in range(100):
        ready = qwen_available()
        if not ready:
            break
        candidate = None
        for source, key in ready:
            if source not in tried:
                candidate = (source, key)
                break
        if candidate is None:
            break
        source, key = candidate
        tried.add(source)

        key_done = False
        for base in bases:
            url = f"{base}/chat/completions"
            payload = {
                "model": model,
                "temperature": 0.2,
                "max_tokens": 2048,
                "messages": messages,
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
                last_error = f"qwen_network:{type(exc).__name__}:{exc}"
                logger.warning("qwen network base=%s err=%s", base, exc)
                continue

            if resp.status_code == 401 or resp.status_code == 403:
                last_error = f"qwen_http_{resp.status_code}:{(resp.text or '')[:200]}"
                logger.warning(
                    "qwen auth fail source=%s base=%s — try next region/key",
                    source,
                    base,
                )
                # try next base URL with same key before cooling
                continue

            if resp.status_code in {429, 503}:
                last_error = f"qwen_http_{resp.status_code}:{(resp.text or '')[:200]}"
                mark_cooldown(
                    source,
                    seconds=float(os.getenv("QWEN_KEY_COOLDOWN_SEC") or "60"),
                )
                logger.warning("qwen rate source=%s — rotate", source)
                key_done = True
                break

            if resp.status_code >= 400:
                last_error = f"qwen_http_{resp.status_code}:{(resp.text or '')[:300]}"
                logger.warning("qwen 400 source=%s base=%s body=%s", source, base, last_error[:120])
                continue

            choices = (resp.json() or {}).get("choices") or []
            if not choices:
                last_error = "qwen_empty_choices"
                continue
            content = str((choices[0].get("message") or {}).get("content") or "")
            if not content.strip():
                last_error = "qwen_empty_content"
                continue
            logger.info("qwen ok source=%s model=%s base=%s", source, model, base)
            return content

        if not key_done:
            # all bases failed auth for this key
            mark_cooldown(
                source,
                seconds=float(os.getenv("QWEN_BAD_KEY_COOLDOWN_SEC") or "300"),
            )

    raise RuntimeError(last_error or f"no_qwen_key pool={pool_status()}")



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


def _call_llamacpp(system: str, user: str, model_id: str, base_url: str | None) -> str:
    """OpenAI-compatible endpoint (llama-server / tablet tunnel).

    Expects base like https://xxx.trycloudflare.com/v1
    Hits POST {base}/chat/completions
    """
    base = (
        base_url
        or os.getenv("LLAMACPP_BASE_URL")
        or os.getenv("OPENAI_COMPAT_BASE_URL")
        or ""
    ).strip().rstrip("/")
    if not base:
        raise RuntimeError("llamacpp_no_base_url")
    # Accept either .../v1 or host root
    if base.endswith("/v1"):
        url = f"{base}/chat/completions"
    else:
        url = f"{base}/v1/chat/completions"
    model = (model_id or os.getenv("LLAMACPP_MODEL") or "qwen").strip()
    # Prefer short non-thinking replies on tiny local models (Qwen3)
    user_body = user
    if os.getenv("LLAMACPP_NO_THINK", "1").strip().lower() in {"1", "true", "yes", "on"}:
        user_body = "/no_think\n" + user
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"{user_body}\n\n{_JSON_SCHEMA_HINT}"},
    ]
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": int(os.getenv("LLAMACPP_MAX_TOKENS") or "1024"),
        "stream": False,
    }
    headers = {"Content-Type": "application/json"}
    api_key = (os.getenv("LLAMACPP_API_KEY") or os.getenv("OPENAI_COMPAT_API_KEY") or "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    resp = requests.post(url, headers=headers, json=payload, timeout=_timeout())
    if resp.status_code >= 400:
        raise RuntimeError(f"llamacpp_http_{resp.status_code}:{(resp.text or '')[:300]}")
    body = resp.json()
    choices = body.get("choices") or []
    if not choices:
        raise RuntimeError("llamacpp_empty_choices")
    msg = choices[0].get("message") or {}
    content = str(msg.get("content") or "").strip()
    # Qwen3 often fills reasoning_content and leaves content empty
    if not content:
        content = str(msg.get("reasoning_content") or "").strip()
    if not content:
        raise RuntimeError("llamacpp_empty_content")
    return content


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
            if provider == "qwen":
                raw = _call_qwen(system, user, choice.model_id, choice.base_url)
            elif provider == "groq":
                try:
                    raw = _call_groq(system, user, choice.model_id)
                except Exception as groq_exc:
                    logger.warning("groq failed (%s) — trying qwen failover", groq_exc)
                    try:
                        from lumen.engine.services.llm.key_pool import qwen_keys
                        if not qwen_keys():
                            raise groq_exc
                        raw = _call_qwen(
                            system,
                            user,
                            (os.getenv("QWEN_MODEL") or "qwen-plus"),
                            None,
                        )
                        provider = "qwen"
                    except Exception:
                        raise groq_exc
            elif provider == "gemini":
                raw = _call_gemini(system, user, choice.model_id)
            elif provider == "xai":
                raw = _call_xai(system, user, choice.model_id)
            elif provider == "ollama":
                raw = _call_ollama(system, user, choice.model_id, choice.base_url)
            elif provider in {"llamacpp", "openai_compat", "tablet"}:
                raw = _call_llamacpp(system, user, choice.model_id, choice.base_url)
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
    # parse failures are soft — agent_loop will nudge and continue
    if not decision.get("parse_ok") and not decision.get("tool"):
        decision["error"] = None
        decision["soft_parse_fail"] = True
    return decision



__all__ = ["ALLOWED_TOOLS", "decide"]
