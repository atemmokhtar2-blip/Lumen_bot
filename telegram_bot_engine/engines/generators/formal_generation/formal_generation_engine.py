"""Formal Generation Engine — contract-based codegen (no domain templates)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from ....formal_engine.services.understanding_service.service import UnderstandingService
from ....formal_engine.services.planning_service.service import PlanningService
from ....formal_engine.services.codegen_service.service import generate_from_contract


class FormalGenerationEngine(BaseEngine):
    def __init__(self) -> None:
        super().__init__(
            name="formal_generation",
            version="2.0.0",
            description="Text-grounded ProgramContract codegen (no domain templates)",
            tags=["generation", "formal", "core"],
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
            contract, _val = UnderstandingService().run(request)
            contract, _plan = PlanningService().run(contract)
            path, verify = generate_from_contract(contract, project_dir)
        except Exception as exc:
            return self.failed([f"Formal generation failed: {exc}"])

        if not verify.get("ok"):
            return self.failed(list(verify.get("errors") or ["verify failed"]))

        outputs: Dict[str, Any] = {
            "project_path": str(path),
            "bot_name": contract.bot_name,
            "commands": [c.name for c in contract.commands],
            "framework": getattr(contract.architecture, "framework", ""),
            "files_created": sorted(
                str(p.relative_to(path)) for p in path.rglob("*") if p.is_file()
            ),
            "verify": verify,
        }
        context.artefacts["generated_project_path"] = str(path)
        context.artefacts["program_contract"] = contract
        context.artefacts["formal_generation_report"] = outputs
        return self.ok(outputs=outputs, metadata={"engine": "formal_generation"})
