"""Model provider selection for Cline agent.

Keys never collide:
  GROQ_API_KEY   → Groq
  QWEN_API_KEY / DASHSCOPE_API_KEY → Qwen DashScope intl (sk-ws-)
  GOOGLE_API_KEY / GEMINI_API_KEY → Gemini
  XAI_API_KEY    → xAI (optional)
  OLLAMA_HOST    → local

CLINE_LLM_PROVIDER / ENGINE_LLM_PROVIDER: groq | gemini | xai | ollama | llamacpp | openai_compat | auto
Default auto order: llamacpp → qwen → groq → gemini → xai → ollama

Tablet / llama.cpp server:
  LLAMACPP_BASE_URL=https://xxx.trycloudflare.com/v1
  LLAMACPP_MODEL=qwen
  CLINE_LLM_PROVIDER=llamacpp
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


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


def select_model(*, task: str = "build") -> ModelChoice:
    forced = _forced_provider()
    table = {
        "gemini": ModelChoice(
            "gemini",
            (os.getenv("GEMINI_MODEL") or "gemini-2.0-flash").strip(),
            "GOOGLE_API_KEY",
        ),
        "google": ModelChoice(
            "gemini",
            (os.getenv("GEMINI_MODEL") or "gemini-2.0-flash").strip(),
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
        order = ("gemini", "xai", "qwen", "groq", "llamacpp", "ollama")
    elif task_l in {"critique", "critic", "review", "qa"}:
        order = ("gemini", "xai", "qwen", "groq", "llamacpp", "ollama")
    else:
        # build / worker — prefer fast local or high-RPM pools
        order = ("llamacpp", "qwen", "groq", "gemini", "xai", "ollama")

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
    }


__all__ = ["ModelChoice", "describe_runtime", "select_model"]
