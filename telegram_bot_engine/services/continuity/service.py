"""
Phase 5 — Project Continuity

Decide whether the user wants to continue work on an existing project
(generated or cloned) and which path to use. No fixed user-facing texts.
No domain templates. All signals come from user text + memory + sandbox index.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..context_engine.service import ContextResolution, resolve_context


@dataclass
class ContinuityPlan:
    """Machine plan only — not a chat script."""

    active: bool = False
    mode: str = ""  # continue_dev | inspect | none
    target_path: str = ""
    target_kind: str = ""
    confidence: float = 0.0
    signals: list[str] = field(default_factory=list)
    prefer_repo_dev: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "active": self.active,
            "mode": self.mode,
            "target_path": self.target_path,
            "target_kind": self.target_kind,
            "confidence": self.confidence,
            "signals": list(self.signals)[:16],
            "prefer_repo_dev": self.prefer_repo_dev,
        }


_CONTINUE_CUES = re.compile(
    r"(?:"
    r"عد[لّ]|عدّل|تعديل|طور|طوّر|تطوير|كم[لّ]|كمّل|كمّلي|"
    r"ضيف|أضف|اضف|احذف|امسح|أصلح|اصلح|حسّن|حسن|"
    r"رج[عّ]|رجع|كمل على|كمّل على|نفس البوت|نفس المشروع|"
    r"اللي فات|اللي قبل|السابق|آخر بوت|اخر بوت|آخر مشروع|اخر مشروع|"
    r"\bmodify\b|\bupdate\b|\bcontinue\b|\badd\b|\bfix\b|\bimprove\b|"
    r"\brefactor\b|\bextend\b"
    r")",
    re.I,
)

_INSPECT_CUES = re.compile(
    r"(?:"
    r"اشرح|شرح|هيكل|الأوامر|الاوامر|الملفات|اعرض|افتح|"
    r"\bexplain\b|\blist\b|\bshow\b|\bstatus\b|\bwhat\s+is\b"
    r")",
    re.I,
)


def plan_continuity(
    user_id: int,
    text: str,
    *,
    base_dir: str | Path | None = None,
    active_path: str = "",
    ctx: ContextResolution | None = None,
) -> ContinuityPlan:
    text = (text or "").strip()
    plan = ContinuityPlan()
    if not text:
        return plan

    if ctx is None:
        ctx = resolve_context(
            user_id, text, base_dir=base_dir, active_path=active_path
        )

    path = (ctx.target_path or active_path or "").strip()
    if path and not Path(path).exists():
        path = ""

    continue_hit = bool(_CONTINUE_CUES.search(text))
    inspect_hit = bool(_INSPECT_CUES.search(text))

    if ctx.refers_to_prior and path and ctx.confidence >= 0.45:
        plan.active = True
        plan.target_path = path
        plan.target_kind = ctx.target_kind or ""
        plan.confidence = ctx.confidence
        plan.signals = list(ctx.signals) + ["prior_resolved"]
        if continue_hit:
            plan.mode = "continue_dev"
            plan.prefer_repo_dev = True
            plan.signals.append("continue_cue")
        elif inspect_hit:
            plan.mode = "inspect"
            plan.prefer_repo_dev = True
            plan.signals.append("inspect_cue")
        else:
            # prior reference without explicit verb — still bind for session
            plan.mode = "continue_dev" if ctx.confidence >= 0.6 else "inspect"
            plan.prefer_repo_dev = plan.mode == "continue_dev"
        return plan

    # Active session path + development language even without "السابق"
    if path and continue_hit:
        plan.active = True
        plan.mode = "continue_dev"
        plan.target_path = path
        plan.confidence = max(0.5, ctx.confidence)
        plan.prefer_repo_dev = True
        plan.signals = list(ctx.signals) + ["session_path", "continue_cue"]
        return plan

    if path and inspect_hit:
        plan.active = True
        plan.mode = "inspect"
        plan.target_path = path
        plan.confidence = max(0.4, ctx.confidence)
        plan.prefer_repo_dev = True
        plan.signals = list(ctx.signals) + ["session_path", "inspect_cue"]
        return plan

    return plan


__all__ = ["ContinuityPlan", "plan_continuity"]
