"""
Telegram Bot Generation Engine

Active path (Formal engine REMOVED permanently from generation):
  user text
    → Execution Planner (OpenAI / Hugging Face / Groq)
    → Plan-driven Codegen
    → project files on disk

No formal/DSL/transpiler codegen path.
No domain templates or canned packs.
"""

from __future__ import annotations

import os

__all__ = [
    "bootstrap", "build_configuration", "generate_bot",
    "PipelineOrchestrator", "EngineRegistry",
]


def __getattr__(name: str):
    if name in ("bootstrap", "build_configuration"):
        from .core import bootstrap, build_configuration
        return {"bootstrap": bootstrap, "build_configuration": build_configuration}[name]
    if name == "PipelineOrchestrator":
        from .pipeline import PipelineOrchestrator
        return PipelineOrchestrator
    if name == "EngineRegistry":
        from .registry import EngineRegistry
        return EngineRegistry
    if name == "generate_bot":
        return generate_bot
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")



def _maybe_run_git_stage(
    *,
    original_request: str,
    project_path: str,
    stages: list,
) -> dict | None:
    """
    Optionally run GitOperationsEngine after successful formal generation.

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




def _generate_bot_zero_ai(request: str, work_dir, t0: float, user_id: int = 0):
    """Deterministic path: preset Spec → coding engines (no LLM)."""
    from pathlib import Path as _Path
    import tempfile as _tempfile
    import time as _time
    from .core.result import GenerationResult, StageResult
    from .spec_core.presets import detect_preset, session_for_preset
    from .spec_core.pipeline import build_from_spec

    preset = detect_preset(request)
    if not preset:
        return None

    if work_dir is None:
        work_dir = _Path(_tempfile.mkdtemp(prefix="spec_bot_"))
    work_dir = _Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    project_dir = work_dir / "generated_bot"
    project_dir.mkdir(parents=True, exist_ok=True)

    session = session_for_preset(preset, user_id=user_id)
    result = build_from_spec(session.to_spec(), project_dir)
    elapsed = _time.perf_counter() - t0
    if result.ok:
        return GenerationResult(
            success=True,
            project_path=str(project_dir),
            stages=[
                StageResult.ok("spec_preset", outputs={"preset": preset}),
                StageResult.ok("spec_codegen", outputs={"files": result.files}),
            ],
            validation_reports=[],
            errors=[],
            metadata={
                "engine": "spec_core",
                "preset": preset,
                "files_created": result.files,
                "services": result.plan_services,
                "elapsed_ms": round(elapsed * 1000, 1),
                "ready_for_token": True,
                "zero_ai": True,
            },
        )
    return GenerationResult(
        success=False,
        project_path=str(project_dir),
        stages=[StageResult.failed("spec_codegen", errors=list(result.errors))],
        validation_reports=[],
        errors=list(result.errors),
        metadata={
            "engine": "spec_core",
            "preset": preset,
            "elapsed_ms": round(elapsed * 1000, 1),
            "zero_ai": True,
        },
    )


def generate_bot(request: str, work_dir=None):
    """
    Entry point used by the Telegram interface.

    Paths:
      1) Zero-AI presets (group admin / tickets / tasks / notes) via spec_core
      2) AI plan+codegen when a provider has credit (optional)

    Formal engine removed. Known bot types no longer require HF/OpenAI.
    """
    from pathlib import Path
    import os
    import tempfile
    import time

    from .core.result import GenerationResult, StageResult

    t0 = time.perf_counter()
    original_request = (request or "").strip()
    if not original_request:
        return GenerationResult(
            success=False,
            project_path=None,
            stages=[],
            validation_reports=[],
            errors=["Empty request"],
            metadata={},
        )

    # Prefer deterministic presets for common requests (works with zero AI credit)
    try:
        zero = _generate_bot_zero_ai(original_request, work_dir, t0)
        if zero is not None:
            return zero
    except Exception:
        pass

    work_dir = (
        Path(tempfile.mkdtemp(prefix="ai_bot_"))
        if work_dir is None
        else Path(work_dir)
    )
    work_dir.mkdir(parents=True, exist_ok=True)
    project_dir = work_dir / "generated_bot"
    project_dir.mkdir(parents=True, exist_ok=True)

    stages: list = []
    execution_plan_meta = None

    try:
        from .chat_ai.execution_planner import plan_from_text
        from .chat_ai.plan_codegen import generate_project_from_plan
        from .chat_ai import multi_provider as mp

        if not mp.any_enabled():
            elapsed = time.perf_counter() - t0
            return GenerationResult(
                success=False,
                project_path=None,
                stages=[
                    StageResult.failed(
                        "ai_provider",
                        errors=[
                            "No AI provider configured. "
                            "Set OPENAI_API_KEY and/or HF_TOKEN (GROQ_API_KEY optional)."
                        ],
                    )
                ],
                validation_reports=[],
                errors=["no_ai_provider"],
                metadata={
                    "engine": "ai_plan_codegen",
                    "elapsed_ms": round(elapsed * 1000, 1),
                },
            )

        execution = plan_from_text(original_request)
        execution_plan_meta = execution.to_dict()

        if not execution.ok:
            elapsed = time.perf_counter() - t0
            stages.append(
                StageResult.failed(
                    "execution_planner",
                    errors=[execution.error or "execution_plan_failed"],
                )
            )
            return GenerationResult(
                success=False,
                project_path=str(project_dir),
                stages=stages,
                validation_reports=[],
                errors=[execution.error or "execution_plan_failed"],
                metadata={
                    "engine": "ai_plan_codegen",
                    "execution_plan": execution_plan_meta,
                    "elapsed_ms": round(elapsed * 1000, 1),
                },
            )

        (project_dir / "execution_plan.json").write_text(
            __import__("json").dumps(execution.plan, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        stages.append(
            StageResult.ok(
                "execution_planner",
                outputs={
                    "model_used": execution.model_used,
                    "plan": execution.plan,
                    "warnings": execution.warnings,
                },
                warnings=list(execution.warnings or []),
            )
        )

        generated = generate_project_from_plan(execution.plan, project_dir)
        if generated.get("ok"):
            stages.append(StageResult.ok("plan_codegen", outputs=generated))
            elapsed = time.perf_counter() - t0
            return GenerationResult(
                success=True,
                project_path=str(project_dir),
                stages=stages,
                validation_reports=[],
                errors=[],
                metadata={
                    "engine": "ai_plan_codegen",
                    "execution_plan": execution_plan_meta,
                    "files_created": generated.get("files") or [],
                    "model": generated.get("model"),
                    "notes": generated.get("notes") or [],
                    "elapsed_ms": round(elapsed * 1000, 1),
                    "ready_for_token": True,
                },
            )

        stages.append(
            StageResult.failed(
                "plan_codegen",
                errors=list(generated.get("errors") or ["plan_codegen_failed"]),
            )
        )
        elapsed = time.perf_counter() - t0
        return GenerationResult(
            success=False,
            project_path=str(project_dir),
            stages=stages,
            validation_reports=[],
            errors=list(generated.get("errors") or ["plan_codegen_failed"]),
            metadata={
                "engine": "ai_plan_codegen",
                "execution_plan": execution_plan_meta,
                "model": generated.get("model"),
                "elapsed_ms": round(elapsed * 1000, 1),
            },
        )
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        stages.append(
            StageResult.failed(
                "ai_plan_codegen",
                errors=[f"{type(exc).__name__}:{exc}"[:500]],
            )
        )
        return GenerationResult(
            success=False,
            project_path=str(project_dir),
            stages=stages,
            validation_reports=[],
            errors=[f"{type(exc).__name__}:{exc}"[:500]],
            metadata={
                "engine": "ai_plan_codegen",
                "execution_plan": execution_plan_meta,
                "elapsed_ms": round(elapsed * 1000, 1),
            },
        )


__all__ = [
    "bootstrap",
    "build_configuration",
    "generate_bot",
    "PipelineOrchestrator",
    "EngineRegistry",
]
