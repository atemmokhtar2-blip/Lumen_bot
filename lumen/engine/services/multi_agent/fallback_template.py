"""Verified template fallback — deterministic catalog path removed.

Returns explicit failure so callers surface Cline errors instead of silent
legacy generate_bot. Kept as import-stable stub for multi_agent orchestrator.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class FallbackBuild:
    ok: bool = False
    project_path: str | None = None
    generation_result: Any = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    preset: str | None = None


def should_trigger_verified_fallback(
    *,
    attempts: int = 0,
    stagnant: bool = False,
    already_tried: bool = False,
) -> bool:
    """Catalog fallback purged — never auto-trigger a deterministic template."""
    return False


def build_verified_bot(
    request: str,
    *,
    work_dir: str | Path,
    user_id: int = 0,
) -> FallbackBuild:
    """No deterministic fallback — Cline SDK only."""
    return FallbackBuild(
        ok=False,
        errors=["no_deterministic_fallback"],
        warnings=["use_cline_sdk_only"],
    )


def run_verified_fallback_on_state(state: Any, *, work_dir: str | Path | None = None) -> Any:
    """No-op path: mark extension and return state unchanged structurally."""
    try:
        state.extensions = dict(state.extensions or {})
        state.extensions["fallback_template_tried"] = True
        state.extensions["fallback_template_result"] = {
            "ok": False,
            "errors": ["no_deterministic_fallback"],
        }
        errs = list(state.build_errors or [])
        errs.append("no_deterministic_fallback")
        state.build_errors = errs[:20]
    except Exception:
        pass
    return state


__all__ = [
    "FallbackBuild",
    "build_verified_bot",
    "should_trigger_verified_fallback",
    "run_verified_fallback_on_state",
]
