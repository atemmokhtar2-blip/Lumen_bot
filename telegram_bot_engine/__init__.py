"""
Telegram Bot Generation Engine

Active path (Formal Logic & DSL Engine):
  text → Custom DSL → Inference → Micro-Transpiler → Formal Verification

Git/Repo engines kept for repository operations.
The old hybrid (ProgramContract unpack) path is retired — it caused
"cannot unpack non-iterable UnderstandingResult" because understand()
returns a single UnderstandingResult, not a (contract, validation) tuple.
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

    Uses the Formal DSL pipeline exclusively (no LLM, no ProgramContract unpack).
    Returns GenerationResult compatible with main.py reporting.

    HARD RULE — no fixed domain templates:
      Commands, buttons, entities, rules, flows, and handlers come ONLY from
      the user text. Never inject shop/ticket/ecommerce/education packs or
      canned domain skeletons.
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

    # ------------------------------------------------------------------
    # Formal path: DSL → Inference → Transpile → Verify
    # ------------------------------------------------------------------
    try:
        from .formal_engine.pipeline_formal import build_from_text

        build = build_from_text(request, project_dir)

        # Understanding stage (DSL extraction summary)
        stages.append(
            StageResult.ok(
                "understanding_service",
                outputs={
                    "dsl_relations": build.dsl_relations,
                    "dsl_operations": build.dsl_operations,
                    "dsl_rules": build.dsl_rules,
                    "engine_path": "dsl_formal",
                },
            )
        )

        # Codegen stage (transpiler output)
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

        # Verification stage
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

        # py_compile hard structural test
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
