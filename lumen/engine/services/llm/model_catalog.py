"""Unified model catalog — single source of truth for agent LLM selection.

Phase 1: registry only. Phase 2+ wires providers in agent_brain.
Routing engines (Foundry / local allocator) consume this catalog — not ad-hoc env strings.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

ApiStyle = Literal["openai_compat", "gemini", "anthropic"]
Role = Literal["plan", "build", "critique", "reason", "fast"]


@dataclass(frozen=True)
class CatalogModel:
    """One selectable model in the agent pool."""

    id: str  # stable catalog id
    label: str
    provider: str  # groq | gemini | openai | deepseek | anthropic | openrouter | xai | qwen | ollama | llamacpp
    model_id: str  # provider API model name
    api_style: ApiStyle
    base_url: str | None
    api_key_env: str  # primary env var for key presence
    roles: tuple[Role, ...]
    cost_tier: int  # 1=cheap … 5=expensive
    strength: int  # 1=weak … 5=strong
    notes: str = ""

    def key_env_candidates(self) -> tuple[str, ...]:
        """Env vars that may hold a usable key for this model."""
        primary = self.api_key_env
        extras: dict[str, tuple[str, ...]] = {
            "GOOGLE_API_KEY": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
            "GROQ_API_KEY": ("GROQ_API_KEY",),
            "OPENAI_API_KEY": ("OPENAI_API_KEY",),
            "DEEPSEEK_API_KEY": ("DEEPSEEK_API_KEY", "OPENROUTER_API_KEY"),
            "ANTHROPIC_API_KEY": ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"),
            "OPENROUTER_API_KEY": ("OPENROUTER_API_KEY",),
            "XAI_API_KEY": ("XAI_API_KEY",),
            "QWEN_API_KEY": ("QWEN_API_KEY", "DASHSCOPE_API_KEY"),
            "OLLAMA_HOST": ("OLLAMA_HOST",),
            "LLAMACPP_BASE_URL": ("LLAMACPP_BASE_URL", "OPENAI_COMPAT_BASE_URL"),
            "AZURE_FOUNDRY_KEY": ("AZURE_FOUNDRY_KEY", "AZURE_OPENAI_API_KEY"),
        }
        return extras.get(primary, (primary,))

    def key_present(self) -> bool:
        if self.provider in {"ollama", "llamacpp"}:
            return bool(
                (self.base_url or os.getenv("OLLAMA_HOST") or os.getenv("LLAMACPP_BASE_URL") or "").strip()
            )
        for env in self.key_env_candidates():
            if (os.getenv(env) or "").strip():
                return True
        return False


# ── Canonical agent models (user-requested set + existing working providers) ──
CATALOG: tuple[CatalogModel, ...] = (
    CatalogModel(
        id="groq-deepseek-v4-flash",
        label="DeepSeek V4 Flash (Groq)",
        provider="groq",
        model_id=(os.getenv("GROQ_DEEPSEEK_MODEL") or "deepseek-r1-distill-llama-70b").strip(),
        api_style="openai_compat",
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY",
        roles=("build", "fast", "reason"),
        cost_tier=1,
        strength=3,
        notes="Fast agent turns via Groq; override GROQ_DEEPSEEK_MODEL when V4 Flash id is published",
    ),
    CatalogModel(
        id="gemini-2.5-flash-lite",
        label="Gemini 2.5 Flash Lite",
        provider="gemini",
        model_id=(os.getenv("GEMINI_FLASH_LITE_MODEL") or "gemini-2.5-flash-lite").strip(),
        api_style="gemini",
        base_url=None,
        api_key_env="GOOGLE_API_KEY",
        roles=("build", "fast"),
        cost_tier=1,
        strength=3,
    ),
    CatalogModel(
        id="gemini-2.5-pro",
        label="Gemini 2.5 Pro",
        provider="gemini",
        model_id=(os.getenv("GEMINI_PRO_MODEL") or "gemini-2.5-pro").strip(),
        api_style="gemini",
        base_url=None,
        api_key_env="GOOGLE_API_KEY",
        roles=("plan", "critique", "reason"),
        cost_tier=4,
        strength=5,
    ),
    CatalogModel(
        id="openai-gpt-4o-mini",
        label="GPT-4o-mini",
        provider="openai",
        model_id=(os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip(),
        api_style="openai_compat",
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        roles=("build", "fast", "plan"),
        cost_tier=2,
        strength=3,
    ),
    CatalogModel(
        id="deepseek-v3",
        label="DeepSeek V3",
        provider="deepseek",
        model_id=(os.getenv("DEEPSEEK_MODEL") or "deepseek-chat").strip(),
        api_style="openai_compat",
        base_url=(os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").strip(),
        api_key_env="DEEPSEEK_API_KEY",
        roles=("plan", "build", "reason"),
        cost_tier=2,
        strength=4,
    ),
    CatalogModel(
        id="claude-3-haiku",
        label="Claude 3 Haiku",
        provider="anthropic",
        model_id=(os.getenv("ANTHROPIC_MODEL") or "claude-3-haiku-20240307").strip(),
        api_style="anthropic",
        base_url="https://api.anthropic.com",
        api_key_env="ANTHROPIC_API_KEY",
        roles=("critique", "fast", "build"),
        cost_tier=2,
        strength=3,
    ),
    CatalogModel(
        id="openrouter-auto",
        label="OpenRouter (passthrough)",
        provider="openrouter",
        model_id=(os.getenv("OPENROUTER_MODEL") or "openrouter/auto").strip(),
        api_style="openai_compat",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        roles=("plan", "build", "critique", "reason", "fast"),
        cost_tier=3,
        strength=4,
        notes="Use OPENROUTER_MODEL to pin any OpenRouter model id",
    ),
    # Foundry model-router entry (phase 3 selection engine)
    CatalogModel(
        id="foundry-model-router",
        label="Microsoft Foundry Model Router",
        provider="foundry",
        model_id=(os.getenv("AZURE_FOUNDRY_MODEL") or "model-router").strip(),
        api_style="openai_compat",
        base_url=(os.getenv("AZURE_FOUNDRY_ENDPOINT") or "").strip() or None,
        api_key_env="AZURE_FOUNDRY_KEY",
        roles=("plan", "build", "critique", "reason", "fast"),
        cost_tier=3,
        strength=5,
        notes="Production intelligent router when AZURE_FOUNDRY_ENDPOINT is set",
    ),
)


def get_model(catalog_id: str) -> CatalogModel | None:
    cid = (catalog_id or "").strip().lower()
    for m in CATALOG:
        if m.id == cid:
            return m
    return None


def models_for_role(role: Role) -> list[CatalogModel]:
    return [m for m in CATALOG if role in m.roles]


def available_models(*, role: Role | None = None) -> list[CatalogModel]:
    pool = models_for_role(role) if role else list(CATALOG)
    return [m for m in pool if m.key_present()]


def catalog_snapshot() -> list[dict]:
    """Safe status (no secrets)."""
    rows = []
    for m in CATALOG:
        rows.append({
            "id": m.id,
            "label": m.label,
            "provider": m.provider,
            "model_id": m.model_id,
            "roles": list(m.roles),
            "cost_tier": m.cost_tier,
            "strength": m.strength,
            "key_present": m.key_present(),
        })
    return rows


__all__ = [
    "CatalogModel",
    "CATALOG",
    "get_model",
    "models_for_role",
    "available_models",
    "catalog_snapshot",
]
