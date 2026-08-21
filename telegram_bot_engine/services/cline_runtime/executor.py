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
    """True only when explicitly enabled AND a provider can be loaded."""
    flag = (os.getenv("CLINE_ENABLED") or "0").strip().lower()
    if flag not in {"1", "true", "yes", "on"}:
        return False
    # Optional real SDK
    try:
        importlib.import_module("cline")  # type: ignore
        return True
    except Exception:
        pass
    try:
        importlib.import_module("@cline/sdk")  # invalid as py module; ignore
    except Exception:
        pass
    # Custom provider module: path.to.module:callable
    prov = (os.getenv("CLINE_PROVIDER") or "").strip()
    if prov:
        return True
    return False


def _policy_allows_cline(ir: Any) -> tuple[bool, str]:
    """Security gate: never open shell tools without sandbox policy."""
    allow_shell = (os.getenv("CLINE_ALLOW_SHELL") or "0").strip().lower() in {
        "1", "true", "yes", "on"
    }
    allow_web = (os.getenv("CLINE_ALLOW_WEB") or "0").strip().lower() in {
        "1", "true", "yes", "on"
    }
    # Default: Cline path is allowed for planning/codegen files only when enabled
    if not is_cline_available():
        return False, "cline_disabled_or_unavailable"
    # High-risk IR gaps still require explicit allow
    gaps = list(getattr(ir, "capabilities_gap", None) or [])
    integrations = list(getattr(ir, "integrations", None) or [])
    if integrations and not allow_web:
        return False, "integrations_require_CLINE_ALLOW_WEB=1"
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

    # SDK present but no custom provider: scaffold contract only (no blind codegen)
    matched = list(getattr(ir, "capabilities_matched", None) or getattr(ir, "preferred_keys", None) or [])
    gap = list(getattr(ir, "capabilities_gap", None) or [])
    if matched and not gap:
        # Should have been catalog mode; still safe to ask catalog
        return ClineExecutionResult(
            ok=False,
            engine="cline_noop_matched_catalog",
            warnings=["ir_has_no_gap_use_catalog"],
            metadata={"matched": matched},
            fallback_catalog=True,
        )

    # Without a wired provider, do not pretend we built a custom bot
    return ClineExecutionResult(
        ok=False,
        engine="cline_not_wired",
        errors=[
            "CLINE_ENABLED but no CLINE_PROVIDER and no usable SDK hook. "
            "Set CLINE_PROVIDER=module:fn or install/wire the SDK."
        ],
        warnings=["fallback_catalog_recommended"],
        metadata={
            "gap": gap,
            "matched": matched,
            "hint": "Wire provider to implement Files/Terminal/MCP under sandbox",
        },
        fallback_catalog=True,
    )


__all__ = [
    "ClineExecutionResult",
    "execute_cline_ir",
    "is_cline_available",
]
