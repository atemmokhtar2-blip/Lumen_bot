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
    """Deterministic Spec → code only. No LLM providers."""
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
    if stack:
        session = compose_session(stack, user_id=user_id, request=request)
        spec = session.to_spec()
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
    }

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
