"""Formal Generation Engine — replaces project builder / generation orchestrator."""
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict
from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from ....formal_engine.schemas.formal_spec import FormalBotSpec
from ....formal_engine.generation.project_generator import generate_project
from ....formal_engine.understanding.requirement_extractor import extract_formal_spec

class FormalGenerationEngine(BaseEngine):
    def __init__(self) -> None:
        super().__init__(
            name="formal_generation",
            version="1.0.0",
            description="Deterministic clean code generation for any Telegram bot type",
            tags=["generation", "formal", "core"],
        )

    def execute(self, context: GenerationContext) -> StageResult:
        spec = context.artefacts.get("formal_bot_spec")
        if not isinstance(spec, FormalBotSpec):
            request = (context.request or "").strip()
            if not request:
                return self.failed(["No request and no formal_bot_spec in context"])
            try:
                spec = extract_formal_spec(request)
                context.artefacts["formal_bot_spec"] = spec
            except Exception as exc:
                return self.failed([f"Failed to build FormalBotSpec: {exc}"])

        work_dir = Path(context.work_dir)
        project_dir = work_dir / "generated_bot"
        if project_dir.exists():
            import shutil
            shutil.rmtree(project_dir, ignore_errors=True)

        try:
            path = generate_project(spec, project_dir)
        except Exception as exc:
            return self.failed([f"Formal generation failed: {exc}"])

        outputs: Dict[str, Any] = {
            "project_path": str(path),
            "bot_name": spec.bot_name,
            "bot_type": spec.bot_type.value,
            "database": spec.database.value,
            "requires_payments": spec.requires_payments,
            "requires_admin_panel": spec.requires_admin_panel,
            "requires_async_queue": spec.requires_async_queue,
            "requires_file_handling": spec.requires_file_handling,
            "files_created": sorted(str(p.relative_to(path)) for p in path.rglob("*") if p.is_file()),
        }
        context.artefacts["generated_project_path"] = str(path)
        context.artefacts["formal_generation_report"] = outputs
        return self.ok(outputs=outputs, metadata={"engine": "formal_generation"})
