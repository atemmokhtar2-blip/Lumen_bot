"""R2-Reasoner-style local allocator (decompose + allocate).

Not a research-code import — a production-thin version of the idea:
  1) Decompose the current agent step into a kind: plan | code | repair | critique
  2) Score catalog models for that kind (keys present only)
  3) Pick the best score

Foundry Model Router remains production primary when configured; this module
runs when Foundry is unavailable or CLINE_ROUTER=local|catalog.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Literal

logger = logging.getLogger(__name__)

StepKind = Literal["plan", "code", "repair", "critique"]


@dataclass(frozen=True)
class AllocateResult:
    catalog_id: str
    provider: str
    model_id: str
    api_key_env: str
    base_url: str | None
    step_kind: StepKind
    score: float
    reasons: tuple[str, ...]
    difficulty_signal: dict[str, Any]


def decompose_step(
    *,
    task: str = "build",
    goal: str = "",
    features: list | None = None,
    findings_count: int = 0,
    file_count: int = 0,
) -> StepKind:
    """Light decomposer: task + goal + size → step kind."""
    task_l = (task or "build").strip().lower()
    if task_l in {"plan", "planner", "architect"}:
        return "plan"
    if task_l in {"critique", "critic", "review", "qa"}:
        return "critique"
    if task_l in {"repair", "fix"}:
        return "repair"

    g = (goal or "").lower()
    # Explicit cues in the goal text
    if re.search(r"\b(critique|review|qa|audit|افحص|راجع)\b", g):
        return "critique"
    if re.search(r"\b(repair|fix|bug|error|كسر|أصلح|صلح)\b", g) or findings_count >= 3:
        return "repair"
    if re.search(r"\b(architect|design|plan|خط[ةه]|صم[مم])\b", g) and file_count == 0:
        return "plan"
    if findings_count >= 1:
        return "repair"
    return "code"


def _difficulty_signal(
    *,
    step_kind: StepKind,
    goal: str,
    features: list | None,
    findings_count: int,
    file_count: int,
) -> dict[str, Any]:
    """Optional signal only — never the final model decision by itself."""
    score = 0
    reasons: list[str] = []
    n_feat = len(features or [])
    if step_kind in {"plan", "critique"}:
        score += 2
        reasons.append(f"kind={step_kind}")
    if findings_count >= 5:
        score += 3
        reasons.append(f"findings={findings_count}")
    elif findings_count >= 1:
        score += 1
        reasons.append(f"findings={findings_count}")
    if file_count >= 40:
        score += 2
        reasons.append(f"files={file_count}")
    elif file_count >= 15:
        score += 1
        reasons.append(f"files={file_count}")
    if n_feat >= 12:
        score += 2
        reasons.append(f"features={n_feat}")
    if len(goal or "") > 1200:
        score += 1
        reasons.append("long_goal")
    if score >= 5:
        band = "hard"
    elif score >= 2:
        band = "medium"
    else:
        band = "easy"
    return {"score": score, "band": band, "reasons": reasons, "step_kind": step_kind}


# Preferred catalog ids per step kind (order = preference within score ties)
_KIND_PREFER: dict[StepKind, tuple[str, ...]] = {
    "plan": (
        "gemini-2.5-pro",
        "deepseek-v3",
        "openrouter-auto",
        "openai-gpt-4o-mini",
        "deepseek-v4-flash",
    ),
    "critique": (
        "claude-3-haiku",
        "gemini-2.5-pro",
        "deepseek-v3",
        "openrouter-auto",
        "openai-gpt-4o-mini",
    ),
    "repair": (
        "deepseek-v3",
        "gemini-2.5-pro",
        "deepseek-v4-flash",
        "openai-gpt-4o-mini",
        "groq-fast",
    ),
    "code": (
        "deepseek-v4-flash",
        "gemini-2.5-flash-lite",
        "groq-fast",
        "openai-gpt-4o-mini",
        "deepseek-v3",
        "openrouter-auto",
    ),
}


def _score_model(m, step_kind: StepKind, signal: dict[str, Any]) -> tuple[float, list[str]]:
    """Higher is better. Mix preference rank, strength, cost, difficulty band."""
    reasons: list[str] = []
    prefer = _KIND_PREFER.get(step_kind) or ()
    if m.id in prefer:
        rank = prefer.index(m.id)
        # first prefer → +50, then -3 per step
        pref_score = 50.0 - 3.0 * rank
        reasons.append(f"prefer_rank={rank}")
    else:
        # not in prefer list — still usable via roles
        pref_score = 5.0
        reasons.append("not_in_prefer")

    # strength 1-5 → 0-20
    strength_s = float(m.strength) * 4.0
    reasons.append(f"strength={m.strength}")

    # cost: lower cost_tier better for code/easy; for plan/hard prefer quality
    band = str(signal.get("band") or "easy")
    if step_kind in {"plan", "critique"} or band == "hard":
        cost_s = float(6 - int(m.cost_tier)) * 2.0  # prefer stronger even if costlier
    else:
        cost_s = float(6 - int(m.cost_tier)) * 4.0  # prefer cheap for fast code
    reasons.append(f"cost_tier={m.cost_tier}")

    # role match
    role_map = {"plan": "plan", "critique": "critique", "repair": "reason", "code": "build"}
    need = role_map.get(step_kind, "build")
    role_s = 10.0 if need in (m.roles or ()) else 0.0
    if role_s:
        reasons.append(f"role={need}")

    total = pref_score + strength_s + cost_s + role_s
    return total, reasons


def allocate(
    *,
    task: str = "build",
    goal: str = "",
    features: list | None = None,
    findings_count: int = 0,
    file_count: int = 0,
) -> AllocateResult | None:
    """Pick best available catalog model for this step."""
    from lumen.engine.services.llm.model_catalog import available_models, CATALOG

    step_kind = decompose_step(
        task=task,
        goal=goal,
        features=features,
        findings_count=findings_count,
        file_count=file_count,
    )
    signal = _difficulty_signal(
        step_kind=step_kind,
        goal=goal,
        features=features,
        findings_count=findings_count,
        file_count=file_count,
    )

    pool = [m for m in available_models() if m.key_present()]
    if not pool:
        # nothing with keys
        return None

    ranked: list[tuple[float, Any, tuple[str, ...]]] = []
    for m in pool:
        score, reasons = _score_model(m, step_kind, signal)
        ranked.append((score, m, tuple(reasons)))
    ranked.sort(key=lambda x: -x[0])
    best_score, best, best_reasons = ranked[0]
    logger.info(
        "r2_allocator kind=%s band=%s pick=%s/%s score=%.1f",
        step_kind,
        signal.get("band"),
        best.provider,
        best.model_id,
        best_score,
    )
    return AllocateResult(
        catalog_id=best.id,
        provider=best.provider,
        model_id=best.model_id,
        api_key_env=best.api_key_env,
        base_url=best.base_url,
        step_kind=step_kind,
        score=best_score,
        reasons=best_reasons,
        difficulty_signal=signal,
    )


def router_mode() -> str:
    """CLINE_ROUTER: foundry | local | auto (default auto)."""
    return (os.getenv("CLINE_ROUTER") or "auto").strip().lower()


__all__ = [
    "StepKind",
    "AllocateResult",
    "decompose_step",
    "allocate",
    "router_mode",
]
