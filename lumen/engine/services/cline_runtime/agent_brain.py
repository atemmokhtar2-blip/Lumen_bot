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

# Last provider call usage (real API fields when present) — Phase A cost metering
_LAST_CALL_USAGE: dict = {}


def get_last_call_usage() -> dict:
    """Return usage from the most recent provider call (may be empty)."""
    return dict(_LAST_CALL_USAGE)


def _record_usage(provider: str, model_id: str, body: dict | None = None, *, prompt_chars: int = 0) -> None:
    """Extract real token usage from provider JSON; fall back to char estimate."""
    global _LAST_CALL_USAGE
    usage: dict = {"provider": provider, "model_id": model_id or ""}
    body = body or {}
    # Gemini
    um = body.get("usageMetadata") or body.get("usage_metadata") or {}
    if um:
        usage["prompt_tokens"] = int(um.get("promptTokenCount") or um.get("prompt_tokens") or 0)
        usage["completion_tokens"] = int(um.get("candidatesTokenCount") or um.get("completion_tokens") or 0)
        usage["total_tokens"] = int(um.get("totalTokenCount") or um.get("total_tokens") or 0)
    # OpenAI-compatible (Groq, xAI, llama)
    ou = body.get("usage") or {}
    if ou and not usage.get("total_tokens"):
        usage["prompt_tokens"] = int(ou.get("prompt_tokens") or 0)
        usage["completion_tokens"] = int(ou.get("completion_tokens") or 0)
        usage["total_tokens"] = int(ou.get("total_tokens") or 0)
    if not usage.get("total_tokens") and prompt_chars:
        # rough estimate only when API omitted usage
        usage["prompt_tokens_est"] = max(1, prompt_chars // 4)
        usage["estimated"] = True
    _LAST_CALL_USAGE = usage


ALLOWED_TOOLS = {
    "list_dir",
    "read_file",
    "read_files",
    "write_file",
    "edit_file",
    "apply_edits",
    "apply_patch",
    "grep_codebase",
    "grep",
    "search",
    "glob_files",
    "glob",
    "search_replace",
    "tree",
    "run_shell",
    "finish",
    "browser_navigate",
    "browser_content",
    "browser_click",
    "browser_fill",
    "browser_screenshot",
    "run_skill",
    "find_symbol",
    "get_symbol_source",
    "find_references",
    "find_refs",
    "blast_radius",
    "symbol_blast_radius",
    "code_search",
    "hybrid_search",
}

_JSON_SCHEMA_HINT = (
    "Respond with ONE JSON object only (no markdown fences). Schema:\n"
    '{"thought": "short plan", '
    '"tool": "list_dir|read_file|read_files|write_file|edit_file|apply_edits|apply_patch|'
    'grep_codebase|glob_files|find_symbol|get_symbol_source|find_references|blast_radius|code_search|tree|run_shell|finish", '
    '"args": {}, "finish": false, "summary": ""}'
)



def _timeout() -> float:
    try:
        # Default 45s (was 90s) — weakness #2 fix: a single LLM call should not
        # consume 90s. With 2 retries the worst-case per-decide is ~2×45s + backoff
        # ≈ ~95s, and the agent_loop time budget (150s) caps the total anyway.
        return max(20.0, min(120.0, float(os.getenv("CLINE_LLM_TIMEOUT_SEC") or "45")))
    except ValueError:
        return 45.0


def _gemini_key() -> str:
    """First Gemini key — same pool as chat/translate (key_pool)."""
    try:
        from lumen.engine.services.llm.key_pool import gemini_keys
        keys = gemini_keys()
        if keys:
            return keys[0][1]
    except Exception:
        pass
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
    reply = str(obj.get("reply") or obj.get("summary") or obj.get("message") or "")[:2000]
    return {
        "thought": str(obj.get("thought") or obj.get("reasoning") or "")[:2000],
        "tool": tool_s or None,
        "args": args,
        "params": args,  # alias for engine_turn / callers
        "finish": finish,
        "summary": reply,
        "reply": reply,
        "raw": (raw_text or "")[:1500],
        "parse_ok": True,
    }


def _system_and_user(
    messages: list[dict[str, Any]],
    *,
    history_keep: int | None = None,
    prompt_max_chars: int | None = None,
) -> tuple[str, str]:
    """Compact history to fit low TPM tiers (e.g. Groq on_demand ~8k).

    history_keep / prompt_max_chars: first-class overrides from Loop Governor.
    Env vars remain as fallback when caller does not pass explicit caps.
    """
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
    if history_keep is not None:
        keep = max(4, min(16, int(history_keep)))
    else:
        try:
            keep = max(4, min(16, int(os.getenv("CLINE_HISTORY_KEEP") or "10")))
        except ValueError:
            keep = 10
    if len(user_parts) > keep:
        user_parts = user_parts[-keep:]
    system = "\n\n".join(system_parts)
    user = "\n\n".join(user_parts)
    # hard cap combined chars (~4 chars/token rough)
    if prompt_max_chars is not None:
        max_chars = max(4000, min(20000, int(prompt_max_chars)))
    else:
        try:
            max_chars = int(os.getenv("CLINE_PROMPT_MAX_CHARS") or "12000")
        except ValueError:
            max_chars = 12000
    if len(system) + len(user) > max_chars:
        budget = max(2000, max_chars - len(system))
        user = user[-budget:]
    return system, user


def _call_gemini(system: str, user: str, model_id: str) -> str:
    """Gemini generateContent with the same multi-key pool as translator/chat."""
    from lumen.engine.services.llm.key_pool import gemini_available, mark_gemini_cooldown

    keys = gemini_available()
    if not keys:
        # fallback single key
        k = _gemini_key()
        keys = [("GEMINI_API_KEY", k)] if k else []
    if not keys:
        raise RuntimeError("no_gemini_key")

    models = [
        (model_id or "").strip(),
        (os.getenv("GEMINI_MODEL") or "").strip(),
        "gemini-3.1-flash-lite",
        "gemini-3-flash-preview",
        "gemini-3.5-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-flash-latest",
    ]
    models = [m for m in models if m]
    # dedupe
    seen: set[str] = set()
    models = [m for m in models if not (m in seen or seen.add(m))]

    prompt = f"{system}\n\n---\n\n{user}\n\n{_JSON_SCHEMA_HINT}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.15,
            "responseMimeType": "application/json",
            "maxOutputTokens": 2048,
        },
    }
    last_err: Exception | None = None
    for source, key in keys:
        for model in models:
            url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent"
            )
            try:
                resp = requests.post(
                    url,
                    params={"key": key},
                    json=payload,
                    timeout=_timeout(),
                    headers={"Content-Type": "application/json"},
                )
            except requests.RequestException as exc:
                last_err = exc
                continue
            if resp.status_code in {401, 403}:
                # Auth errors are per-KEY — cool down this key and try the next one.
                try:
                    mark_gemini_cooldown(source, reason=f"http_{resp.status_code}")
                except Exception:
                    pass
                last_err = RuntimeError(
                    f"gemini_http_{resp.status_code}:{(resp.text or '')[:200]}"
                )
                break  # next key
            if resp.status_code in {429, 503}:
                # Rate-limit / overload are PER-MODEL (free-tier daily quota is
                # GenerateRequestsPerDayPerProjectPerModel).  Cool down this key
                # but try the NEXT MODEL with the same (or next) key first — a
                # different model has its own quota bucket and may still work.
                try:
                    mark_gemini_cooldown(source, reason=f"http_{resp.status_code}")
                except Exception:
                    pass
                last_err = RuntimeError(
                    f"gemini_http_{resp.status_code}:{(resp.text or '')[:200]}"
                )
                continue  # next model (per-model quota bucket)
            if resp.status_code == 404:
                last_err = RuntimeError(f"gemini_model_404:{model}")
                continue  # next model
            if resp.status_code >= 400:
                last_err = RuntimeError(
                    f"gemini_http_{resp.status_code}:{(resp.text or '')[:300]}"
                )
                continue
            body = resp.json()
            parts = ((body.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
            text = "".join(str(p.get("text") or "") for p in parts)
            if text.strip():
                try:
                    _record_usage("gemini", model, body, prompt_chars=len(prompt))
                except Exception:
                    pass
                return text
            last_err = RuntimeError("gemini_empty_response")
    raise RuntimeError(str(last_err) if last_err else "gemini_exhausted")


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
    content = str((choices[0].get("message") or {}).get("content") or "")
    try:
        _record_usage("xai", model, body, prompt_chars=len(system) + len(user))
    except Exception:
        pass
    return content


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

    model = model_id or (os.getenv("GROQ_MODEL") or "openai/gpt-oss-20b").strip()
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
    tpm_retries = 0
    max_tpm_retries = 3  # after 3 TPM sleeps, give up and let caller handle
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
                    # TPM (tokens-per-minute) rate limit is ORG-level, not per-key.
                    # All 6 keys share the same limit, so rotating keys doesn't help.
                    # Parse Groq's "Please try again in X.Xs" to wait the right time.
                    import re as _re
                    wait_match = _re.search(r"try again in ([\d.]+)\s*s", body)
                    tpm_wait = float(wait_match.group(1)) if wait_match else 0.0
                    # Short cooldown: TPM resets every 60s, so 15s is enough.
                    # If Groq tells us a specific wait, use max(that, 15) capped at 30.
                    cooldown_sec = min(30.0, max(15.0, tpm_wait + 2.0))
                    mark_cooldown(
                        source,
                        seconds=cooldown_sec,
                        env_name="GROQ_KEY_COOLDOWN_SEC",
                    )
                    # If ALL keys are cooling (TPM org-level limit), sleep briefly
                    # instead of immediately failing — the limit resets in ~15s.
                    remaining = pool_status().get("groq_keys_ready", 0)
                    if remaining == 0:
                        logger.warning(
                            "groq TPM exhausted (all keys cooling) — sleeping %.1fs for limit reset",
                            cooldown_sec,
                        )
                        time.sleep(cooldown_sec)
                        # Reset tried_sources so we can retry after the sleep
                        tried_sources.clear()
                        break  # restart key loop with fresh (cooled-down) keys
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
            try:
                _record_usage("groq", model, body_j, prompt_chars=len(system) + len(user))
            except Exception:
                pass
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


def _call_openai_compat(
    system: str,
    user: str,
    model_id: str,
    *,
    base_url: str,
    api_key: str,
    extra_headers: dict | None = None,
) -> str:
    """OpenAI-compatible /chat/completions (openai, openrouter, deepseek, foundry, groq-style)."""
    import requests

    url = (base_url or "").rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    anti = (
        "CRITICAL: Do NOT call provider built-in tools. "
        "Return ONE JSON object for our custom tools only."
    )
    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": anti + "\n\n" + system},
            {"role": "user", "content": f"{user}\n\n{_JSON_SCHEMA_HINT}"},
        ],
        "temperature": 0.2,
    }
    timeout = float(os.getenv("CLINE_LLM_TIMEOUT") or "90")
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f"openai_compat_http_{resp.status_code}:{(resp.text or '')[:400]}")
    body = resp.json()
    choices = body.get("choices") or []
    if not choices:
        raise RuntimeError("openai_compat_empty_choices")
    msg = choices[0].get("message") or {}
    content = str(msg.get("content") or msg.get("reasoning_content") or "").strip()
    if not content:
        raise RuntimeError("openai_compat_empty_content")
    return content


def _call_anthropic(system: str, user: str, model_id: str, api_key: str) -> str:
    import requests

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model_id,
            "max_tokens": 4096,
            "system": system,
            "messages": [{"role": "user", "content": f"{user}\n\n{_JSON_SCHEMA_HINT}"}],
        },
        timeout=float(os.getenv("CLINE_LLM_TIMEOUT") or "90"),
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"anthropic_http_{resp.status_code}:{(resp.text or '')[:400]}")
    text = ""
    for part in (resp.json().get("content") or []):
        if isinstance(part, dict) and part.get("type") == "text":
            text += str(part.get("text") or "")
    text = text.strip()
    if not text:
        raise RuntimeError("anthropic_empty_content")
    return text



def _dispatch_catalog_provider(provider: str, system: str, user: str, choice: ModelChoice) -> str:
    """Execute a catalog provider end-to-end (key → HTTP → text)."""
    from lumen.engine.services.llm.model_catalog import CATALOG

    cat = next((m for m in CATALOG if m.provider == provider and m.model_id == choice.model_id), None)
    if cat is None:
        cat = next((m for m in CATALOG if m.provider == provider), None)

    key = ""
    if cat is not None:
        key = cat.resolve_api_key()
    if not key:
        key = (os.getenv(choice.api_key_env) or "").strip()
    if not key:
        for env in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY",
                    "AZURE_FOUNDRY_KEY", "AZURE_OPENAI_API_KEY", "GROQ_API_KEY"):
            key = (os.getenv(env) or "").strip()
            if key:
                break
    if not key:
        raise RuntimeError(f"{provider}_api_key_missing")

    model_id = (choice.model_id or (cat.model_id if cat else "") or "").strip()
    if not model_id:
        raise RuntimeError(f"{provider}_model_id_missing")

    if provider == "anthropic":
        # Native Anthropic key (not OpenRouter)
        if not key.startswith("sk-or-") and "openrouter" not in key.lower():
            try:
                return _call_anthropic(system, user, model_id, key)
            except Exception:
                or_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
                if not or_key:
                    raise
                key = or_key
                model_id = model_id if "/" in model_id else f"anthropic/{model_id}"
                return _call_openai_compat(
                    system, user, model_id,
                    base_url="https://openrouter.ai/api/v1",
                    api_key=key,
                    extra_headers={"HTTP-Referer": "https://lumen.bot", "X-Title": "Lumen"},
                )
        model_id = model_id if "/" in model_id else f"anthropic/{model_id}"
        return _call_openai_compat(
            system, user, model_id,
            base_url="https://openrouter.ai/api/v1",
            api_key=key,
            extra_headers={"HTTP-Referer": "https://lumen.bot", "X-Title": "Lumen"},
        )

    if provider == "openai":
        return _call_openai_compat(
            system, user, model_id,
            base_url=(choice.base_url or "https://api.openai.com/v1"),
            api_key=key,
        )

    if provider == "openrouter":
        return _call_openai_compat(
            system, user, model_id,
            base_url=(choice.base_url or "https://openrouter.ai/api/v1"),
            api_key=key,
            extra_headers={"HTTP-Referer": "https://lumen.bot", "X-Title": "Lumen"},
        )

    if provider == "deepseek":
        # Official: https://api.deepseek.com + /v1/chat/completions
        # If only OpenRouter key, route through OpenRouter model id
        has_native = bool((os.getenv("DEEPSEEK_API_KEY") or "").strip())
        if not has_native and (os.getenv("OPENROUTER_API_KEY") or "").strip():
            mid = model_id if "/" in model_id else f"deepseek/{model_id}"
            return _call_openai_compat(
                system, user, mid,
                base_url="https://openrouter.ai/api/v1",
                api_key=(os.getenv("OPENROUTER_API_KEY") or "").strip(),
                extra_headers={"HTTP-Referer": "https://lumen.bot", "X-Title": "Lumen"},
            )
        base = (choice.base_url or "https://api.deepseek.com").rstrip("/")
        if not base.endswith("/v1"):
            base = base + "/v1"
        return _call_openai_compat(system, user, model_id, base_url=base, api_key=key)

    if provider == "foundry":
        endpoint = (choice.base_url or os.getenv("AZURE_FOUNDRY_ENDPOINT") or "").rstrip("/")
        if not endpoint:
            raise RuntimeError("AZURE_FOUNDRY_ENDPOINT missing")
        base = endpoint if endpoint.endswith("/v1") else endpoint + "/v1"
        return _call_openai_compat(system, user, model_id or "model-router", base_url=base, api_key=key)

    raise RuntimeError(f"unsupported_catalog_provider:{provider}")



def _invoke_choice(choice: ModelChoice, system: str, user: str) -> str:
    """Single dispatch: every provider ModelChoice can run goes through here."""
    provider = (choice.provider or "").strip()
    if provider in {"openai", "openrouter", "deepseek", "foundry", "anthropic"}:
        return _dispatch_catalog_provider(provider, system, user, choice)
    if provider == "gemini":
        return _call_gemini(system, user, choice.model_id)
    if provider == "groq":
        return _call_groq(system, user, choice.model_id)
    if provider == "qwen":
        return _call_qwen(system, user, choice.model_id, choice.base_url)
    if provider == "xai":
        return _call_xai(system, user, choice.model_id)
    if provider == "ollama":
        return _call_ollama(system, user, choice.model_id, choice.base_url)
    if provider in {"llamacpp", "openai_compat", "tablet"}:
        return _call_llamacpp(system, user, choice.model_id, choice.base_url)
    raise RuntimeError(f"unsupported_provider:{provider or 'none'}")


def _failover_choice(failed: ModelChoice, *, task: str = "build") -> ModelChoice | None:
    """Next available catalog model excluding the failed provider."""
    try:
        from lumen.engine.services.llm.model_catalog import available_models
        from .model_router import _task_to_role, _choice_from_catalog_model

        role = _task_to_role(task)
        pool = available_models(role=role) or available_models()
        candidates = [m for m in pool if m.provider != (failed.provider or "")]
        if not candidates:
            return None
        if role in {"plan", "critique", "reason"}:
            candidates = sorted(candidates, key=lambda m: (-int(m.strength), int(m.cost_tier)))
        else:
            candidates = sorted(candidates, key=lambda m: (int(m.cost_tier), -int(m.strength)))
        return _choice_from_catalog_model(candidates[0])
    except Exception:
        logger.debug("failover_choice failed", exc_info=True)
        return None



def decide(
    messages: list[dict[str, Any]],
    *,
    choice: ModelChoice | None = None,
    history_keep: int | None = None,
    prompt_max_chars: int | None = None,
) -> dict[str, Any]:
    """One reasoning step with smart retries (parse fail / transient HTTP).

    history_keep / prompt_max_chars: optional Loop Governor caps (first-class).
    """
    choice = choice or select_model(task="build")
    system, user = _system_and_user(
        messages, history_keep=history_keep, prompt_max_chars=prompt_max_chars
    )
    if not system:
        system = "You are an autonomous coding agent building a software project."

    # Phase A: optional decision cache for identical prompts (cost control)
    cache_on = (os.getenv("CLINE_DECISION_CACHE") or "1").strip().lower() in {"1", "true", "yes", "on"}
    cache_payload = {
        "provider": choice.provider,
        "model": choice.model_id,
        "system": system[:4000],
        "user": user[:6000],
    }
    if cache_on:
        try:
            from .model_router import cache_get, cache_set
            hit = cache_get("decide", cache_payload, ttl_sec=int(os.getenv("CLINE_DECISION_CACHE_TTL") or "1800"))
            if isinstance(hit, dict) and (hit.get("parse_ok") or hit.get("tool") or hit.get("finish")):
                hit = dict(hit)
                hit["cache_hit"] = True
                return hit
        except Exception:
            pass

    try:
        # Default 2 retries (was 3) — weakness #2 fix: fewer retries means a
        # slow/hung provider fails faster. The agent_loop time budget is the
        # hard backstop regardless.
        max_attempts = max(1, min(4, int(os.getenv("CLINE_LLM_RETRIES") or "2")))
    except ValueError:
        max_attempts = 2

    provider = choice.provider
    last_error = ""
    raw = ""

    for attempt in range(1, max_attempts + 1):
        try:
            raw = _invoke_choice(choice, system, user)
            provider = choice.provider
        except Exception as exc:
            last_error = f"{type(exc).__name__}:{exc}"
            logger.warning(
                "agent_brain attempt %s/%s provider=%s failed: %s",
                attempt,
                max_attempts,
                choice.provider,
                exc,
            )
            alt = _failover_choice(choice, task="build")
            if alt is not None and attempt < max_attempts:
                logger.info(
                    "failover %s → %s/%s",
                    choice.provider,
                    alt.provider,
                    alt.model_id,
                )
                choice = alt
                provider = alt.provider
                # brief backoff on rate limits
                if any(tok in last_error.lower() for tok in ("429", "503", "502", "timeout")):
                    time.sleep(min(4.0, 1.5 * attempt))
                continue
            if attempt < max_attempts and any(
                tok in last_error.lower()
                for tok in ("timeout", "429", "503", "502", "connection", "temporar")
            ):
                time.sleep(min(6.0, 2.0 * attempt))
                continue
            if attempt < max_attempts:
                continue
            return {
                "thought": "",
                "tool": None,
                "args": {},
                "params": {},
                "finish": False,
                "summary": "",
                "reply": "",
                "raw": "",
                "parse_ok": False,
                "error": last_error,
                "provider": choice.provider,
                "model_id": choice.model_id,
                "attempts": attempt,
            }

        obj = _extract_json_object(raw)
        decision = _normalize_decision(obj, raw)
        decision["provider"] = choice.provider
        decision["model_id"] = choice.model_id
        decision["attempts"] = attempt
        try:
            decision["usage"] = get_last_call_usage()
        except Exception:
            decision["usage"] = {}
        if decision.get("parse_ok") or decision.get("tool"):
            if cache_on:
                try:
                    from .model_router import cache_set
                    cache_set(
                        "decide",
                        cache_payload,
                        {k: decision[k] for k in decision if k != "usage"},
                    )
                except Exception:
                    pass
            return decision

        # Invalid JSON — retry; on last attempts switch provider via catalog
        logger.info(
            "agent_brain parse fail attempt %s provider=%s — retry",
            attempt,
            choice.provider,
        )
        last_error = "parse_fail"
        if attempt < max_attempts:
            alt = _failover_choice(choice, task="build")
            if alt is not None:
                logger.info(
                    "parse-fail failover %s → %s/%s",
                    choice.provider,
                    alt.provider,
                    alt.model_id,
                )
                choice = alt
            user = user + "\n\nIMPORTANT: Previous reply was invalid JSON. Output ONLY one JSON object."

    decision = _normalize_decision(_extract_json_object(raw), raw)
    decision["provider"] = choice.provider
    decision["model_id"] = choice.model_id
    decision["attempts"] = max_attempts
    if not decision.get("parse_ok") and not decision.get("tool"):
        decision["error"] = None
        decision["soft_parse_fail"] = True
    return decision


    return decision



__all__ = ["ALLOWED_TOOLS", "decide"]
