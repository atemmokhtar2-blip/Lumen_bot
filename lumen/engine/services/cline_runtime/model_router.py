"""Model provider selection for Cline agent.

Keys never collide:
  GROQ_API_KEY   → Groq
  QWEN_API_KEY / DASHSCOPE_API_KEY → Qwen DashScope intl (sk-ws-)
  GOOGLE_API_KEY / GEMINI_API_KEY → Gemini
  XAI_API_KEY    → xAI (optional)
  OLLAMA_HOST    → local

CLINE_LLM_PROVIDER / ENGINE_LLM_PROVIDER: groq | gemini | xai | ollama | llamacpp | openai_compat | auto
Default auto order: xai (Grok) → groq → qwen → llamacpp → gemini → ollama

Tablet / llama.cpp server:
  LLAMACPP_BASE_URL=https://xxx.trycloudflare.com/v1
  LLAMACPP_MODEL=qwen
  CLINE_LLM_PROVIDER=llamacpp
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
import hashlib
import json
import threading
import time


@dataclass
class ModelChoice:
    provider: str  # gemini | xai | groq | ollama | none
    model_id: str
    api_key_env: str
    base_url: str | None = None

    def key_present(self) -> bool:
        if self.provider in {"ollama", "llamacpp", "openai_compat"}:
            if self.provider == "ollama":
                return bool((os.getenv("OLLAMA_HOST") or "").strip())
            # llama.cpp / OpenAI-compatible HTTP (tablet tunnel, local server)
            return bool(
                (self.base_url or os.getenv("LLAMACPP_BASE_URL") or os.getenv("OPENAI_COMPAT_BASE_URL") or "").strip()
            )
        if self.provider == "gemini":
            try:
                from lumen.engine.services.llm.key_pool import gemini_keys
                return bool(gemini_keys())
            except Exception:
                return bool(
                    (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
                )
        if self.provider == "groq":
            try:
                from lumen.engine.services.llm.key_pool import groq_keys
                return bool(groq_keys())
            except Exception:
                return bool((os.getenv("GROQ_API_KEY") or "").strip())
        if self.provider == "qwen":
            try:
                from lumen.engine.services.llm.key_pool import qwen_keys
                return bool(qwen_keys())
            except Exception:
                return bool(
                    (os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY") or "").strip()
                )
        return bool((os.getenv(self.api_key_env) or "").strip())


def _forced_provider() -> str:
    for name in ("CLINE_LLM_PROVIDER", "ENGINE_LLM_PROVIDER"):
        v = (os.getenv(name) or "").strip().lower()
        if v:
            return v
    return ""



# ── Phase A: task difficulty + result cache ──────────────────────────

_CACHE_LOCK = threading.Lock()
_RESULT_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_MAX = 256


def estimate_task_difficulty(
    *,
    task: str = "build",
    goal: str = "",
    features: list | None = None,
    findings_count: int = 0,
    file_count: int = 0,
) -> dict[str, Any]:
    """Heuristic difficulty for model routing (no external services).

    Returns score 0.0..1.0 and band: easy | medium | hard.
    """
    task_l = (task or "build").strip().lower()
    goal_s = (goal or "").strip()
    feats = list(features or [])
    score = 0.15
    if task_l in {"plan", "planner", "architect"}:
        score += 0.25
    if task_l in {"critique", "critic", "review", "qa"}:
        score += 0.2
    if task_l in {"repair", "fix"}:
        score += 0.3
    score += min(0.25, len(goal_s) / 4000.0)
    score += min(0.2, len(feats) * 0.03)
    score += min(0.2, max(0, findings_count) * 0.04)
    score += min(0.15, max(0, file_count) * 0.01)
    # Arabic + multi-feature custom bots tend harder
    if any(ord(c) > 0x600 for c in goal_s[:200]):
        score += 0.05
    score = max(0.0, min(1.0, score))
    if score < 0.35:
        band = "easy"
    elif score < 0.65:
        band = "medium"
    else:
        band = "hard"
    return {"score": round(score, 3), "band": band, "task": task_l}


def _cache_key(namespace: str, payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(f"{namespace}:{raw}".encode("utf-8")).hexdigest()


def cache_get(namespace: str, payload: dict[str, Any], *, ttl_sec: int = 3600) -> Any | None:
    """Return cached result if fresh; else None."""
    key = _cache_key(namespace, payload)
    with _CACHE_LOCK:
        entry = _RESULT_CACHE.get(key)
        if not entry:
            return None
        if time.time() - float(entry.get("ts") or 0) > max(30, ttl_sec):
            _RESULT_CACHE.pop(key, None)
            return None
        entry["hits"] = int(entry.get("hits") or 0) + 1
        return entry.get("value")


def cache_set(namespace: str, payload: dict[str, Any], value: Any) -> str:
    """Store result for repeated identical tasks (Phase A cost control)."""
    key = _cache_key(namespace, payload)
    with _CACHE_LOCK:
        if len(_RESULT_CACHE) >= _CACHE_MAX:
            # drop oldest
            oldest = sorted(_RESULT_CACHE.items(), key=lambda kv: float(kv[1].get("ts") or 0))
            for k, _ in oldest[: max(1, _CACHE_MAX // 10)]:
                _RESULT_CACHE.pop(k, None)
        _RESULT_CACHE[key] = {"ts": time.time(), "value": value, "hits": 0}
    return key


def cache_stats() -> dict[str, Any]:
    with _CACHE_LOCK:
        return {
            "entries": len(_RESULT_CACHE),
            "max": _CACHE_MAX,
            "hits": sum(int(v.get("hits") or 0) for v in _RESULT_CACHE.values()),
        }


def select_model(*, task: str = "build") -> ModelChoice:

    forced = _forced_provider()
    table = {
        "gemini": ModelChoice(
            "gemini",
            (os.getenv("GEMINI_MODEL") or "gemini-3.6-flash").strip(),
            "GOOGLE_API_KEY",
        ),
        "google": ModelChoice(
            "gemini",
            (os.getenv("GEMINI_MODEL") or "gemini-3.6-flash").strip(),
            "GOOGLE_API_KEY",
        ),
        "xai": ModelChoice(
            "xai",
            (os.getenv("XAI_MODEL") or "grok-2-latest").strip(),
            "XAI_API_KEY",
        ),
        "grok": ModelChoice(
            "xai",
            (os.getenv("XAI_MODEL") or "grok-2-latest").strip(),
            "XAI_API_KEY",
        ),
        "groq": ModelChoice(
            "groq",
            (os.getenv("GROQ_MODEL") or "qwen/qwen3.6-27b").strip(),
            "GROQ_API_KEY",
            base_url="https://api.groq.com/openai/v1",
        ),
        "ollama": ModelChoice(
            "ollama",
            (os.getenv("OLLAMA_MODEL") or "llama3.2").strip(),
            "OLLAMA_HOST",
            base_url=(os.getenv("OLLAMA_HOST") or "http://127.0.0.1:11434").strip(),
        ),
        "qwen": ModelChoice(
            "qwen",
            (os.getenv("QWEN_MODEL") or os.getenv("DASHSCOPE_MODEL") or "qwen-plus").strip(),
            "QWEN_API_KEY",
            base_url=(
                os.getenv("QWEN_BASE_URL")
                or os.getenv("DASHSCOPE_BASE_URL")
                or "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
            ).strip(),
        ),
        "dashscope": ModelChoice(
            "qwen",
            (os.getenv("QWEN_MODEL") or "qwen-plus").strip(),
            "QWEN_API_KEY",
            base_url=(
                os.getenv("QWEN_BASE_URL")
                or "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
            ).strip(),
        ),
        # Tablet / llama-server (OpenAI-compatible /v1/chat/completions)
        "llamacpp": ModelChoice(
            "llamacpp",
            (os.getenv("LLAMACPP_MODEL") or os.getenv("OPENAI_COMPAT_MODEL") or "qwen").strip(),
            "LLAMACPP_BASE_URL",
            base_url=(
                os.getenv("LLAMACPP_BASE_URL")
                or os.getenv("OPENAI_COMPAT_BASE_URL")
                or ""
            ).strip().rstrip("/"),
        ),
        "openai_compat": ModelChoice(
            "llamacpp",
            (os.getenv("LLAMACPP_MODEL") or os.getenv("OPENAI_COMPAT_MODEL") or "qwen").strip(),
            "LLAMACPP_BASE_URL",
            base_url=(
                os.getenv("LLAMACPP_BASE_URL")
                or os.getenv("OPENAI_COMPAT_BASE_URL")
                or ""
            ).strip().rstrip("/"),
        ),
        "tablet": ModelChoice(
            "llamacpp",
            (os.getenv("LLAMACPP_MODEL") or "qwen").strip(),
            "LLAMACPP_BASE_URL",
            base_url=(os.getenv("LLAMACPP_BASE_URL") or "").strip().rstrip("/"),
        ),
    }
    if forced in table:
        choice = table[forced]
        return _apply_task_model_override(choice, task)

    # Phase A: task-aware preference order
    # plan/critique → stronger models first; build → cheaper/faster first
    task_l = (task or "build").strip().lower()
    if task_l in {"plan", "planner", "architect"}:
        order = ("xai", "gemini", "qwen", "groq", "llamacpp", "ollama")
    elif task_l in {"critique", "critic", "review", "qa"}:
        order = ("xai", "gemini", "qwen", "groq", "llamacpp", "ollama")
    else:
        # build / worker — Grok (xAI) first for speed, then Groq high-RPM
        order = ("xai", "groq", "qwen", "llamacpp", "gemini", "ollama")

    for name in order:
        choice = table.get(name)
        if choice is not None and choice.key_present():
            return _apply_task_model_override(choice, task_l)
    return ModelChoice("none", "", "")


def _apply_task_model_override(choice: ModelChoice, task: str) -> ModelChoice:
    """Optional per-task model id via env (Planner strong / Worker cheap)."""
    task_l = (task or "build").strip().lower()
    env_map = {
        "plan": "CLINE_MODEL_PLAN",
        "planner": "CLINE_MODEL_PLAN",
        "architect": "CLINE_MODEL_PLAN",
        "build": "CLINE_MODEL_BUILD",
        "worker": "CLINE_MODEL_BUILD",
        "critique": "CLINE_MODEL_CRITIQUE",
        "critic": "CLINE_MODEL_CRITIQUE",
        "review": "CLINE_MODEL_CRITIQUE",
        "qa": "CLINE_MODEL_CRITIQUE",
    }
    env_name = env_map.get(task_l)
    if not env_name:
        return choice
    override = (os.getenv(env_name) or "").strip()
    if not override:
        return choice
    return ModelChoice(
        choice.provider,
        override,
        choice.api_key_env,
        base_url=choice.base_url,
    )




def select_model_for_goal(
    *,
    task: str = "build",
    goal: str = "",
    features: list | None = None,
    findings_count: int = 0,
    file_count: int = 0,
) -> tuple[ModelChoice, dict[str, Any]]:
    """Select model using task difficulty band (hard → stronger providers first)."""
    diff = estimate_task_difficulty(
        task=task,
        goal=goal,
        features=features,
        findings_count=findings_count,
        file_count=file_count,
    )
    # For hard repair/critique, force plan-like order by mapping task
    task_eff = task
    if diff["band"] == "hard" and (task or "").lower() in {"build", "worker"}:
        task_eff = "plan"  # stronger order
    choice = select_model(task=task_eff)
    return choice, diff


def describe_runtime() -> dict[str, Any]:
    choice = select_model(task="build")
    return {
        "provider": choice.provider,
        "model_id": choice.model_id,
        "key_present": choice.key_present() if choice.provider != "none" else False,
        "base_url": choice.base_url,
        "forced": _forced_provider() or "auto",
        "task_orders": {
            "plan": "gemini>xai>qwen>groq>llamacpp>ollama",
            "build": "llamacpp>qwen>groq>gemini>xai>ollama",
            "critique": "gemini>xai>qwen>groq>llamacpp>ollama",
        },
        "cache": cache_stats(),
        "difficulty_sample": estimate_task_difficulty(task="build", goal="sample"),
    }


__all__ = [
    "ModelChoice",
    "describe_runtime",
    "select_model",
    "select_model_for_goal",
    "estimate_task_difficulty",
    "cache_get",
    "cache_set",
    "cache_stats",
]
