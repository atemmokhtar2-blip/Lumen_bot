"""Cline execution adapter.

Primary design:
  Core IR → policy gate → free agent (Phase 5) or builtin → acceptance

Modes (env):
  CLINE_ENABLED=1          — allow general path
  CLINE_MODE=agent|builtin — default agent (real free path); builtin = old catalog compose
  CLINE_PROVIDER=mod:fn    — optional full override
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
    """Cline is the sole product generation engine — enabled by default.

    Set CLINE_ENABLED=0 only for emergency kill-switch.
    """
    flag = (os.getenv("CLINE_ENABLED") or "1").strip().lower()
    return flag not in {"0", "false", "no", "off"}


def _cline_mode() -> str:
    mode = (os.getenv("CLINE_MODE") or "agent").strip().lower()
    if mode in {"builtin", "catalog", "legacy"}:
        return "builtin"
    return "agent"


def _policy_allows_cline(ir: Any) -> tuple[bool, str]:
    allow_shell = (os.getenv("CLINE_ALLOW_SHELL") or "0").strip().lower() in {
        "1", "true", "yes", "on"
    }
    if not is_cline_available():
        return False, "cline_disabled_or_unavailable"
    gaps = list(getattr(ir, "capabilities_gap", None) or [])
    if any("shell" in str(g).lower() or "terminal" in str(g).lower() for g in gaps):
        if not allow_shell:
            return False, "shell_gap_requires_CLINE_ALLOW_SHELL=1"
    return True, "ok"


def _call_external_provider(ir: Any, work_dir: Path) -> ClineExecutionResult | None:
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
            fallback_catalog=False,
        )


def execute_cline_ir(ir: Any, work_dir: str | Path) -> ClineExecutionResult:
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)

    allowed, reason = _policy_allows_cline(ir)
    if not allowed:
        logger.error("cline path blocked: %s", reason)
        return ClineExecutionResult(
            ok=False,
            engine="cline_blocked",
            errors=[reason],
            warnings=["cline_blocked_by_policy"],
            metadata={
                "policy": reason,
                "ir_mode": getattr(getattr(ir, "engine_mode", None), "value", None),
            },
            fallback_catalog=False,
        )

    external = _call_external_provider(ir, work)
    if external is not None:
        return external

    mode = _cline_mode()
    # Production policy: catalog builtin is dead unless CLINE_ALLOW_BUILTIN=1 (dev only)
    try:
        from lumen.engine.services.multi_agent.production_policy import allow_cline_builtin
        if mode == "builtin" and not allow_cline_builtin():
            logger.error("cline builtin blocked by production policy")
            return ClineExecutionResult(
                ok=False,
                engine="cline_builtin_blocked",
                errors=["cline_builtin_disabled: set CLINE_MODE=agent (or CLINE_ALLOW_BUILTIN=1 in non-prod)"],
                warnings=["builtin_path_removed"],
                metadata={"policy": "force_agent"},
                fallback_catalog=False,
            )
    except Exception as _pol_exc:
        if mode == "builtin":
            # Fail closed if policy import fails and mode is builtin
            logger.warning("policy check failed (%s); refusing builtin", _pol_exc)
            return ClineExecutionResult(
                ok=False,
                engine="cline_builtin_blocked",
                errors=["cline_builtin_disabled_policy_unavailable"],
                warnings=["builtin_path_removed"],
                metadata={},
                fallback_catalog=False,
            )

    ir_dict = ir.to_dict() if hasattr(ir, "to_dict") else dict(ir)

    if mode == "agent":
        try:
            from lumen.engine.services.cline_runtime.provider_agent import (
                build as agent_build,
            )
            try:
                from lumen.engine.services.progress_bus import report_progress
                report_progress({
                    "phase": "coding_agent",
                    "tool": "coding_agent",
                    "detail": "مسار Cline agent",
                    "step": 0,
                })
            except Exception:
                pass

            raw = agent_build(ir_dict, str(work))
            return ClineExecutionResult(
                ok=bool(raw.get("ok")),
                project_path=raw.get("project_path"),
                engine=str(raw.get("engine") or "cline_agent"),
                errors=list(raw.get("errors") or []),
                warnings=list(raw.get("warnings") or []),
                metadata=dict(raw.get("metadata") or {}),
                fallback_catalog=bool(raw.get("fallback_catalog")),
            )
        except Exception as exc:
            logger.exception("cline agent provider failed")
            return ClineExecutionResult(
                ok=False,
                engine="cline_agent_error",
                errors=[f"{type(exc).__name__}:{exc}"],
                fallback_catalog=False,
            )

    # Catalog/builtin path permanently deleted — refuse non-agent modes.
    return ClineExecutionResult(
        ok=False,
        engine="cline_mode_unsupported",
        errors=[
            f"cline_mode={mode!r}_rejected: only agent path remains "
            "(catalog/hybrid/builtin permanently removed)"
        ],
        warnings=["catalog_path_deleted"],
        metadata={"requested_mode": mode},
        fallback_catalog=False,
    )


__all__ = [
    "ClineExecutionResult",
    "execute_cline_ir",
    "is_cline_available",
]
