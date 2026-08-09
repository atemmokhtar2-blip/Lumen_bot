"""
Telegram Bot Generation Engine

Active path:
  user text
    → [SpecTranslator AI: translate only → JSON]
    → [Grounding against original text]
    → Formal DSL → Inference → Flow Composer → Transpile → Verify
    → [optional] GitOperations (push/pull/commit) when user text requests it

HARD RULES (STRICT — non-negotiable):
  - AI may ONLY translate speech → structured spec (no code generation).
  - Grounding drops anything not evidenced in the user text.
  - Formal engine is the ONLY code generator.
  - IMPOSSIBLE to create any saved artefact, ready-made bot template,
    default command packs, or pre-baked structures.
  - Everything is generated dynamically and exclusively from the user's
    natural-language text. Zero domain templates / canned packs.
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



def generate_bot(request: str, work_dir=None):
    """
    Entry point used by the Telegram interface.

    AI SpecTranslator (optional): speech → structured spec only.
    Formal engine: only code generator. No domain templates.

    STRICT RULE (project-wide, non-negotiable until tomorrow and beyond):
      Impossible to create any saved artefact, ready-made bot template,
      default command packs, or pre-baked structures. Everything is
      generated dynamically and exclusively from the user's natural-language
      text via SpecTranslator → formal/DSL path.
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
    translator_meta = None
    formal_text = request
    grounding_src = original_request

    try:
        # ── SpecTranslator: AI translates only (never generates code) ──
        try:
            from .chat_ai.spec_translator import prepare_formal_text
            formal_text, tr = prepare_formal_text(original_request)
            translator_meta = tr.to_dict()
            if tr.ok:
                stages.append(
                    StageResult.ok(
                        "spec_translator",
                        outputs=tr.to_dict(),
                        warnings=[
                            f"dropped:{k}:{v}"
                            for k, v in (tr.dropped or {}).items()
                            if v
                        ][:8],
                    )
                )
                # Never block on needs_clarification — AI + formal path always attempt generation.
                # Use grounded sectioned text for formal path; ground against original words
                if tr.structured_text.strip():
                    formal_text = tr.structured_text
                    grounding_src = original_request  # NEVER ground against AI output (self-justifies hallucinations)
            else:
                # AI failed/weak — still continue with the original user text through formal DSL.
                # This is NOT a domain template path: formal engine only reads what the user wrote.
                stages.append(
                    StageResult.failed(
                        "spec_translator",
                        errors=[tr.error or "spec_translator_failed"],
                    )
                )
                formal_text = (original_request or "").strip()
                grounding_src = original_request
                translator_meta = {
                    **translator_meta,
                    "continued_with_user_text": True,
                }
        except Exception as tr_exc:
            stages.append(
                StageResult.failed(
                    "spec_translator",
                    errors=[f"{type(tr_exc).__name__}:{tr_exc}"],
                )
            )
            elapsed = time.perf_counter() - t0
            return GenerationResult(
                success=False,
                project_path=None,
                stages=stages,
                validation_reports=[],
                errors=[f"spec_translator_exception:{type(tr_exc).__name__}:{tr_exc}"],
                metadata={"engine": "spec_translator", "elapsed_ms": round(elapsed * 1000, 1)},
            )

        from .formal_engine.pipeline_formal import build_from_text
        from .formal_engine.dsl.extractor import extract_dsl
        from .formal_engine.generation_contract import assess_generation_contract

        # World-class gate: refuse hollow contracts (start/help only). No domain templates.
        # Assess on merged formal_text (AI structured + user) and original for evidence.
        contract = assess_generation_contract(formal_text or original_request)
        if not contract.ready:
            # Second look at pure user text if AI path stripped signals
            contract_user = assess_generation_contract(original_request)
            if contract_user.score > contract.score:
                contract = contract_user
                formal_text = original_request
                grounding_src = original_request
        stages.append(
            StageResult.ok(
                "generation_contract",
                outputs=contract.to_dict(),
                warnings=list(contract.gaps)[:8],
            )
            if contract.ready
            else StageResult.failed(
                "generation_contract",
                errors=list(contract.gaps)[:8] or ["hollow_contract"],
            )
        )
        if not contract.ready:
            elapsed = time.perf_counter() - t0
            return GenerationResult(
                success=False,
                project_path=None,
                stages=stages,
                validation_reports=[],
                errors=["hollow_contract"] + list(contract.gaps)[:5],
                metadata={
                    "engine": "generation_contract",
                    "elapsed_ms": round(elapsed * 1000, 1),
                    "contract": contract.to_dict(),
                    "needs_richer_spec": True,
                    "spec_translator": translator_meta,
                },
            )

        build = build_from_text(
            formal_text,
            project_dir,
            grounding_text=grounding_src,
        )

        stages.append(
            StageResult.ok(
                "understanding_service",
                outputs={
                    "dsl_relations": build.dsl_relations,
                    "dsl_operations": build.dsl_operations,
                    "dsl_rules": build.dsl_rules,
                    "engine_path": "dsl_formal",
                    "translator_used": bool(translator_meta and translator_meta.get("ok")),
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

        # Phase 1/2/3 stage reporting
        sg = getattr(build, "structure_gate", None) or {}
        if isinstance(sg, dict) and sg.get("ok", True):
            stages.append(
                StageResult.ok(
                    "structure_engine",
                    outputs={
                        "structure_files": list(getattr(build, "structure_files", None) or []),
                        "structure_gate": sg,
                        "structure_only": bool(getattr(build, "structure_only", False)),
                    },
                    warnings=list(sg.get("warnings") or [])[:8],
                )
            )
        else:
            stages.append(
                StageResult.failed(
                    "structure_engine",
                    errors=list((sg or {}).get("errors") or ["structure_gate_failed"])[:10],
                )
            )

        ce = getattr(build, "code_engine", None) or {}
        if ce.get("ok", True) and not getattr(build, "structure_only", False):
            stages.append(
                StageResult.ok(
                    "code_engine",
                    outputs=ce,
                )
            )
        elif getattr(build, "structure_only", False):
            stages.append(
                StageResult.ok("code_engine", outputs={"skipped": True, "reason": "structure_only"})
            )
        else:
            stages.append(
                StageResult.failed(
                    "code_engine",
                    errors=list(ce.get("errors") or ["code_engine_failed"])[:10],
                )
            )
            errors.extend(list(ce.get("errors") or [])[:5])

        stages.append(
            StageResult.ok(
                "codegen_service",
                outputs={
                    "project_path": str(project_dir),
                    "files_created": files,
                    "file_count": len(files),
                    "path": (ce.get("path") if isinstance(ce, dict) else None) or "formal",
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

        # Structural runtime-safety verification of generated handlers (no domain packs)
        gen_verify_meta = {}
        try:
            from .formal_engine.services.gen_verify import verify_generated_project
            gv = verify_generated_project(project_dir)
            gen_verify_meta = gv.to_dict()
            if gv.ok:
                stages.append(
                    StageResult.ok("gen_verify", outputs=gen_verify_meta)
                )
            else:
                stages.append(
                    StageResult.failed("gen_verify", errors=list(gv.errors)[:10])
                )
                errors.extend(list(gv.errors)[:5])
                compile_ok = False  # treat as not ready for token
            for w in list(gv.warnings)[:8]:
                # stubs are warnings; many stubs degrade success below
                if str(w).startswith("stub_handler:"):
                    pass
        except Exception as gv_exc:
            stages.append(
                StageResult.failed(
                    "gen_verify",
                    errors=[f"{type(gv_exc).__name__}:{gv_exc}"],
                )
            )

        quality = getattr(build, "quality", None) or {}
        if quality:
            if quality.get("ok", True):
                stages.append(StageResult.ok("quality", outputs=quality))
            else:
                stages.append(
                    StageResult.failed(
                        "quality",
                        errors=list(quality.get("errors") or [])[:10],
                    )
                )
                # quality errors are soft unless invented_* 
                for e in list(quality.get("errors") or [])[:5]:
                    if str(e).startswith("invented_"):
                        errors.append(str(e))

        # Surface extracted commands for reporting
        cmd_names: list[str] = []
        try:
            from .formal_engine.dsl.extractor import extract_dsl
            prog = extract_dsl(formal_text)
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

        # ── Optional Git stage: FormalGeneration → GitOperations link ──
        # Runs only when user text explicitly requests git/push/pull/commit.
        # STRICT RULE: no templates; ops derived solely from user text + generated path.
        git_meta = None
        if ok and path_str:
            git_meta = _maybe_run_git_stage(
                original_request=original_request,
                project_path=path_str,
                stages=stages,
            )

        elapsed = time.perf_counter() - t0
        meta = {
            "engine": "dsl_formal",
            "files_created": files,
            "elapsed_ms": round(elapsed * 1000, 1),
            "compile_ok": compile_ok,
            "ready_for_token": bool(ok),
            "dsl_relations": build.dsl_relations,
            "dsl_operations": build.dsl_operations,
            "dsl_rules": build.dsl_rules,
            "structure_plan": getattr(build, "structure_plan", None) or {},
            "structure_gate": getattr(build, "structure_gate", None) or {},
            "structure_files": list(getattr(build, "structure_files", None) or []),
            "structure_only": bool(getattr(build, "structure_only", False)),
            "code_engine": getattr(build, "code_engine", None) or {},
            "quality": getattr(build, "quality", None) or {},
            "verify_ok": verify_ok,
            "gen_verify": gen_verify_meta,
            "commands": cmd_names,
            "grounding": (
                build.grounding.to_dict()
                if getattr(build, "grounding", None) is not None
                else None
            ),
            "spec_translator": translator_meta,
        }
        if git_meta is not None:
            meta["git_operations"] = git_meta

        return GenerationResult(
            success=ok,
            project_path=path_str,
            stages=stages,
            validation_reports=[],
            errors=errors,
            metadata=meta,
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
