"""
Telegram Bot Generation Engine

Active path (spec-driven, v2):
  user text
    → [SpecTranslator v2: 4-pass AI translate → RichSpec JSON]
    → [Evidence grounding: drop items not traceable to user text]
    → [ContractBuilder: RichSpec → InferenceResult + ProgramContract]
    → [SpecDrivenTranspiler: generate code from spec]
    → [Formal Verification: syntax + handlers + compile]

Fallback path (if AI unavailable):
  user text
    → [SpecTranslator v1: AI → lossy text]
    → [Old DSL pipeline: extract → ground → infer → transpile → verify]

HARD RULES:
  - AI may ONLY translate speech → structured spec (no code generation).
  - Grounding drops anything not evidenced in the user text.
  - The formal engine is the ONLY code generator.
  - No domain templates / canned packs / hardcoded verb/stem classification.
  - Command kind, entity, fields, post_action all come from the AI spec.
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


def _run_spec_driven_pipeline(
    original_request: str,
    project_dir,
    t0: float,
    stages: list,
    errors: list,
):
    """
    New spec-driven pipeline:
      SpecTranslator v2 → RichSpec → ContractBuilder → SpecTranspiler → Verify
    Returns (success, metadata_dict) or raises.
    """
    import time
    from .core.result import StageResult
    from .chat_ai.spec_translator_v2 import prepare_rich_spec
    from .formal_engine.spec_pipeline.pipeline import build_from_spec_pipeline

    # ── SpecTranslator v2: AI translates to RichSpec ──
    rich_spec = None
    translator_meta = None
    try:
        rich_spec, tr = prepare_rich_spec(original_request)
        translator_meta = tr.to_dict()
        if tr.ok and rich_spec is not None:
            stages.append(
                StageResult.ok(
                    "spec_translator_v2",
                    outputs=tr.to_dict(),
                    warnings=[
                        f"dropped:{k}:{len(v)}" for k, v in (tr.dropped or {}).items() if v
                    ][:8] + (tr.validation_warnings[:4] if tr.validation_warnings else []),
                )
            )
            # Check if needs clarification
            if tr.needs_clarification and not rich_spec.commands:
                elapsed = time.perf_counter() - t0
                return False, {
                    "engine": "spec_driven",
                    "needs_clarification": True,
                    "clarification_questions": list(tr.clarification_questions or []),
                    "spec_translator": translator_meta,
                    "elapsed_ms": round(elapsed * 1000, 1),
                }
        else:
            stages.append(
                StageResult.ok(
                    "spec_translator_v2",
                    outputs=tr.to_dict(),
                    warnings=[tr.error or "no_rich_spec_fallback"],
                )
            )
    except Exception as tr_exc:
        stages.append(
            StageResult.ok(
                "spec_translator_v2",
                outputs={"ok": False, "error": f"{type(tr_exc).__name__}:{tr_exc}"},
                warnings=["translator_v2_exception"],
            )
        )
        return None, {"translator_failed": True}  # signal fallback

    if rich_spec is None:
        return None, {"translator_failed": True}  # signal fallback

    # ── Spec-driven build pipeline ──
    build = build_from_spec_pipeline(rich_spec, project_dir)

    stages.append(
        StageResult.ok(
            "understanding_service",
            outputs={
                "commands": len(build.commands),
                "entities": len(build.entities),
                "engine_path": "spec_driven",
                "translator_used": True,
                "contract_ok": build.contract_ok,
            },
        )
    )

    # Grounding stage (already done in translator, report it)
    stages.append(
        StageResult.ok(
            "grounding_gate",
            outputs={"method": "evidence_based", "items": len(build.commands)},
        )
    )

    stages.append(
        StageResult.ok(
            "codegen_service",
            outputs={
                "project_path": str(project_dir),
                "files_created": build.files,
                "file_count": len(build.files),
            },
        )
    )

    # Verification
    verify_ok = True
    verify_errors: list[str] = []
    if build.verification is not None:
        verify_ok = bool(build.verification.ok)
        verify_errors = list(getattr(build.verification, "errors", None) or [])
        if verify_ok:
            stages.append(
                StageResult.ok(
                    "formal_verification",
                    outputs=build.verification.to_dict() if hasattr(build.verification, "to_dict") else {},
                )
            )
        else:
            errors.extend(verify_errors[:10])
            stages.append(StageResult.failed("formal_verification", errors=verify_errors[:10]))
    else:
        stages.append(StageResult.ok("formal_verification", outputs={"skipped": True}))

    # py_compile
    import py_compile
    compile_ok = True
    compile_errors: list[str] = []
    try:
        for py in sorted(project_dir.rglob("*.py")):
            try:
                py_compile.compile(str(py), doraise=True)
            except py_compile.PyCompileError as e:
                compile_ok = False
                compile_errors.append(str(e)[:200])
        if compile_ok:
            stages.append(StageResult.ok("py_compile", outputs={"files": len(list(project_dir.rglob("*.py")))}))
        else:
            errors.extend(compile_errors[:5])
            stages.append(StageResult.failed("py_compile", errors=compile_errors[:5]))
    except Exception as exc:
        compile_ok = False
        errors.append(f"py_compile failed: {exc}")
        stages.append(StageResult.failed("py_compile", errors=[str(exc)]))

    path_str = str(project_dir) if project_dir.exists() else None
    ok = bool(path_str) and verify_ok and compile_ok and not errors and len(build.files) > 0
    elapsed = time.perf_counter() - t0

    metadata = {
        "engine": "spec_driven",
        "files_created": build.files,
        "elapsed_ms": round(elapsed * 1000, 1),
        "compile_ok": compile_ok,
        "ready_for_token": bool(ok),
        "verify_ok": verify_ok,
        "commands": build.commands,
        "entities": build.entities,
        "contract_ok": build.contract_ok,
        "contract_warnings": build.contract_warnings,
        "spec_validation_warnings": build.spec_validation_warnings,
        "spec_translator": translator_meta,
    }
    return ok, metadata


def _run_fallback_pipeline(
    original_request: str,
    project_dir,
    t0: float,
    stages: list,
    errors: list,
):
    """
    Fallback: old DSL pipeline (extract → ground → infer → transpile → verify).
    Used only when the spec-driven translator is unavailable.
    """
    import time
    import py_compile
    from .core.result import StageResult
    from .chat_ai.spec_translator import prepare_formal_text
    from .formal_engine.pipeline_formal import build_from_text

    formal_text = original_request
    grounding_src = original_request
    translator_meta = None

    try:
        formal_text, tr = prepare_formal_text(original_request)
        translator_meta = tr.to_dict()
        if tr.ok:
            stages.append(StageResult.ok("spec_translator", outputs=tr.to_dict(), warnings=[]))
            if tr.needs_clarification and not (tr.grounded_json or {}).get("commands"):
                elapsed = time.perf_counter() - t0
                return False, {
                    "engine": "dsl_formal",
                    "needs_clarification": True,
                    "clarification_questions": list(tr.clarification_questions or []),
                    "spec_translator": translator_meta,
                    "elapsed_ms": round(elapsed * 1000, 1),
                }
            if tr.structured_text.strip():
                formal_text = tr.structured_text
                grounding_src = original_request
        else:
            stages.append(StageResult.ok("spec_translator", outputs=tr.to_dict(), warnings=[tr.error or "fallback_raw_text"]))
    except Exception as tr_exc:
        stages.append(StageResult.ok("spec_translator", outputs={"ok": False, "error": f"{type(tr_exc).__name__}:{tr_exc}"}, warnings=["translator_exception_fallback"]))

    build = build_from_text(formal_text, project_dir, grounding_text=grounding_src)
    stages.append(StageResult.ok("understanding_service", outputs={"dsl_relations": build.dsl_relations, "dsl_operations": build.dsl_operations, "dsl_rules": build.dsl_rules, "engine_path": "dsl_formal", "translator_used": bool(translator_meta and translator_meta.get("ok"))}))

    g = getattr(build, "grounding", None)
    if g is not None:
        stages.append(StageResult.ok("grounding_gate", outputs=g.to_dict() if hasattr(g, "to_dict") else {}, warnings=list(getattr(g, "warnings", None) or [])))

    files = list(build.files or [])
    stages.append(StageResult.ok("codegen_service", outputs={"project_path": str(project_dir), "files_created": files, "file_count": len(files)}))

    verify_ok = True
    verify_errors: list[str] = []
    if build.verification is not None:
        verify_ok = bool(build.verification.ok)
        verify_errors = list(getattr(build.verification, "errors", None) or [])
        if verify_ok:
            stages.append(StageResult.ok("formal_verification", outputs=build.verification.to_dict() if hasattr(build.verification, "to_dict") else {}))
        else:
            errors.extend(verify_errors[:10])
            stages.append(StageResult.failed("formal_verification", errors=verify_errors[:10]))
    else:
        stages.append(StageResult.ok("formal_verification", outputs={"skipped": True}))

    compile_ok = True
    compile_errors: list[str] = []
    try:
        for py in sorted(project_dir.rglob("*.py")):
            try:
                py_compile.compile(str(py), doraise=True)
            except py_compile.PyCompileError as e:
                compile_ok = False
                compile_errors.append(str(e)[:200])
        if compile_ok:
            stages.append(StageResult.ok("py_compile", outputs={"files": len(list(project_dir.rglob("*.py")))}))
        else:
            errors.extend(compile_errors[:5])
            stages.append(StageResult.failed("py_compile", errors=compile_errors[:5]))
    except Exception as exc:
        compile_ok = False
        errors.append(f"py_compile failed: {exc}")
        stages.append(StageResult.failed("py_compile", errors=[str(exc)]))

    cmd_names: list[str] = []
    try:
        from .formal_engine.dsl.extractor import extract_dsl
        prog = extract_dsl(formal_text)
        cmd_names = [c.name for c in prog.commands]
    except Exception:
        pass

    path_str = str(project_dir) if project_dir.exists() else None
    ok = bool(path_str) and verify_ok and compile_ok and not errors and len(files) > 0
    elapsed = time.perf_counter() - t0

    metadata = {
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
        "grounding": build.grounding.to_dict() if getattr(build, "grounding", None) is not None else None,
        "spec_translator": translator_meta,
    }
    return ok, metadata


def generate_bot(request: str, work_dir=None):
    """
    Entry point used by the Telegram interface.

    Tries the spec-driven pipeline (v2) first:
      AI → RichSpec → ContractBuilder → SpecTranspiler → Verify

    Falls back to the old DSL pipeline only if the v2 translator is unavailable.
    """
    from pathlib import Path
    import tempfile
    import time

    from .core.result import GenerationResult, StageResult

    t0 = time.perf_counter()
    original_request = (request or "").strip()
    request = original_request
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
        # ── Try spec-driven pipeline (v2) first ──
        ok, metadata = _run_spec_driven_pipeline(
            original_request, project_dir, t0, stages, errors
        )

        # If v2 translator failed, fall back to old pipeline
        if ok is None and metadata.get("translator_failed"):
            # Reset for fallback
            stages_append = list(stages)
            # Clean project dir for fresh fallback build
            for f in project_dir.rglob("*"):
                if f.is_file():
                    f.unlink()
            ok, metadata = _run_fallback_pipeline(
                original_request, project_dir, t0, stages, errors
            )

        if ok is None:
            # shouldn't happen, but guard
            ok = False
            metadata = metadata or {}

        path_str = str(project_dir) if project_dir.exists() else None
        return GenerationResult(
            success=bool(ok),
            project_path=path_str,
            stages=stages,
            validation_reports=[],
            errors=errors,
            metadata=metadata,
        )

    except Exception as exc:
        errors.append(f"Pipeline failed: {type(exc).__name__}: {exc}")
        stages.append(StageResult.failed("pipeline", errors=[str(exc)[:300]]))
        elapsed = time.perf_counter() - t0
        return GenerationResult(
            success=False,
            project_path=None,
            stages=stages,
            validation_reports=[],
            errors=errors,
            metadata={
                "engine": "spec_driven",
                "elapsed_ms": round(elapsed * 1000, 1),
            },
        )
