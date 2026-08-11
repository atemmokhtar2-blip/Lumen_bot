"""
Telegram Bot Generation Engine

Active path (zero-AI, deterministic only):
  user text
    → spec_core presets + deterministic coding engines
    → anti-hallucination gate
    → project files on disk (inside per-user sandbox)

No LLM / AI provider path.
No formal/DSL/transpiler codegen path.
"""

from __future__ import annotations


from typing import TYPE_CHECKING

if TYPE_CHECKING:  # explicit for mypy/pylint/IDEs — no runtime cycle
    from .pipeline import PipelineOrchestrator as PipelineOrchestrator
    from .registry import EngineRegistry as EngineRegistry
    from .core import bootstrap as bootstrap, build_configuration as build_configuration


import os

__all__ = [
    "bootstrap", "build_configuration", "generate_bot",
    "PipelineOrchestrator", "EngineRegistry",
]




def _maybe_run_git_stage(
    *,
    original_request: str,
    project_path: str,
    stages: list,
) -> dict | None:
    """
    Optionally run GitOperationsEngine after successful generation.

    Triggered only when the user text explicitly mentions git-related actions
    (push / pull / commit / clone / git / بوش / اسحب / اعمل كوميت ...).

    STRICT RULE (non-negotiable):
      - No saved templates or ready-made bot packs.
      - Every operation is derived dynamically from the user's text
        and the just-generated project path. Nothing is pre-baked.
    """
    from pathlib import Path as _Path
    from .core.context import GenerationContext
    from .core.result import StageResult
    from .configuration import Configuration
    from .configuration.defaults import build_default_schema

    text = (original_request or "").lower()
    git_keywords = (
        "git ", "git\n", "push", "pull", "commit", "clone", "fetch",
        "بوش", "اسحب", "اسحبوا", "كوميت", "اعمل كوميت", "ادفع", "جيب من الجيت",
        "repository", "repo ", "github",
    )
    if not any(k in text for k in git_keywords):
        return None

    try:
        from .engines.generators.git_operations import GitOperationsEngine

        # Detect intended operation from user text (purely dynamic)
        op = "commit"
        if any(k in text for k in ("push", "بوش", "ادفع")):
            op = "push"
        elif any(k in text for k in ("pull", "اسحب", "اسحبوا", "جيب")):
            op = "pull"
        elif any(k in text for k in ("clone", "كلون")):
            op = "clone"
        elif any(k in text for k in ("commit", "كوميت", "اعمل كوميت")):
            op = "commit"

        cfg = Configuration(schema=build_default_schema(), sources=[])
        ctx = GenerationContext(
            request=original_request,
            config=cfg,
            work_dir=_Path(project_path),
        )
        # Pass real-execution hints so GitExecutor can act on the generated project
        ctx.artefacts["repo_path"] = project_path
        ctx.artefacts["git_operation"] = op
        ctx.artefacts["operation"] = op
        ctx.artefacts["execute_real"] = True
        ctx.artefacts["add_all"] = True
        ctx.artefacts["message"] = "chore: generated bot from user request"
        # Shape expected by UserRequestReader / GitExecutor
        ctx.artefacts["user_request"] = {
            "operation": op,
            "git_operation": op,
            "repo_path": project_path,
            "path": project_path,
            "work_dir": project_path,
            "execute_real": True,
            "add_all": True,
            "message": "chore: generated bot from user request",
            "operations": [op],
        }

        engine = GitOperationsEngine()
        result = engine.execute(ctx)

        ok = bool(getattr(result, "success", None) or getattr(result, "ok", False))
        stage_payload = {
            "ok": ok,
            "operation": op,
            "project_path": project_path,
            "outputs": getattr(result, "outputs", None) or {},
            "errors": list(getattr(result, "errors", None) or [])[:8],
        }

        if ok:
            stages.append(StageResult.ok("git_operations", outputs=stage_payload))
        else:
            stages.append(
                StageResult.failed(
                    "git_operations",
                    errors=stage_payload["errors"] or ["git_operations_failed"],
                )
            )
        return stage_payload
    except Exception as exc:
        stages.append(
            StageResult.failed("git_operations", errors=[f"{type(exc).__name__}:{exc}"])
        )
        return {"ok": False, "error": str(exc)[:200]}




def _generate_bot_zero_ai(request: str, work_dir, t0: float, user_id: int = 0, *, force: bool = False):
    """Deterministic Spec → code only. No LLM providers.

    Runs L1→L6 intelligence stack (understand / intent / questions / memory /
    suggestions / personalization) then builds the bot from the resolved style.
    """
    from pathlib import Path as _Path
    import tempfile as _tempfile
    import time as _time

    from .core.result import GenerationResult, StageResult
    from .spec_core.presets import (
        detect_preset,
        detect_preset_stack,
        compose_session,
        session_for_preset,
        is_bot_request,
        default_spec_from_request,
    )
    from .spec_core.pipeline import build_from_spec

    # ── Layers 1–6 (zero-AI intelligence) ──────────────────────────────────
    lu = None
    intent = None
    style = None
    suggestion_report = None
    memory_engine = None
    layers_meta: dict = {}
    try:
        from .spec_core.language_understanding import (
            understand,
            analyze_intent,
            suggest,
            personalize,
            feature_filter_for_skill,
            get_memory_engine,
        )

        lu = understand(request or "")
        intent = analyze_intent(request or "", lu=lu)
        if user_id:
            try:
                memory_engine = get_memory_engine()
                memory_engine.remember_turn(
                    int(user_id),
                    request or "",
                    intent=intent,
                    lu=lu,
                    features=list(getattr(intent, "feature_plan", None) or []),
                )
            except Exception:
                try:
                    memory_engine = get_memory_engine()
                except Exception:
                    memory_engine = None
        style = personalize(
            request or "", intent=intent, lu=lu, user_id=user_id or None, memory=memory_engine
        )
        suggestion_report = suggest(
            request or "",
            intent=intent,
            lu=lu,
            user_id=user_id or None,
            memory=memory_engine,
        )
        layers_meta = {
            "l1_domains": [
                {"domain": d.domain, "score": round(d.score, 2)}
                for d in (lu.domains or [])[:6]
            ] if lu else [],
            "l1_primary": getattr(lu, "primary_domain", None),
            "l2_intent": intent.primary.intent if intent and intent.primary else None,
            "l2_skill": getattr(intent, "skill_level", None),
            "l2_language": getattr(intent, "language", None),
            "l2_feature_plan": list(getattr(intent, "feature_plan", None) or [])[:20],
            "l5_build": [s.feature for s in (suggestion_report.build if suggestion_report else [])],
            "l5_improve": [s.feature for s in (suggestion_report.improve if suggestion_report else [])],
            "l6_style": style.to_dict() if style else None,
        }
    except Exception as _lu_exc:
        layers_meta = {"layers_error": f"{type(_lu_exc).__name__}:{str(_lu_exc)[:200]}"}

    preset = detect_preset(request)
    if preset is None and not force and not is_bot_request(request):
        if not (request or "").strip():
            return None
        force = True

    if work_dir is None:
        work_dir = _Path(_tempfile.mkdtemp(prefix="spec_bot_"))
    work_dir = _Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    project_dir = work_dir / "generated_bot"
    project_dir.mkdir(parents=True, exist_ok=True)

    # Always prefer multi-intent composition so bots are not single-thin packs
    stack = detect_preset_stack(request, limit=8)
    # L1 domain can lead the stack when strong
    if lu and getattr(lu, "primary_preset", None):
        lead = lu.primary_preset
        if lead and lead not in (stack or []):
            stack = [lead] + list(stack or [])
    if stack:
        session = compose_session(stack, user_id=user_id, request=request)
        # L5: inject high-confidence suggestion features into selection
        if suggestion_report is not None:
            for s in list(suggestion_report.build)[:8]:
                if getattr(s, "confidence", 0) >= 0.55 and hasattr(session, "selected"):
                    try:
                        session.selected.add(s.feature)
                    except Exception:
                        pass
        # L6: skill-based feature density
        if style is not None and hasattr(session, "selected"):
            try:
                filtered = feature_filter_for_skill(list(session.selected), style)
                session.selected = set(filtered)
            except Exception:
                pass
        spec = session.to_spec()
        # Stamp personalization into bot meta description
        if style is not None:
            try:
                from .spec_core.language_understanding import style_prompt_ar, phrase

                stamp = style_prompt_ar(style)
                if hasattr(spec, "bot") and hasattr(spec.bot, "description"):
                    base = (spec.bot.description or "").strip()
                    spec.bot.description = (base + "\n" + stamp).strip()[:500]
                if hasattr(spec, "bot") and hasattr(spec.bot, "language"):
                    lang = style.language_variant
                    if lang.startswith("ar"):
                        spec.bot.language = "ar"
                    elif lang == "en":
                        spec.bot.language = "en"
            except Exception:
                pass
        tag = "+".join(stack)
    elif preset:
        spec = session_for_preset(preset, user_id=user_id).to_spec()
        tag = preset
    else:
        spec = default_spec_from_request(request, user_id=user_id)
        tag = detect_preset(request) or "market_default"

    result = build_from_spec(spec, project_dir)
    elapsed = _time.perf_counter() - t0
    meta = {
        "engine": "spec_core",
        "preset": tag,
        "elapsed_ms": round(elapsed * 1000, 1),
        "zero_ai": True,
        "ai_disabled": True,
        "quality": "market_pack_v2",
        "layers": layers_meta,
    }
    # Persist L4 memory of successful build intent
    if memory_engine is not None and user_id and result.ok:
        try:
            feats = list(layers_meta.get("l2_feature_plan") or [])
            memory_engine.register_bot(
                int(user_id),
                name=getattr(getattr(spec, "bot", None), "name", None) or tag,
                intent=str(layers_meta.get("l2_intent") or tag),
                features=feats,
                request_text=request or "",
                preset=tag,
                output_path=str(project_dir),
                success=True,
            )
            primary = layers_meta.get("l2_intent")
            if primary and feats:
                memory_engine.record_patterns(intent=str(primary), features=feats)
        except Exception:
            pass

    # ── Anti-hallucination gate (mandatory before any "ready" claim) ──
    ah_report = None
    ah_dict = {}
    try:
        from .services.anti_hallucination import run_anti_hallucination_gate
        claimed = []
        try:
            claimed = [getattr(f, "feature", None) or getattr(f, "id", None) for f in (spec.features or [])]
            claimed = [str(c) for c in claimed if c]
        except Exception:
            claimed = []
        ah_report = run_anti_hallucination_gate(
            project_dir,
            claimed_features=claimed,
            user_request=request or "",
        )
        ah_dict = ah_report.to_dict()
        meta["anti_hallucination"] = ah_dict
        meta["verified_commands"] = list(ah_report.verified_commands)
        meta["stub_handlers"] = list(ah_report.stub_handlers)
        meta["ready_for_token"] = bool(ah_report.ready_for_token)
    except Exception as exc:
        meta["anti_hallucination_error"] = str(exc)[:300]
        meta["ready_for_token"] = False
        # Fail closed: never mark project ready if the gate itself crashed
        if result.ok:
            meta["blocked_by"] = "anti_hallucination_exception"
            return GenerationResult(
                success=False,
                project_path=str(project_dir),
                stages=[
                    StageResult.ok("spec_preset", outputs={"preset": tag}),
                    StageResult.ok("spec_codegen", outputs={"files": result.files}),
                    StageResult.failed(
                        "anti_hallucination",
                        errors=[f"gate_exception:{type(exc).__name__}"],
                    ),
                ],
                validation_reports=[],
                errors=[f"anti_hallucination_gate_failed:{type(exc).__name__}: {str(exc)[:200]}"],
                metadata=meta,
            )

    if result.ok and ah_report is not None and not ah_report.ok:
        # Structural generation succeeded but verification failed → not success for user
        meta.update(
            {
                "files_created": result.files,
                "services": result.plan_services,
                "ready_for_token": False,
                "blocked_by": "anti_hallucination",
            }
        )
        errs = list(result.errors) + [f.message_ar for f in ah_report.errors]
        return GenerationResult(
            success=False,
            project_path=str(project_dir),
            stages=[
                StageResult.ok("spec_preset", outputs={"preset": tag}),
                StageResult.ok("spec_codegen", outputs={"files": result.files}),
                StageResult.failed(
                    "anti_hallucination",
                    errors=[f.code for f in ah_report.errors],
                ),
            ],
            validation_reports=[],
            errors=errs,
            metadata=meta,
        )

    if result.ok:
        meta.update(
            {
                "files_created": result.files,
                "services": result.plan_services,
                # ready_for_token already set from gate (or False on gate error)
                "ready_for_token": bool(meta.get("ready_for_token", False)),
            }
        )
        stages = [
            StageResult.ok("spec_preset", outputs={"preset": tag}),
            StageResult.ok("spec_codegen", outputs={"files": result.files}),
        ]
        if ah_report is not None:
            stages.append(
                StageResult.ok(
                    "anti_hallucination",
                    outputs={
                        "verified_commands": ah_report.verified_commands,
                        "ready_for_token": ah_report.ready_for_token,
                    },
                )
            )
        return GenerationResult(
            success=True,
            project_path=str(project_dir),
            stages=stages,
            validation_reports=[],
            errors=[],
            metadata=meta,
        )
    return GenerationResult(
        success=False,
        project_path=str(project_dir),
        stages=[StageResult.failed("spec_codegen", errors=list(result.errors))],
        validation_reports=[],
        errors=list(result.errors),
        metadata=meta,
    )


def generate_bot(request: str, work_dir=None):
    """Generate a runnable Telegram bot using zero-AI engines only.

    AI plan/codegen path is disabled permanently. All generation goes through
    spec_core presets + deterministic coding engines.
    """
    import time
    from .core.result import GenerationResult

    t0 = time.perf_counter()
    original_request = (request or "").strip()
    if not original_request:
        return GenerationResult(
            success=False,
            project_path=None,
            stages=[],
            validation_reports=[],
            errors=["Empty request"],
            metadata={"ai_disabled": True},
        )

    result = _generate_bot_zero_ai(original_request, work_dir, t0, force=True)
    if result is not None:
        return result
    return GenerationResult(
        success=False,
        project_path=None,
        stages=[],
        validation_reports=[],
        errors=["zero_ai_generation_failed"],
        metadata={"engine": "spec_core", "ai_disabled": True},
    )



__all__ = [
    "bootstrap",
    "build_configuration",
    "generate_bot",
    "PipelineOrchestrator",
    "EngineRegistry",
]


def bootstrap(*args, **kwargs):
    from .core import bootstrap as _bootstrap
    return _bootstrap(*args, **kwargs)


def build_configuration(*args, **kwargs):
    from .core import build_configuration as _bc
    return _bc(*args, **kwargs)


def PipelineOrchestrator(*args, **kwargs):
    from .pipeline import PipelineOrchestrator as _PO
    return _PO(*args, **kwargs)


def EngineRegistry(*args, **kwargs):
    from .registry import EngineRegistry as _ER
    return _ER(*args, **kwargs)
