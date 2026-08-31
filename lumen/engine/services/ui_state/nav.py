"""Universal bottom navigation for Engine UI (Deep Navigation).

Every interactive surface that is not HOME gets a fixed last row:
  [رجوع] [الرئيسية] [إلغاء]

Callers either:
  - use buttons_for_state (already applies this), or
  - pass rows through ``with_nav`` / ``build_inline_keyboard(..., nav=True)``.
"""
from __future__ import annotations

from typing import Sequence

from .models import EngineUiPhase, UiButton

_NAV_ACTIONS = frozenset({"home", "cancel_generate", "nav_back"})
_NAV_LABELS = frozenset({"رجوع", "القائمة", "إلغاء", "الرئيسية"})


def nav_footer(phase: EngineUiPhase | str | None = None) -> tuple[UiButton, ...]:
    """Fixed bottom row for a phase (empty on HOME/IDLE)."""
    try:
        ph = phase if isinstance(phase, EngineUiPhase) else EngineUiPhase(str(phase or ""))
    except Exception:
        ph = EngineUiPhase.CONTEXT

    if ph in {EngineUiPhase.HOME, EngineUiPhase.IDLE}:
        return tuple()
    if ph == EngineUiPhase.GENERATING:
        return (
            UiButton("الرئيسية", "home"),
            UiButton("إلغاء", "cancel_generate", style="danger"),
        )
    return (
        UiButton("رجوع", "nav_back", style="primary"),
        UiButton("الرئيسية", "home"),
        UiButton("إلغاء", "cancel_generate", style="danger"),
    )


def with_nav(
    rows: Sequence[Sequence[UiButton]] | None,
    phase: EngineUiPhase | str | None = None,
    *,
    force: bool = False,
) -> tuple[tuple[UiButton, ...], ...]:
    """Strip duplicate nav buttons and append the standard footer."""
    try:
        ph = phase if isinstance(phase, EngineUiPhase) else EngineUiPhase(str(phase or "context"))
    except Exception:
        ph = EngineUiPhase.CONTEXT

    footer = nav_footer(ph)
    if not footer and not force:
        return tuple(tuple(r) for r in (rows or []) if r)

    cleaned: list[tuple[UiButton, ...]] = []
    for row in rows or []:
        kept = tuple(
            b
            for b in row
            if (getattr(b, "action", "") or "") not in _NAV_ACTIONS
            and (getattr(b, "text", "") or "") not in _NAV_LABELS
        )
        if kept:
            cleaned.append(kept)
    if footer:
        cleaned.append(footer)
    elif force:
        cleaned.append(
            (
                UiButton("رجوع", "nav_back", style="primary"),
                UiButton("الرئيسية", "home"),
                UiButton("إلغاء", "cancel_generate", style="danger"),
            )
        )
    return tuple(cleaned)


def last_row_is_nav(rows: Sequence[Sequence[UiButton]] | None) -> bool:
    if not rows:
        return False
    acts = {getattr(b, "action", "") for b in rows[-1]}
    return "home" in acts and ("cancel_generate" in acts or "nav_back" in acts)


__all__ = ["nav_footer", "with_nav", "last_row_is_nav"]
