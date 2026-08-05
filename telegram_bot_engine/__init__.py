"""
Telegram Bot Generation Engine

Active path (Formal Logic & DSL Engine ONLY — zero LLM):
  text → Custom DSL → Inference → Micro-Transpiler → Formal Verification

HARD RULES:
  - No LLM / g4f / Understanding-AI on the generation path.
  - No fixed domain templates or canned command packs.
  - Commands, buttons, entities, rules come ONLY from user text.
  - Structural minima only: /start and /help.
"""

from __future__ import annotations

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


def generate_bot(request: str, work_dir=None):
    """
    Entry point used by the Telegram interface.

    Uses the Formal DSL pipeline exclusively.
    NO LLM. NO Understanding-AI. NO domain templates.
    """
    from pathlib import Path
    import tempfile
    import time

    from .core.result import GenerationResult, StageResult

    t0 = time.perf_counter()
    request = (request or "").strip()
    if not request:
        return GenerationResult(
            success=False,
            project_path=None,
            stages=[],
            validation_reports=[],
            errors=["Empty request"],
            metadata={},
        )

    work_dir = (
        Path(tempfile.mkdtemp(prefix="formal_bot_"))
        if work_dir is None
        else Path(work_dir)
    )
    work_dir.mkdir(parents=True, exist_ok=True)
    project_dir = work_dir / "generated_bot"
    project_dir.mkdir(parents=True, exist_ok=True)

    stages: list = []
    errors: list = []

    try:
        from .formal_engine.pipeline_formal import build_from_text

        # Formal path only — raw user text, no AI enrichment
        build = build_from_text(
            request,
            project_dir,
            grounding_text=request,
        )

        stages.append(
            StageResult.ok(
                "understanding_service",
                outputs={
                    "dsl_relations": build.dsl_relations,
                    "dsl_operations": build.dsl_operations,
                    "dsl_rules": build.dsl_rules,
                    "engine_path": "dsl_formal",
                    "ai_enriched": False,
                },
            )
        )

        g = getattr(build, "grounding", None)
        if g is not None:
            stages.append(
                StageResult.ok(
                    "grounding_gate",
                    outputs=g.to_dict() if hasattr(g, "to_dict") else {},
                    warnings=list(getattr(g, "warnings", None) or []),
                )
            )

        files = list(build.files or [])
        stages.append(
            StageResult.ok(
                "codegen_service",
                outputs={
                    "project_path": str(project_dir),
                    "files_created": files,
                    "file_count": len(files),
                },
            )
        )

        verify_ok = True
        verify_errors: list[str] = []
        if build.verification is not None:
            verify_ok = bool(build.verification.ok)
            verify_errors = list(getattr(build.verification, "errors", None) or [])
            if verify_ok:
                stages.append(
                    StageResult.ok(
                        "formal_verification",
                        outputs=build.verification.to_dict()
                        if hasattr(build.verification, "to_dict")
                        else {},
                    )
                )
            else:
                errors.extend(verify_errors[:10])
                stages.append(
                    StageResult.failed(
                        "formal_verification",
                        errors=verify_errors[:10],
                    )
                )
        else:
            stages.append(
                StageResult.ok("formal_verification", outputs={"skipped": True})
            )

        compile_ok = True
        compile_errors: list[str] = []
        try:
            import py_compile

            for py in sorted(project_dir.rglob("*.py")):
                try:
                    py_compile.compile(str(py), doraise=True)
                except py_compile.PyCompileError as e:
                    compile_ok = False
                    compile_errors.append(str(e)[:200])
            if compile_ok:
                stages.append(
                    StageResult.ok(
                        "py_compile",
                        outputs={"files": len(list(project_dir.rglob("*.py")))},
                    )
                )
            else:
                errors.extend(compile_errors[:5])
                stages.append(
                    StageResult.failed("py_compile", errors=compile_errors[:5])
                )
        except Exception as exc:
            compile_ok = False
            errors.append(f"py_compile failed: {exc}")
            stages.append(StageResult.failed("py_compile", errors=[str(exc)]))

        # Surface extracted commands for reporting
        cmd_names: list[str] = []
        try:
            from .formal_engine.dsl.extractor import extract_dsl
            prog = extract_dsl(request)
            cmd_names = [c.name for c in prog.commands]
        except Exception:
            pass

        path_str = str(project_dir) if project_dir.exists() else None
        ok = (
            bool(path_str)
            and verify_ok
            and compile_ok
            and not errors
            and len(files) > 0
        )

        elapsed = time.perf_counter() - t0
        return GenerationResult(
            success=ok,
            project_path=path_str,
            stages=stages,
            validation_reports=[],
            errors=errors,
            metadata={
                "engine": "dsl_formal",
                "files_created": files,
                "elapsed_ms": round(elapsed * 1000, 1),
                "compile_ok": compile_ok,
                "ready_for_token": bool(ok),
                "dsl_relations": build.dsl_relations,
                "dsl_operations": build.dsl_operations,
                "dsl_rules": build.dsl_rules,
                "verify_ok": verify_ok,
                "commands": cmd_names,
                "grounding": (
                    build.grounding.to_dict()
                    if getattr(build, "grounding", None) is not None
                    else None
                ),
                "understanding_ai": None,
            },
        )

    except Exception as exc:
        errors.append(f"Formal pipeline failed: {type(exc).__name__}: {exc}")
        stages.append(
            StageResult.failed("formal_pipeline", errors=[str(exc)[:300]])
        )
        elapsed = time.perf_counter() - t0
        return GenerationResult(
            success=False,
            project_path=None,
            stages=stages,
            validation_reports=[],
            errors=errors,
            metadata={
                "engine": "dsl_formal",
                "elapsed_ms": round(elapsed * 1000, 1),
            },
        )
