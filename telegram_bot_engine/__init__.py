"""
Telegram Bot Generation Engine
==============================

Microservice pipeline:
  UnderstandingService (text → ProgramContract)
  → validate contract
  → CodegenService (ProgramContract → files)  [blind to raw text]
  → post_verify
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
    from pathlib import Path
    import tempfile
    import time

    from .core.result import GenerationResult, StageResult
    from .formal_engine.services.understanding_service import understand
    from .formal_engine.services.codegen_service import generate_from_contract

    t0 = time.perf_counter()
    request = (request or "").strip()
    if not request:
        return GenerationResult(
            success=False, project_path=None, stages=[], validation_reports=[],
            errors=["Empty request"], metadata={},
        )

    if work_dir is None:
        work_dir = Path(tempfile.mkdtemp(prefix="formal_bot_"))
    else:
        work_dir = Path(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)

    stages = []
    errors: list[str] = []

    # --- Service 1: Understanding ---
    try:
        contract, validation = understand(request)
        stages.append(
            StageResult.ok(
                "understanding_service",
                outputs={
                    "bot_name": contract.bot_name,
                    "bot_kind": contract.bot_kind.value,
                    "commands": [c.name for c in contract.commands],
                    "buttons": [b.label for b in contract.buttons],
                    "entities": [e.name for e in contract.entities],
                    "contract_ok": validation.ok,
                    "contract_errors": validation.errors,
                    "contract_warnings": validation.warnings,
                },
            )
        )
        if not validation.ok:
            errors.extend(validation.errors)
            return GenerationResult(
                success=False, project_path=None, stages=stages, validation_reports=[],
                errors=errors, metadata={"engine": "formal_microservices", "phase": "understanding"},
            )
    except Exception as exc:
        errors.append(f"UnderstandingService failed: {exc}")
        stages.append(StageResult.failed("understanding_service", errors=[str(exc)]))
        return GenerationResult(
            success=False, project_path=None, stages=stages, validation_reports=[],
            errors=errors, metadata={"engine": "formal_microservices"},
        )

    # --- Service 2: Codegen (blind to request text) ---
    project_dir = work_dir / "generated_bot"
    try:
        path, verify = generate_from_contract(contract, project_dir)
        files = sorted(str(p.relative_to(path)) for p in path.rglob("*") if p.is_file())
        stages.append(
            StageResult.ok(
                "codegen_service",
                outputs={
                    "project_path": str(path),
                    "files_created": files,
                    "verify": verify,
                },
            )
        )
        if not verify.get("ok"):
            errors.extend(verify.get("errors") or [])
    except Exception as exc:
        errors.append(f"CodegenService failed: {exc}")
        stages.append(StageResult.failed("codegen_service", errors=[str(exc)]))
        return GenerationResult(
            success=False, project_path=None, stages=stages, validation_reports=[],
            errors=errors, metadata={"engine": "formal_microservices"},
        )

    elapsed = time.perf_counter() - t0
    ok = not errors and bool(verify.get("ok", True))
    return GenerationResult(
        success=ok,
        project_path=str(path),
        stages=stages,
        validation_reports=[],
        errors=errors,
        metadata={
            "engine": "formal_microservices",
            "bot_name": contract.bot_name,
            "bot_type": contract.bot_kind.value,
            "files_created": files,
            "elapsed_ms": round(elapsed * 1000, 1),
            "button_count": (verify.get("info") or {}).get("button_count", 0),
            "verify_ok": verify.get("ok"),
            "buttons": [b.label for b in contract.buttons],
            "commands": [c.name for c in contract.commands],
            "contract_warnings": validation.warnings,
        },
    )
