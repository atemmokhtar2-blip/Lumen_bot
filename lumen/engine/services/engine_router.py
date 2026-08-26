"""Core engine router — selects catalog | hybrid | cline from BuildIR.

Foundation is intentionally strict:
  package → BuildIR → validate_and_normalize_ir → execute → IR acceptance check
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from lumen.engine.core.ir import BuildIR, EngineMode, IRStatus

logger = logging.getLogger(__name__)


def _env_force_mode() -> EngineMode | None:
    raw = (os.getenv("ENGINE_MODE_FORCE") or "").strip().lower()
    if not raw:
        return None
    try:
        return EngineMode(raw)
    except ValueError:
        return None


def _deterministic_paused() -> bool:
    """Deterministic engine is HARD-OFF in the product path.

    No hosting env needed. Only an explicit DETERMINISTIC_ENGINE=1
    (dev/emergency) re-enables catalog/infinite/hybrid.
    """
    raw = (os.getenv("DETERMINISTIC_ENGINE") or "").strip().lower()
    return raw not in {"1", "true", "yes", "on"}


def _cline_only() -> bool:
    """Cline SDK is the only generation path while deterministic is hard-off."""
    if _deterministic_paused():
        return True
    raw = os.getenv("CLINE_ONLY")
    if raw is None or not str(raw).strip():
        raw = os.getenv("CLINE_FORCE_AGENT")
    if raw is None or not str(raw).strip():
        return False
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _infinite_primary() -> bool:
    """Infinite path — disabled while deterministic is paused."""
    if _deterministic_paused():
        return False
    if (os.getenv("TBE_INFINITE_SPEC") or "").strip().lower() in {"1", "true", "yes", "on"}:
        return True
    raw = (os.getenv("TBE_INFINITE_PRIMARY") or "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _infinite_preferred() -> bool:
    """Back-compat alias for _infinite_primary."""
    return _infinite_primary()


def decide_engine_mode(
    *,
    preferred_keys: list[str],
    capabilities_gap: list[str],
    looks_custom: bool,
    needs_ai_codegen: bool,
    confidence: float,
) -> EngineMode:
    """Policy: **Cline SDK primary** (deterministic paused by default).

    Order:
      1. ENGINE_MODE_FORCE override (if set)
      2. Cline when CLINE_ONLY or deterministic paused (default)
      3. Else infinite / catalog / hybrid only if DETERMINISTIC_ENGINE=1
    """
    forced = _env_force_mode()
    if forced is not None:
        if _deterministic_paused() and forced in {
            EngineMode.CATALOG, EngineMode.HYBRID, EngineMode.INFINITE
        }:
            logger.warning(
                "deterministic paused — ignoring ENGINE_MODE_FORCE=%s, using CLINE",
                forced.value,
            )
            return EngineMode.CLINE
        return forced

    if _cline_only() or _deterministic_paused():
        return EngineMode.CLINE

    if _infinite_primary():
        return EngineMode.INFINITE

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
    elif mode_raw in {"infinite", "infinite_v1", "atomic", "dynamic"}:
        mode = EngineMode.INFINITE
    else:
        mode = decide_engine_mode(
            preferred_keys=preferred,
            capabilities_gap=gap,
            looks_custom=looks_custom,
            needs_ai_codegen=needs_ai,
            confidence=conf,
        )
    if _cline_only():
        mode = EngineMode.CLINE

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
        # Preserve infinite when package/engine says so; else re-decide
        eng = str(package.get("engine") or "")
        if mode == EngineMode.INFINITE or eng.startswith("infinite") or mode_raw in {
            "infinite", "infinite_v1", "atomic", "dynamic"
        }:
            ir.engine_mode = EngineMode.INFINITE
        else:
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

    mode = ir.engine_mode
    if _deterministic_paused() and mode != EngineMode.CLINE:
        logger.warning(
            "deterministic paused — remapping mode %s → cline", mode.value
        )
        mode = EngineMode.CLINE
        ir.engine_mode = EngineMode.CLINE

    logger.info(
        "engine_router mode=%s keys=%s gap=%s conf=%.2f domain=%s",
        mode.value,
        ir.preferred_keys,
        ir.capabilities_gap,
        ir.confidence,
        (ir.metadata or {}).get("domain_primary"),
    )

    if mode == EngineMode.INFINITE:
        try:
            from lumen.engine.spec_core.infinite.compose import try_compose_infinite
            from lumen.engine.services.translator_client import translate_infinite_via_gemini
            from lumen.engine.spec_core.pipeline import build_from_spec
            from lumen.engine.spec_core.infinite.jit_compiler import compile_to_project
        except Exception as exc:
            logger.warning("infinite path unavailable (%s); falling back to hybrid/catalog", type(exc).__name__)
            mode = EngineMode.HYBRID
        else:
            dyn_payload = (ir.metadata or {}).get("dynamic_spec")
            bot_spec_dict = (ir.metadata or {}).get("bot_spec")
            dyn = None
            bot = None
            if dyn_payload:
                bot, dyn, err = try_compose_infinite(dyn_payload)
            if bot is None:
                # re-translate via infinite if needed
                inf = translate_infinite_via_gemini(
                    ir.original_text or ir.spec_request,
                    context={"infinite": True, "looks_custom": True},
                )
                if inf and inf.get("ok"):
                    dyn_payload = inf.get("dynamic_spec")
                    bot_spec_dict = inf.get("bot_spec")
                    bot, dyn, err = try_compose_infinite(dyn_payload or {})
                else:
                    err = (inf or {}).get("validation_error") if isinstance(inf, dict) else "infinite_translate_failed"
                    logger.warning("infinite translate failed: %s — building deterministic DynamicBotSpec", err)
                    # Deterministic atomic fallback so infinite path stays primary offline
                    try:
                        from lumen.engine.spec_core.dynamic_bot_spec import DynamicBotSpec
                        req = (ir.original_text or ir.spec_request or "bot").strip()[:80]
                        fallback = {
                            "bot_name": (req[:40] or "infinite_bot").replace(" ", "_")[:40] or "infinite_bot",
                            "description": req[:500],
                            "language": "ar",
                            "version": "infinite_v1",
                            "nodes": [
                                {
                                    "id": "start_n",
                                    "trigger": {"type": "on_start", "config": {"command": "start"}},
                                    "actions": [{
                                        "type": "send_message",
                                        "config": {"text": f"مرحباً — {req[:120]}"},
                                    }],
                                },
                                {
                                    "id": "msg_n",
                                    "trigger": {"type": "on_message", "config": {}},
                                    "conditions": [{"type": "always", "config": {}}],
                                    "actions": [{
                                        "type": "send_message",
                                        "config": {"text": "تم استلام رسالتك."},
                                    }],
                                },
                            ],
                        }
                        # Add simple command nodes from preferred_keys
                        for i, key in enumerate((ir.preferred_keys or [])[:8]):
                            k = str(key).strip().lower().replace("-", "_")
                            if not k or k in {"start", "help"}:
                                continue
                            fallback["nodes"].append({
                                "id": f"cmd_{k}"[:32],
                                "trigger": {"type": "on_command", "config": {"command": k}},
                                "actions": [{
                                    "type": "send_message",
                                    "config": {"text": f"أمر /{k}"},
                                }],
                            })
                        bot, dyn, err2 = try_compose_infinite(fallback)
                        if bot is None and dyn is None:
                            logger.warning("infinite deterministic fallback failed: %s", err2)
                            mode = EngineMode.HYBRID
                        else:
                            dyn_payload = fallback
                    except Exception as exc:
                        logger.warning("infinite fallback error: %s", type(exc).__name__)
                        mode = EngineMode.HYBRID
            if mode == EngineMode.INFINITE and (bot is not None or bot_spec_dict or dyn is not None):
                out = work_dir / "infinite_bot"
                out.mkdir(parents=True, exist_ok=True)
                project_path = None
                errors: list[str] = []
                try:
                    if callable(compile_to_project) and dyn is not None:
                        project_path = compile_to_project(dyn, out)
                    if project_path is None:
                        spec = bot_spec_dict or (bot.to_dict() if bot else {})
                        br = build_from_spec(spec, out, request=ir.original_text or ir.spec_request)
                        if br.ok:
                            project_path = br.project_path
                        else:
                            errors = list(br.errors)
                except Exception as exc:
                    logger.exception("infinite compile failed")
                    errors.append(type(exc).__name__)
                if project_path:
                    # promote successful macro
                    try:
                        if dyn is not None:
                            from lumen.engine.spec_core.infinite.macro_registry import get_macro_registry
                            get_macro_registry().promote(dyn, score=0.8)
                    except Exception:
                        pass
                    result = GenerationResult(
                        success=True,
                        project_path=str(project_path),
                        stages=[],
                        validation_reports=[],
                        errors=errors,
                        metadata={
                            "engine": "infinite_v1",
                            "ir": ir.to_dict(),
                            "dynamic_spec": dyn.model_dump() if dyn is not None else dyn_payload,
                        },
                    )
                    return _finalize(result, ir)
                logger.warning("infinite build failed: %s — fallback hybrid", errors[:3])
                mode = EngineMode.HYBRID

    if mode == EngineMode.CLINE:
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
        # Network/LLM failures must not brick generation: fall back to catalog
        # unless operator explicitly disables it.
        if (os.getenv("CLINE_NO_CATALOG_FALLBACK") or "0").strip().lower() in {
            "1", "true", "yes", "on",
        }:
            logger.warning("cline failed and catalog fallback DISABLED: %s", cline_res.errors[:3])
            return GenerationResult(
                success=False,
                project_path=cline_res.project_path,
                stages=[],
                validation_reports=[],
                errors=list(cline_res.errors) or ["cline_failed_no_catalog_fallback"],
                metadata={
                    "engine": cline_res.engine,
                    "ir": ir.to_dict(),
                    "cline": cline_res.to_dict(),
                    "catalog_fallback": False,
                },
            )
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
    from lumen.engine import generate_bot

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
