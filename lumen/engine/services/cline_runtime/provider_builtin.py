"""Builtin provider — permanently retired (was catalog compose).

Cline agent is the only generation path. This module remains importable so
old call sites fail closed with an explicit error instead of inventing bots.
"""
from __future__ import annotations

from typing import Any


def build(ir_dict: dict[str, Any], work_dir: str) -> dict[str, Any]:
    return {
        "ok": False,
        "project_path": None,
        "engine": "cline_builtin_removed",
        "errors": [
            "catalog_builtin_permanently_removed: use CLINE_MODE=agent (Cline SDK only)"
        ],
        "warnings": ["builtin_catalog_deleted"],
        "metadata": {"fallback_catalog": False},
        "fallback_catalog": False,
    }


__all__ = ["build"]
