"""R2-Reasoner-style local allocator — decompose step + score catalog models.

Production path when Microsoft Foundry Model Router is not configured:
  1. Decompose (task, goal, findings, files) → plan | code | repair | critique
  2. Score only models with live keys from model_catalog
  3. Pick max score (preference + strength + cost + role + difficulty signal)

Foundry remains first when CLINE_ROUTER=auto|foundry and Azure is configured.
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


def router_mode() -> str:
    """CLINE_ROUTER: auto | foundry | local | catalog | r2."""
    return (os.getenv("CLINE_ROUTER") or "auto").strip().lower()


def decompose_step(
    *,
    task: str = "build",
    goal: str = "",
    features: list | None = None,
    findings_count: int = 0,
    file_count: int = 0,
    last_tool: str = "",
    soft_parse_fail: bool = False,
) -> StepKind:
    """Map context → step kind for this agent turn."""
    task_l = (task or "build").strip().lower()
    tool_l = (last_tool or "").strip().lower()
    g = (goal or "").lower()

    if task_l in {"plan", "planner", "architect"}:
        return "plan"
    if task_l in {"critique", "critic", "review", "qa"}:
        return "critique"
    if task_l in {"repair", "fix"}:
        return "repair"

    if tool_l in {"read_file", "list_files", "search_files"} and file_count == 0:
        return "plan"
    if tool_l in {"run_command", "apply_patch"} and findings_count > 0:
        return "repair"
    if soft_parse_fail:
        return "repair"

    if re.search(r"\b(critique|review|qa|audit|افحص|راجع|تقييم)\b", g):
        return "critique"
    if findings_count >= 2 or re.search(r"\b(repair|fix|bug|error|كسر|أصلح|صلح|فشل)\b", g):
        return "repair"
    if file_count == 0 and re.search(r"\b(architect|design|plan|خط[ةه]|صم[مم]|مواصفات)\b", g):
        return "plan"
    if findings_count >= 1:
        return "repair"
    return "code"


def difficulty_signal(
    *,
    step_kind: StepKind,
    goal: str,
    features: list | None,
    findings_count: int,
    file_count: int,
) -> dict[str, Any]:
    """Optional signal for scoring + LoopGovernor — never sole routing decision."""
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
    band = "hard" if score >= 5 else "medium" if score >= 2 else "easy"
    return {"score": score, "band": band, "reasons": reasons, "step_kind": step_kind}


# Preference lists match product model lineup (catalog ids)
_KIND_PREFER: dict[StepKind, tuple[str, ...]] = {
    "plan": (
        "gemini-2.5-pro",
        "deepseek-v3",
        "openrouter-auto",
        "openai-gpt-4o-mini",
        "deepseek-v4-flash",
        "claude-3-haiku",
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
        "openrouter-auto",
    ),
    "code": (
        "deepseek-v4-flash",
        "gemini-2.5-flash-lite",
        "groq-fast",
        "openai-gpt-4o-mini",
        "deepseek-v3",
        "openrouter-auto",
        "claude-3-haiku",
    ),
}


def _score_model(m, step_kind: StepKind, signal: dict[str, Any]) -> tuple[float, list[str]]:
    reasons: list[str] = []
    prefer = _KIND_PREFER.get(step_kind) or ()
    if m.id in prefer:
        rank = prefer.index(m.id)
        pref_score = 50.0 - 3.0 * rank
        reasons.append(f"prefer_rank={rank}")
    else:
        pref_score = 4.0
        reasons.append("not_in_prefer")

    strength_s = float(m.strength) * 4.0
    reasons.append(f"strength={m.strength}")

    band = str(signal.get("band") or "easy")
    if step_kind in {"plan", "critique"} or band == "hard":
        cost_s = float(6 - int(m.cost_tier)) * 2.0
    else:
        cost_s = float(6 - int(m.cost_tier)) * 4.0
    reasons.append(f"cost_tier={m.cost_tier}")

    role_map = {"plan": "plan", "critique": "critique", "repair": "reason", "code": "build"}
    need = role_map.get(step_kind, "build")
    role_s = 12.0 if need in (m.roles or ()) else (6.0 if "fast" in (m.roles or ()) and step_kind == "code" else 0.0)
    if role_s:
        reasons.append(f"role_match={need}")

    return pref_score + strength_s + cost_s + role_s, reasons


def allocate(
    *,
    task: str = "build",
    goal: str = "",
    features: list | None = None,
    findings_count: int = 0,
    file_count: int = 0,
    last_tool: str = "",
    soft_parse_fail: bool = False,
) -> AllocateResult | None:
    from lumen.engine.services.llm.model_catalog import available_models

    step_kind = decompose_step(
        task=task,
        goal=goal,
        features=features,
        findings_count=findings_count,
        file_count=file_count,
        last_tool=last_tool,
        soft_parse_fail=soft_parse_fail,
    )
    signal = difficulty_signal(
        step_kind=step_kind,
        goal=goal,
        features=features,
        findings_count=findings_count,
        file_count=file_count,
    )
    pool = [m for m in available_models() if m.key_present()]
    if not pool:
        return None

    ranked: list[tuple[float, Any, tuple[str, ...]]] = []
    for m in pool:
        score, reasons = _score_model(m, step_kind, signal)
        ranked.append((score, m, tuple(reasons)))
    ranked.sort(key=lambda x: -x[0])
    best_score, best, best_reasons = ranked[0]
    logger.info(
        "r2_allocator kind=%s band=%s pick=%s/%s score=%.1f keys=%d",
        step_kind,
        signal.get("band"),
        best.provider,
        best.model_id,
        best_score,
        len(pool),
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


__all__ = [
    "StepKind",
    "AllocateResult",
    "decompose_step",
    "difficulty_signal",
    "allocate",
    "router_mode",
]
