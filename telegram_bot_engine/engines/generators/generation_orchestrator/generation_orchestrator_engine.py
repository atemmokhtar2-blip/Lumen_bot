"""REMOVED — replaced by Formal Generation Engine."""
from __future__ import annotations
from ...base.base_engine import BaseEngine

class GenerationOrchestratorEngine(BaseEngine):
    def __init__(self) -> None:
        super().__init__(name="generation_orchestrator", version="2.0.0", description="Replaced by formal_generation", tags=["formal", "removed"])
    def execute(self, context):
        from ..formal_generation.formal_generation_engine import FormalGenerationEngine
        return FormalGenerationEngine().execute(context)
