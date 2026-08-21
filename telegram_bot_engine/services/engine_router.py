"""Core engine router — selects catalog | hybrid | cline from BuildIR.

User
  → Core (this module + IR)
  → catalog (spec_core)  OR  cline runtime (under policy)
  → acceptance / smoke (callers)

Does not talk to the user. Does not translate. Only routes execution.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from telegram_bot_engine.core.ir import BuildIR, EngineMode, IRStatus

logger = logging.getLogger(__name__)


def _env_force_mode() -> EngineMode | None:
    raw = (os.getenv("ENGINE_MODE_FORCE") or "").strip().lower()
    if not raw:
        return None
    try:
        return EngineMode(raw)
    except ValueError:
        return None


def decide_engine_mode(
    *,
    preferred_keys: list[str],
    capabilities_gap: list[str],
    looks_custom: bool,
    needs_ai_codegen: bool,
    confidence: float,
) -> EngineMode:
    """Policy: catalog first; cline only for real gaps / custom stacks."""
    forced = _env_force_mode()
    if forced is not None:
        return forced

    core = {"start", "help", "lang", "language", "cancel"}
    non_core = [k for k in preferred_keys if k not in core]
    gap = [g for g in capabilities_gap if str(g).strip()]

    # Strong catalog hit
    if non_core and not gap and not needs_ai_codegen:
        return EngineMode.CATALOG

    # Partial: some keys + residual custom need
    if non_core and (gap or looks_custom or needs_ai_codegen):
        return EngineMode.HYBRID

    # No catalog signal but custom demand
    if needs_ai_codegen or (looks_custom and not non_core):
        return EngineMode.CLINE

    # Weak confidence with only core keys → still catalog (echo/start bots)
    if confidence >= 0.4:
        return EngineMode.CATALOG
    return EngineMode.CATALOG


def build_ir_from_package(package: dict[str, Any], *, user_id: int = 0) -> BuildIR:
    """Normalize bridge package → BuildIR (control-plane object)."""
    preferred = [str(x).strip() for x in (package.get("preferred_keys") or []) if str(x).strip()]
    if "capabilities_matched" in package:
        matched = [str(x).strip() for x in (package.get("capabilities_matched") or []) if str(x).strip()]
    else:
        matched = list(preferred)
    gap = [str(x).strip() for x in (package.get("capabilities_gap") or []) if str(x).strip()]
    integrations = [str(x).strip() for x in (package.get("integrations") or []) if str(x).strip()]
    looks_custom = bool(package.get("looks_custom"))
    needs_ai = bool(package.get("needs_ai_codegen"))
    conf = float(package.get("confidence") or 0.0)

    mode_raw = package.get("engine_mode")
    if mode_raw in {"catalog", "hybrid", "cline"}:
        mode = EngineMode(str(mode_raw))
    elif mode_raw in {"spec_core"}:
        mode = EngineMode.CATALOG
    elif mode_raw in {"ai_codegen"}:
        mode = EngineMode.CLINE
    else:
        mode = decide_engine_mode(
            preferred_keys=preferred,
            capabilities_gap=gap,
            looks_custom=looks_custom,
            needs_ai_codegen=needs_ai,
            confidence=conf,
        )

    acceptance = []
    for k in preferred:
        if k in {"start", "help"}:
            continue
        acceptance.append(
            {
                "id": f"cmd:{k}",
                "description": f"Command/feature {k} must be registered and invokable",
                "kind": "command",
            }
        )
    acceptance.append(
        {
            "id": "smoke",
            "description": "Pre-delivery smoke must pass",
            "kind": "smoke",
        }
    )

    ir = BuildIR.from_dict(
        {
            "original_text": package.get("original_text") or "",
            "spec_request": package.get("spec_request") or package.get("original_text") or "",
            "purpose": package.get("purpose") or "",
            "preferred_keys": preferred,
            "capabilities_matched": matched,
            "capabilities_gap": gap,
            "integrations": integrations,
            "acceptance": acceptance,
            "engine_mode": mode.value,
            "confidence": conf,
            "model": package.get("model") or "rules",
            "status": IRStatus.VALIDATED.value,
            "notes": list(package.get("notes") or []),
            "metadata": {
                "looks_custom": looks_custom,
                "needs_ai_codegen": needs_ai,
                "legacy_engine_mode": package.get("engine_mode"),
            },
            "user_id": int(user_id or 0),
        }
    )
    return ir


def execute_ir(
    ir: BuildIR,
    work_dir: str | Path,
    *,
    user_id: int = 0,
) -> Any:
    """Run the selected engine. Returns GenerationResult-compatible object when catalog.

    Cline path may return a result that signals fallback_catalog.
    """
    from pathlib import Path as _Path

    work_dir = _Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    uid = int(user_id or ir.user_id or 0)

    mode = ir.engine_mode
    logger.info(
        "engine_router mode=%s keys=%s gap=%s conf=%.2f",
        mode.value,
        ir.preferred_keys,
        ir.capabilities_gap,
        ir.confidence,
    )

    if mode in {EngineMode.CATALOG, EngineMode.HYBRID}:
        return _run_catalog(ir, work_dir, uid)

    # CLINE
    from telegram_bot_engine.services.cline_runtime import execute_cline_ir

    cline_res = execute_cline_ir(ir, work_dir)
    if cline_res.ok and cline_res.project_path:
        # Adapt to GenerationResult shape
        from telegram_bot_engine.core.result import GenerationResult

        return GenerationResult(
            success=True,
            project_path=cline_res.project_path,
            stages=[],
            validation_reports=[],
            errors=list(cline_res.errors),
            metadata={
                "engine": cline_res.engine,
                "ir": ir.to_dict(),
                "cline": cline_res.to_dict(),
            },
        )

    if cline_res.fallback_catalog or mode == EngineMode.CLINE:
        logger.warning(
            "cline path unavailable (%s) — falling back to catalog",
            cline_res.errors[:2],
        )
        result = _run_catalog(ir, work_dir, uid)
        try:
            meta = dict(getattr(result, "metadata", None) or {})
            meta["cline_fallback"] = cline_res.to_dict()
            meta["ir"] = ir.to_dict()
            result.metadata = meta
        except Exception:
            pass
        return result

    from telegram_bot_engine.core.result import GenerationResult

    return GenerationResult(
        success=False,
        project_path=None,
        stages=[],
        validation_reports=[],
        errors=list(cline_res.errors) or ["cline_failed"],
        metadata={"ir": ir.to_dict(), "cline": cline_res.to_dict()},
    )


def _run_catalog(ir: BuildIR, work_dir: Path, user_id: int) -> Any:
    from telegram_bot_engine import generate_bot

    result = generate_bot(
        ir.spec_request or ir.original_text,
        work_dir=str(work_dir),
        user_id=int(user_id or 0),
        preferred_keys=list(ir.preferred_keys) or None,
    )
    try:
        meta = dict(getattr(result, "metadata", None) or {})
        meta["ir"] = ir.to_dict()
        meta["engine_router_mode"] = ir.engine_mode.value
        result.metadata = meta
    except Exception:
        pass
    return result


__all__ = [
    "build_ir_from_package",
    "decide_engine_mode",
    "execute_ir",
]
