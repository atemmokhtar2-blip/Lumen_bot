"""Model provider selection for Cline agent.

Keys never collide:
  GROQ_API_KEY   → Groq
  QWEN_API_KEY / DASHSCOPE_API_KEY → Qwen DashScope intl (sk-ws-)
  GOOGLE_API_KEY / GEMINI_API_KEY → Gemini
  XAI_API_KEY    → xAI (optional)
  OLLAMA_HOST    → local

CLINE_LLM_PROVIDER / ENGINE_LLM_PROVIDER: groq | gemini | xai | ollama | llamacpp | openai_compat | auto
Default auto order: gemini → groq → qwen → xai → llamacpp → ollama

Tablet / llama.cpp server:
  LLAMACPP_BASE_URL=https://xxx.trycloudflare.com/v1
  LLAMACPP_MODEL=qwen
  CLINE_LLM_PROVIDER=llamacpp
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)
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
    catalog_id: str = ""  # Phase-1 SoT link back to model_catalog

    def key_present(self) -> bool:
        if self.provider in {"ollama", "llamacpp", "openai_compat"}:
            if self.provider == "ollama":
                return bool((os.getenv("OLLAMA_HOST") or "").strip())
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
        if self.provider == "openai":
            return bool((os.getenv("OPENAI_API_KEY") or "").strip())
        if self.provider == "openrouter":
            return bool((os.getenv("OPENROUTER_API_KEY") or "").strip())
        if self.provider == "deepseek":
            return bool(
                (os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENROUTER_API_KEY") or "").strip()
            )
        if self.provider == "anthropic":
            return bool(
                (os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENROUTER_API_KEY") or "").strip()
            )
        if self.provider == "foundry":
            return bool(
                (os.getenv("AZURE_FOUNDRY_KEY") or os.getenv("AZURE_OPENAI_API_KEY") or "").strip()
                and (self.base_url or os.getenv("AZURE_FOUNDRY_ENDPOINT") or "").strip()
            )
        if self.provider == "xai":
            return bool((os.getenv("XAI_API_KEY") or "").strip())
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


def _task_to_role(task: str) -> str:
    task_l = (task or "build").strip().lower()
    if task_l in {"plan", "planner", "architect"}:
        return "plan"
    if task_l in {"critique", "critic", "review", "qa"}:
        return "critique"
    if task_l in {"repair", "fix", "reason"}:
        return "reason"
    return "build"


def _choice_from_catalog_model(m) -> ModelChoice:
    """Build ModelChoice from catalog row — always via resolve_dispatch (OpenRouter rewrite)."""
    try:
        disp = m.resolve_dispatch()
    except Exception:
        disp = {
            "provider": m.provider,
            "model_id": m.model_id,
            "base_url": m.base_url or "",
        }
    return ModelChoice(
        disp.get("provider") or m.provider,
        disp.get("model_id") or m.model_id,
        m.api_key_env,
        base_url=(disp.get("base_url") or m.base_url or None) or None,
        catalog_id=getattr(m, "id", "") or "",
    )


def select_model(*, task: str = "build") -> ModelChoice:
    """Production order:

    1. Forced provider (CLINE_LLM_PROVIDER) when set
    2. Microsoft Foundry Model Router when Azure endpoint+key present
    3. Catalog role ranking among remaining providers
    """
    from lumen.engine.services.llm.model_catalog import CATALOG, available_models

    forced = _forced_provider()
    role = _task_to_role(task)

    # Production primary: Foundry when CLINE_ROUTER allows it
    try:
        from lumen.engine.services.llm.r2_allocator import router_mode
        rmode = router_mode()
    except Exception:
        rmode = (os.getenv("CLINE_ROUTER") or "auto").strip().lower()
    use_foundry = rmode in {"auto", "foundry"} and (
        not forced or forced in {"auto", "foundry", "azure", "model-router"}
    )
    if use_foundry:
        try:
            from lumen.engine.services.llm.foundry_router import (
                foundry_configured,
                mode_for_task,
                deployment_for_mode,
                resolve_endpoint,
            )
            if foundry_configured():
                mode = mode_for_task(task)
                deployment = deployment_for_mode(mode)
                return ModelChoice(
                    "foundry",
                    deployment,
                    "AZURE_FOUNDRY_KEY",
                    base_url=resolve_endpoint(),
                )
        except Exception:
            pass

    if forced and forced not in {"auto", "none"}:
        # Prefer catalog entries for this provider, role-matched first (Phase-1 SoT)
        matches = [
            m for m in CATALOG
            if m.provider == forced
            or (forced in {"google"} and m.provider == "gemini")
            or (forced in {"grok"} and m.provider == "xai")
        ]
        role_hits = [m for m in matches if role in (m.roles or ())]
        ordered = role_hits + [m for m in matches if m not in role_hits]
        for m in ordered:
            if not m.key_present():
                continue
            choice = _choice_from_catalog_model(m)
            if choice.key_present():
                return _apply_task_model_override(choice, task)
        # Legacy forced providers not in catalog (qwen/ollama/llamacpp)
        legacy = {
            "qwen": ModelChoice(
                "qwen",
                (os.getenv("QWEN_MODEL") or "qwen-plus").strip(),
                "QWEN_API_KEY",
                base_url=(
                    os.getenv("QWEN_BASE_URL")
                    or "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
                ).strip(),
            ),
            "ollama": ModelChoice(
                "ollama",
                (os.getenv("OLLAMA_MODEL") or "llama3.2").strip(),
                "OLLAMA_HOST",
                base_url=(os.getenv("OLLAMA_HOST") or "http://127.0.0.1:11434").strip(),
            ),
            "llamacpp": ModelChoice(
                "llamacpp",
                (os.getenv("LLAMACPP_MODEL") or "qwen").strip(),
                "LLAMACPP_BASE_URL",
                base_url=(os.getenv("LLAMACPP_BASE_URL") or "").strip().rstrip("/"),
            ),
            "xai": ModelChoice(
                "xai",
                (os.getenv("XAI_MODEL") or "grok-2-latest").strip(),
                "XAI_API_KEY",
            ),
        }
        if forced in legacy:
            c = legacy[forced]
            if c.key_present():
                return _apply_task_model_override(c, task)

    pool = available_models(role=role)  # type: ignore[arg-type]
    if not pool:
        pool = available_models()
    if not pool:
        return ModelChoice("none", "", "")

    # Prefer product order from R2 kind list when available, then strength/cost
    prefer_index: dict[str, int] = {}
    try:
        from lumen.engine.services.llm.r2_allocator import _KIND_PREFER, decompose_step
        kind = decompose_step(task=task)
        for i, cid in enumerate(_KIND_PREFER.get(kind, ())):
            prefer_index[cid] = i
    except Exception:
        pass

    def _rank(m):
        pref = prefer_index.get(m.id, 10_000)
        if role in {"plan", "critique", "reason"}:
            return (pref, -int(m.strength), int(m.cost_tier))
        return (pref, int(m.cost_tier), -int(m.strength))

    pool = sorted(pool, key=_rank)
    choice = _choice_from_catalog_model(pool[0])
    return _apply_task_model_override(choice, task)



def _apply_task_model_override(choice: ModelChoice, task: str) -> ModelChoice:
    """Optional per-task override via env — catalog id preferred over raw model_id."""
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
    # Prefer catalog id (e.g. CLINE_MODEL_PLAN=gemini-2.5-pro)
    try:
        from lumen.engine.services.llm.model_catalog import get_model
        m = get_model(override)
        if m is not None and m.key_present():
            return _choice_from_catalog_model(m)
        # match by model_id string inside catalog
        from lumen.engine.services.llm.model_catalog import CATALOG
        for row in CATALOG:
            if row.model_id == override and row.key_present():
                return _choice_from_catalog_model(row)
    except Exception:
        pass
    return ModelChoice(
        choice.provider,
        override,
        choice.api_key_env,
        base_url=choice.base_url,
        catalog_id=choice.catalog_id,
    )




def select_model_for_goal(
    *,
    task: str = "build",
    goal: str = "",
    features: list | None = None,
    findings_count: int = 0,
    file_count: int = 0,
    last_tool: str = "",
    soft_parse_fail: bool = False,
) -> tuple[ModelChoice, dict[str, Any]]:
    """Foundry first (if configured), else R2-style local allocator over catalog.

    ``estimate_task_difficulty`` is only a signal inside the allocator — never
    the sole decision.
    """
    meta: dict[str, Any] = {
        "router": "none",
        "task": task,
    }

    # 1) Foundry primary (production)
    try:
        from lumen.engine.services.llm.r2_allocator import router_mode
        rmode = router_mode()
    except Exception:
        rmode = (os.getenv("CLINE_ROUTER") or "auto").strip().lower()
    meta["cline_router"] = rmode

    forced = _forced_provider()
    if rmode in {"auto", "foundry"} and (not forced or forced in {"auto", "foundry", "azure", "model-router"}):
        try:
            from lumen.engine.services.llm.foundry_router import (
                foundry_configured,
                mode_for_task,
                deployment_for_mode,
                resolve_endpoint,
            )
            if foundry_configured():
                mode = mode_for_task(task)
                deployment = deployment_for_mode(mode)
                choice = ModelChoice(
                    "foundry",
                    deployment,
                    "AZURE_FOUNDRY_KEY",
                    base_url=resolve_endpoint(),
                )
                meta.update({
                    "router": "foundry",
                    "foundry_mode": mode,
                    "foundry_deployment": deployment,
                })
                # difficulty remains optional signal for logging / governor
                try:
                    sig = estimate_task_difficulty(
                        task=task, goal=goal, features=features,
                        findings_count=findings_count, file_count=file_count,
                    )
                    meta["difficulty_signal"] = sig
                    meta["band"] = sig.get("band") or "medium"
                    meta["score"] = sig.get("score")
                except Exception:
                    meta["band"] = "medium"
                return choice, meta
        except Exception as exc:
            meta["foundry_error"] = type(exc).__name__

    # 2) Local R2-style allocator (decompose + score catalog)
    if rmode in {"auto", "local", "catalog", "r2"}:
        try:
            from lumen.engine.services.llm.r2_allocator import allocate
            result = allocate(
                task=task,
                goal=goal,
                features=features,
                findings_count=findings_count,
                file_count=file_count,
                last_tool=last_tool,
                soft_parse_fail=soft_parse_fail,
            )
            if result is not None:
                try:
                    from lumen.engine.services.llm.model_catalog import get_model
                    row = get_model(result.catalog_id) if result.catalog_id else None
                except Exception:
                    row = None
                if row is not None:
                    choice = _choice_from_catalog_model(row)
                else:
                    choice = ModelChoice(
                        result.provider,
                        result.model_id,
                        result.api_key_env,
                        base_url=result.base_url,
                        catalog_id=result.catalog_id or "",
                    )
                choice = _apply_task_model_override(choice, task)
                sig = result.difficulty_signal or {}
                meta.update({
                    "router": "r2_allocator",
                    "step_kind": result.step_kind,
                    "allocator_score": result.score,
                    "reasons": list(result.reasons),
                    "catalog_id": result.catalog_id,
                    "difficulty_signal": sig,
                    # LoopGovernor reads band + score
                    "band": sig.get("band") or "medium",
                    "score": sig.get("score"),
                })
                return choice, meta
        except Exception as exc:
            meta["allocator_error"] = type(exc).__name__
            logger.warning("r2_allocator failed: %s", exc)

    # 3) Legacy fallback — catalog role ranking via select_model
    choice = select_model(task=task)
    try:
        meta["difficulty_signal"] = estimate_task_difficulty(
            task=task, goal=goal, features=features,
            findings_count=findings_count, file_count=file_count,
        )
        meta["band"] = meta["difficulty_signal"].get("band")
    except Exception:
        pass
    meta["router"] = "catalog_fallback"
    return choice, meta


def describe_runtime() -> dict[str, Any]:
    choice = select_model(task="build")
    foundry: dict[str, Any] = {"configured": False}
    try:
        from lumen.engine.services.llm.foundry_router import (
            foundry_configured,
            mode_for_task,
            deployment_for_mode,
            resolve_endpoint,
        )
        if foundry_configured():
            foundry = {
                "configured": True,
                "endpoint": resolve_endpoint(),
                "mode_build": mode_for_task("build"),
                "mode_plan": mode_for_task("plan"),
                "deployment_build": deployment_for_mode(mode_for_task("build")),
                "deployment_plan": deployment_for_mode(mode_for_task("plan")),
                "primary": choice.provider == "foundry",
            }
    except Exception as exc:
        foundry = {"configured": False, "error": type(exc).__name__}
    return {
        "provider": choice.provider,
        "model_id": choice.model_id,
        "key_present": choice.key_present() if choice.provider != "none" else False,
        "base_url": choice.base_url,
        "forced": _forced_provider() or "auto",
        "task_orders": "foundry_primary_then_catalog",
        "foundry": foundry,
        "catalog": __import__("lumen.engine.services.llm.model_catalog", fromlist=["catalog_snapshot"]).catalog_snapshot(),
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
