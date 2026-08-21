"""Cline execution adapter.

Primary design:
  Core IR → policy gate → (optional) Cline SDK / headless agent → acceptance

Until the external SDK is wired in production, we:
  1) Prefer catalog compose when IR has matched capabilities
  2) Mark gap explicitly in metadata
  3) Optionally call a registered provider hook (CLINE_PROVIDER_MODULE)
"""
from __future__ import annotations

import importlib
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ClineExecutionResult:
    ok: bool
    project_path: str | None = None
    engine: str = "cline"
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    # When True, caller should fall back to catalog generate_bot
    fallback_catalog: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "project_path": self.project_path,
            "engine": self.engine,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "fallback_catalog": self.fallback_catalog,
        }


def is_cline_available() -> bool:
    """True when CLINE_ENABLED — builtin provider always usable; external optional."""
    flag = (os.getenv("CLINE_ENABLED") or "0").strip().lower()
    return flag in {"1", "true", "yes", "on"}


def _policy_allows_cline(ir: Any) -> tuple[bool, str]:
    """Security gate: shell/web stay off unless env allows; builtin scaffolds always ok."""
    allow_shell = (os.getenv("CLINE_ALLOW_SHELL") or "0").strip().lower() in {
        "1", "true", "yes", "on"
    }
    if not is_cline_available():
        return False, "cline_disabled_or_unavailable"
    gaps = list(getattr(ir, "capabilities_gap", None) or [])
    # Builtin provider does not fetch web/shell — only catalog+scaffolds.
    # Live web/shell tools remain disabled in tools.py until policy enables them.
    if any("shell" in str(g).lower() or "terminal" in str(g).lower() for g in gaps):
        if not allow_shell:
            return False, "shell_gap_requires_CLINE_ALLOW_SHELL=1"
    return True, "ok"


def _call_external_provider(ir: Any, work_dir: Path) -> ClineExecutionResult | None:
    """Optional: CLINE_PROVIDER=package.module:function(ir_dict, work_dir) -> dict."""
    spec = (os.getenv("CLINE_PROVIDER") or "").strip()
    if not spec or ":" not in spec:
        return None
    mod_name, fn_name = spec.rsplit(":", 1)
    try:
        mod = importlib.import_module(mod_name)
        fn = getattr(mod, fn_name)
        raw = fn(ir.to_dict() if hasattr(ir, "to_dict") else dict(ir), str(work_dir))
        if not isinstance(raw, dict):
            return ClineExecutionResult(False, errors=["provider_returned_non_dict"])
        return ClineExecutionResult(
            ok=bool(raw.get("ok")),
            project_path=raw.get("project_path"),
            engine=str(raw.get("engine") or "cline_provider"),
            errors=list(raw.get("errors") or []),
            warnings=list(raw.get("warnings") or []),
            metadata=dict(raw.get("metadata") or {}),
            fallback_catalog=bool(raw.get("fallback_catalog")),
        )
    except Exception as exc:
        logger.exception("CLINE_PROVIDER failed")
        return ClineExecutionResult(
            ok=False,
            errors=[f"provider_error:{type(exc).__name__}:{exc}"],
            fallback_catalog=True,
        )


def execute_cline_ir(ir: Any, work_dir: str | Path) -> ClineExecutionResult:
    """Execute general path under IR. Safe fallback to catalog when blocked."""
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)

    allowed, reason = _policy_allows_cline(ir)
    if not allowed:
        logger.info("cline path blocked: %s — fallback catalog", reason)
        return ClineExecutionResult(
            ok=False,
            engine="cline_blocked",
            errors=[reason],
            warnings=["falling_back_to_catalog"],
            metadata={"policy": reason, "ir_mode": getattr(getattr(ir, "engine_mode", None), "value", None)},
            fallback_catalog=True,
        )

    external = _call_external_provider(ir, work)
    if external is not None:
        return external

    # Default: builtin provider (catalog compose + scaffolds + QA tools)
    try:
        from telegram_bot_engine.services.cline_runtime.provider_builtin import build as builtin_build

        raw = builtin_build(
            ir.to_dict() if hasattr(ir, "to_dict") else dict(ir),
            str(work),
        )
        return ClineExecutionResult(
            ok=bool(raw.get("ok")),
            project_path=raw.get("project_path"),
            engine=str(raw.get("engine") or "cline_builtin"),
            errors=list(raw.get("errors") or []),
            warnings=list(raw.get("warnings") or []),
            metadata=dict(raw.get("metadata") or {}),
            fallback_catalog=bool(raw.get("fallback_catalog")),
        )
    except Exception as exc:
        logger.exception("builtin cline provider failed")
        return ClineExecutionResult(
            ok=False,
            engine="cline_builtin_error",
            errors=[f"{type(exc).__name__}:{exc}"],
            fallback_catalog=True,
        )


__all__ = [
    "ClineExecutionResult",
    "execute_cline_ir",
    "is_cline_available",
]
