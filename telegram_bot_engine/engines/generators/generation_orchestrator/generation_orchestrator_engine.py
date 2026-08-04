"""Generation Orchestrator — Formal Generation (lazy)."""
from __future__ import annotations
from ...base.base_engine import BaseEngine

class GenerationOrchestratorEngine(BaseEngine):
    def __init__(self) -> None:
        super().__init__(name="generation_orchestrator", version="2.0.0", description="Formal generation orchestrator", tags=["formal"])
    def execute(self, context):
        if context.artefacts.get("generated_project_path"):
            return self.ok(outputs={"reused": context.artefacts["generated_project_path"]}, metadata={"engine": "generation_orchestrator"})
        from ..formal_generation.formal_generation_engine import FormalGenerationEngine
        return FormalGenerationEngine().execute(context)
