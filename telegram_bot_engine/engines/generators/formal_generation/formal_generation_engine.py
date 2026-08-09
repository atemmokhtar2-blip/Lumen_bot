"""Formal Generation Engine — Formal Logic & DSL path (active)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine


class FormalGenerationEngine(BaseEngine):
    def __init__(self) -> None:
        super().__init__(
            name="formal_generation",
            version="3.0.0",
            description="DSL → Inference → Micro-Transpiler → Formal Verification",
            tags=["generation", "formal", "dsl", "core"],
        )

    def execute(self, context: GenerationContext) -> StageResult:
        request = (context.request or "").strip()
        if not request:
            return self.failed(["No request text for formal generation"])

        work_dir = Path(context.work_dir)
        project_dir = work_dir / "generated_bot"
        if project_dir.exists():
            import shutil
            shutil.rmtree(project_dir, ignore_errors=True)

        try:
            from ....formal_engine.pipeline_formal import build_from_text

            result = build_from_text(request, project_dir)
        except Exception as exc:
            return self.failed([f"Formal DSL generation failed: {exc}"])

        verify = result.verification
        if verify is None or not verify.ok:
            errs = list(verify.errors) if verify else ["verify missing"]
            return self.failed(errs)

        path = Path(result.out_dir)
        outputs: Dict[str, Any] = {
            "project_path": str(path),
            "bot_name": "dsl_bot",
            "commands": [],
            "framework": "python-telegram-bot",
            "files_created": sorted(
                str(p.relative_to(path)) for p in path.rglob("*") if p.is_file()
            ),
            "verify": verify.to_dict(),
            "dsl_relations": result.dsl_relations,
            "dsl_operations": result.dsl_operations,
            "engine_path": "dsl_formal",
        }
        # Expose path so downstream GitOperationsEngine can act on the generated project
        context.artefacts["generated_project_path"] = str(path)
        context.artefacts["repo_path"] = str(path)
        context.artefacts["formal_generation_report"] = outputs
        context.artefacts["dsl_inference"] = result.inference
        return self.ok(outputs=outputs, metadata={"engine": "formal_generation", "path": "dsl_formal"})
