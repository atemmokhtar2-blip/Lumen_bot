"""
Telegram Bot Generation Engine
==============================

Main entry: generate_bot() — powered exclusively by the Formal Engine
(deterministic understanding + clean code generation). No legacy AI/heuristic
understanding or old code-generation engines on the hot path.
"""

from __future__ import annotations

__all__ = [
    "bootstrap",
    "build_configuration",
    "generate_bot",
    "PipelineOrchestrator",
    "EngineRegistry",
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
    Generate a complete Telegram bot project from a natural-language description.

    Uses ONLY the Formal Engine:
      1. Formal understanding → FormalBotSpec
      2. Formal generation → clean project on disk
    """
    from pathlib import Path
    import tempfile
    import time

    from .core.result import GenerationResult, StageResult
    from .formal_engine.understanding.requirement_extractor import extract_formal_spec
    from .formal_engine.generation.project_generator import generate_project

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

    if work_dir is None:
        work_dir = Path(tempfile.mkdtemp(prefix="formal_bot_"))
    else:
        work_dir = Path(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)

    stages = []
    errors = []

    # --- Stage 1: Formal Understanding ---
    try:
        spec = extract_formal_spec(request)
        stages.append(
            StageResult.ok(
                "formal_understanding",
                outputs={
                    "bot_name": spec.bot_name,
                    "bot_type": spec.bot_type.value,
                    "intent": {
                        "raw": request,
                        "bot_type": spec.bot_type.value,
                        "bot_name": spec.bot_name,
                        "features": [getattr(f, "name", str(f)) for f in spec.features],
                        "commands": [
                            {"name": getattr(c, "command", "start"), "description": getattr(c, "description", "")}
                            for c in (spec.ui.commands if spec.ui else [])
                        ],
                        "source": "formal_understanding",
                    },
                },
            )
        )
    except Exception as exc:
        errors.append(f"Formal understanding failed: {exc}")
        stages.append(StageResult.failed("formal_understanding", errors=[str(exc)]))
        return GenerationResult(
            success=False,
            project_path=None,
            stages=stages,
            validation_reports=[],
            errors=errors,
            metadata={"engine": "formal"},
        )

    # --- Stage 2: Formal Generation ---
    project_dir = work_dir / "generated_bot"
    try:
        path = generate_project(spec, project_dir)
        files = sorted(str(p.relative_to(path)) for p in path.rglob("*") if p.is_file())
        stages.append(
            StageResult.ok(
                "formal_generation",
                outputs={
                    "project_path": str(path),
                    "files_created": files,
                    "bot_name": spec.bot_name,
                    "bot_type": spec.bot_type.value,
                },
            )
        )
    except Exception as exc:
        errors.append(f"Formal generation failed: {exc}")
        stages.append(StageResult.failed("formal_generation", errors=[str(exc)]))
        return GenerationResult(
            success=False,
            project_path=None,
            stages=stages,
            validation_reports=[],
            errors=errors,
            metadata={"engine": "formal"},
        )

    elapsed = time.perf_counter() - t0
    return GenerationResult(
        success=True,
        project_path=str(path),
        stages=stages,
        validation_reports=[],
        errors=[],
        metadata={
            "engine": "formal",
            "bot_name": spec.bot_name,
            "bot_type": spec.bot_type.value,
            "files_created": files,
            "elapsed_ms": round(elapsed * 1000, 1),
        },
    )
