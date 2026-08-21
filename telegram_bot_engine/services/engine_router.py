"""Core engine router — selects catalog | hybrid | cline from BuildIR.

Foundation is intentionally strict:
  package → BuildIR → validate_and_normalize_ir → execute → IR acceptance check
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

    if non_core and not gap and not needs_ai_codegen:
        return EngineMode.CATALOG
    if non_core and (gap or looks_custom or needs_ai_codegen):
        return EngineMode.HYBRID
    if needs_ai_codegen or (looks_custom and not non_core):
        return EngineMode.CLINE
    return EngineMode.CATALOG


def build_ir_from_package(package: dict[str, Any], *, user_id: int = 0) -> BuildIR:
    """Normalize bridge package → validated BuildIR."""
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

    ir = BuildIR.from_dict(
        {
            "original_text": package.get("original_text") or "",
            "spec_request": package.get("spec_request") or package.get("original_text") or "",
            "purpose": package.get("purpose") or "",
            "preferred_keys": preferred,
            "capabilities_matched": matched,
            "capabilities_gap": gap,
            "integrations": integrations,
            "acceptance": [],
            "engine_mode": mode.value,
            "confidence": conf,
            "model": package.get("model") or "rules",
            "status": IRStatus.DRAFT.value,
            "notes": list(package.get("notes") or []),
            "metadata": {
                "looks_custom": looks_custom,
                "needs_ai_codegen": needs_ai,
                "legacy_engine_mode": package.get("engine_mode"),
            },
            "user_id": int(user_id or 0),
        }
    )
    from telegram_bot_engine.core.ir_validate import validate_and_normalize_ir

    v = validate_and_normalize_ir(ir)
    if v.warnings:
        ir.notes = list(ir.notes) + [f"warn:{w}" for w in v.warnings[:6]]
    if not v.ok:
        ir.status = IRStatus.REJECTED
        ir.notes = list(ir.notes) + [f"err:{e}" for e in v.errors]
    else:
        # Re-decide mode after lean-pack enrichment
        ir.engine_mode = decide_engine_mode(
            preferred_keys=ir.preferred_keys,
            capabilities_gap=ir.capabilities_gap,
            looks_custom=looks_custom,
            needs_ai_codegen=needs_ai,
            confidence=ir.confidence,
        )
    return ir


def execute_ir(
    ir: BuildIR,
    work_dir: str | Path,
    *,
    user_id: int = 0,
) -> Any:
    """Validate → route → optional hybrid scaffolds → IR acceptance report."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    uid = int(user_id or ir.user_id or 0)

    from telegram_bot_engine.core.ir_validate import (
        check_project_against_ir,
        validate_and_normalize_ir,
    )
    from telegram_bot_engine.core.result import GenerationResult

    v = validate_and_normalize_ir(ir)
    ir = v.ir
    if not v.ok:
        return GenerationResult(
            success=False,
            project_path=None,
            stages=[],
            validation_reports=[],
            errors=list(v.errors) or ["ir_rejected"],
            metadata={"ir": ir.to_dict(), "ir_warnings": v.warnings},
        )

    mode = ir.engine_mode
    logger.info(
        "engine_router mode=%s keys=%s gap=%s conf=%.2f domain=%s",
        mode.value,
        ir.preferred_keys,
        ir.capabilities_gap,
        ir.confidence,
        (ir.metadata or {}).get("domain_primary"),
    )

    if mode == EngineMode.CLINE:
        from telegram_bot_engine.services.cline_runtime import execute_cline_ir

        cline_res = execute_cline_ir(ir, work_dir)
        if cline_res.ok and cline_res.project_path:
            result = GenerationResult(
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
            return _finalize(result, ir)
        logger.warning("cline unavailable %s — catalog fallback", cline_res.errors[:2])
        result = _run_catalog(ir, work_dir, uid)
        try:
            meta = dict(getattr(result, "metadata", None) or {})
            meta["cline_fallback"] = cline_res.to_dict()
            result.metadata = meta
        except Exception:
            pass
        return _finalize(result, ir, hybrid=True)

    # catalog or hybrid
    result = _run_catalog(ir, work_dir, uid)
    return _finalize(result, ir, hybrid=(mode == EngineMode.HYBRID))


def _finalize(result: Any, ir: BuildIR, *, hybrid: bool = False) -> Any:
    meta = dict(getattr(result, "metadata", None) or {})
    meta["ir"] = ir.to_dict()
    meta["engine_router_mode"] = ir.engine_mode.value

    path = getattr(result, "project_path", None)
    if path and hybrid and ir.capabilities_gap:
        try:
            from telegram_bot_engine.services.hybrid_scaffolds import apply_hybrid_scaffolds

            written = apply_hybrid_scaffolds(path, list(ir.capabilities_gap), meta)
            meta["hybrid_scaffolds"] = written
        except Exception as exc:
            meta["hybrid_scaffold_error"] = f"{type(exc).__name__}:{exc}"

    if path and getattr(result, "success", False):
        try:
            from telegram_bot_engine.core.ir_validate import check_project_against_ir

            acc = check_project_against_ir(str(path), ir)
            meta["ir_acceptance"] = acc
            if not acc.get("ok"):
                # Soft fail: keep success but flag for delivery layer
                meta["ir_acceptance_soft_fail"] = True
                logger.warning(
                    "IR acceptance missing features: %s",
                    acc.get("missing_features"),
                )
        except Exception as exc:
            meta["ir_acceptance_error"] = f"{type(exc).__name__}:{exc}"

    try:
        result.metadata = meta
    except Exception:
        pass
    return result


def _run_catalog(ir: BuildIR, work_dir: Path, user_id: int) -> Any:
    from telegram_bot_engine import generate_bot

    return generate_bot(
        ir.spec_request or ir.original_text,
        work_dir=str(work_dir),
        user_id=int(user_id or 0),
        preferred_keys=list(ir.preferred_keys) or None,
    )


__all__ = [
    "build_ir_from_package",
    "decide_engine_mode",
    "execute_ir",
]
