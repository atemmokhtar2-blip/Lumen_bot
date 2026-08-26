"""Core engine router — Cline SDK is the sole generation engine.

Deterministic engines (catalog / hybrid / infinite / spec_core generate_bot)
are purged from the user-request path.

  package → BuildIR → validate_and_normalize_ir → execute_cline_ir → IR acceptance
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from lumen.engine.core.ir import BuildIR, EngineMode, IRStatus

logger = logging.getLogger(__name__)


def _env_force_mode() -> EngineMode | None:
    """ENGINE_MODE_FORCE is ignored for catalog/hybrid/infinite — product is Cline-only."""
    raw = (os.getenv("ENGINE_MODE_FORCE") or "").strip().lower()
    if not raw:
        return None
    try:
        mode = EngineMode(raw)
    except ValueError:
        return None
    if mode != EngineMode.CLINE:
        logger.warning(
            "ENGINE_MODE_FORCE=%s ignored — deterministic engines purged; forcing CLINE",
            raw,
        )
        return EngineMode.CLINE
    return mode


def _deterministic_paused() -> bool:
    """Deterministic engines (catalog / hybrid / infinite / spec_core) are permanently off.

    DETERMINISTIC_ENGINE is ignored — product path is Cline SDK only.
    Kept as a named API for call sites that still import it.
    """
    return True


def _cline_only() -> bool:
    """Cline SDK is the sole generation engine for user requests."""
    return True


def _infinite_primary() -> bool:
    """Infinite/spec_core path permanently disabled."""
    return False


def _infinite_preferred() -> bool:
    return False


def decide_engine_mode(
    *,
    preferred_keys: list[str],
    capabilities_gap: list[str],
    looks_custom: bool,
    needs_ai_codegen: bool,
    confidence: float,
) -> EngineMode:
    """Product policy: Cline SDK only. Deterministic engines are purged from the request path."""
    forced = _env_force_mode()
    if forced is not None:
        return forced
    return EngineMode.CLINE


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

    # Product path: Cline SDK only — ignore package.engine_mode catalog/hybrid/infinite.
    mode_raw = package.get("engine_mode")
    mode = EngineMode.CLINE
    if mode_raw and str(mode_raw) not in {"cline", "ai_codegen", ""}:
        logger.info(
            "purged deterministic engine_mode=%s → cline",
            mode_raw,
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
                "dynamic_spec": package.get("dynamic_spec"),
                "bot_spec": package.get("bot_spec"),
                "engine": package.get("engine"),
            },
            "user_id": int(user_id or 0),
        }
    )
    from lumen.engine.core.ir_validate import validate_and_normalize_ir

    v = validate_and_normalize_ir(ir)
    if v.warnings:
        ir.notes = list(ir.notes) + [f"warn:{w}" for w in v.warnings[:6]]
    if not v.ok:
        ir.status = IRStatus.REJECTED
        ir.notes = list(ir.notes) + [f"err:{e}" for e in v.errors]
    else:
        ir.engine_mode = EngineMode.CLINE
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

    from lumen.engine.core.ir_validate import (
        check_project_against_ir,
        validate_and_normalize_ir,
    )
    from lumen.engine.core.result import GenerationResult

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

    # ── Cline SDK only (deterministic catalog/hybrid/infinite purged) ──
    mode = EngineMode.CLINE
    ir.engine_mode = EngineMode.CLINE

    logger.info(
        "engine_router mode=cline (sole engine) keys=%s gap=%s conf=%.2f domain=%s",
        ir.preferred_keys,
        ir.capabilities_gap,
        ir.confidence,
        (ir.metadata or {}).get("domain_primary"),
    )

    from lumen.engine.services.cline_runtime import execute_cline_ir

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

    logger.warning("cline failed — no deterministic fallback: %s", cline_res.errors[:5])
    return GenerationResult(
        success=False,
        project_path=cline_res.project_path,
        stages=[],
        validation_reports=[],
        errors=list(cline_res.errors) or ["cline_failed"],
        metadata={
            "engine": cline_res.engine,
            "ir": ir.to_dict(),
            "cline": cline_res.to_dict(),
            "catalog_fallback": False,
            "deterministic_purged": True,
        },
    )



def _finalize(result: Any, ir: BuildIR, *, hybrid: bool = False) -> Any:
    meta = dict(getattr(result, "metadata", None) or {})
    meta["ir"] = ir.to_dict()
    meta["engine_router_mode"] = ir.engine_mode.value

    # Control plane: permissions + project record + delivery gate
    try:
        from lumen.engine.control_plane.permissions import check_generate_permission
        from lumen.engine.control_plane.projects import ProjectStore
        from lumen.engine.control_plane.plans import PlanStore
        from lumen.engine.control_plane.delivery_gate import gate_delivery

        perm = check_generate_permission(ir.user_id, engine_mode=ir.engine_mode.value)
        meta["permission"] = {"allowed": perm.allowed, "reason": perm.reason}
        if not perm.allowed:
            from lumen.engine.core.result import GenerationResult
            return GenerationResult(
                success=False,
                project_path=None,
                stages=[],
                validation_reports=[],
                errors=[perm.reason],
                metadata=meta,
            )
        plan = PlanStore().save_draft(ir.user_id, ir.to_dict(), notes=list(ir.notes or []))
        meta["plan_id"] = plan.plan_id
    except Exception as exc:
        meta["control_plane_error"] = f"{type(exc).__name__}:{exc}"

    path = getattr(result, "project_path", None)
    if path and hybrid and ir.capabilities_gap:
        try:
            from lumen.engine.services.hybrid_scaffolds import apply_hybrid_scaffolds

            written = apply_hybrid_scaffolds(path, list(ir.capabilities_gap), meta)
            meta["hybrid_scaffolds"] = written
        except Exception as exc:
            meta["hybrid_scaffold_error"] = f"{type(exc).__name__}:{exc}"

    if path and getattr(result, "success", False):
        try:
            from lumen.engine.core.ir_validate import check_project_against_ir

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

    path = getattr(result, "project_path", None)
    if path and getattr(result, "success", False):
        try:
            from lumen.engine.control_plane.delivery_gate import gate_delivery
            from lumen.engine.control_plane.projects import ProjectStore
            from lumen.engine.control_plane.plans import PlanStore

            gate = gate_delivery(path, ir=ir.to_dict())
            meta["delivery_gate"] = gate
            if not gate.get("ok"):
                result.success = False
                errs = list(getattr(result, "errors", None) or [])
                errs.extend(gate.get("errors") or [])
                result.errors = errs
            proj = ProjectStore().create(
                user_id=ir.user_id,
                title=(ir.purpose or ir.original_text or "bot")[:80],
                engine_mode=ir.engine_mode.value,
                ir_snapshot=ir.to_dict(),
                path=str(path),
                metadata={"delivery_gate": gate, "hybrid": hybrid},
            )
            meta["project_id"] = proj.project_id
            if meta.get("plan_id"):
                PlanStore().mark_executed(str(meta["plan_id"]))
            ProjectStore().update(
                proj.project_id,
                status="delivered" if getattr(result, "success", False) else "failed",
            )
        except Exception as exc:
            meta["control_plane_finalize_error"] = f"{type(exc).__name__}:{exc}"

    try:
        result.metadata = meta
    except Exception:
        pass
    return result


def _run_catalog(ir: BuildIR, work_dir: Path, user_id: int) -> Any:
    """Deterministic catalog path removed from product. Kept as a hard-fail stub."""
    from lumen.engine.core.result import GenerationResult

    logger.error("_run_catalog invoked — deterministic engine purged; refusing")
    return GenerationResult(
        success=False,
        project_path=None,
        stages=[],
        validation_reports=[],
        errors=["deterministic_engine_purged"],
        metadata={"engine": "purged", "ir": ir.to_dict()},
    )


__all__ = [
    "build_ir_from_package",
    "decide_engine_mode",
    "execute_ir",
]
