"""REMOVED — legacy code generation disabled. Formal Engine handles generation."""
from __future__ import annotations
from ...base.base_engine import BaseEngine

class GenerationStrategyEngine(BaseEngine):
    def __init__(self) -> None:
        super().__init__(name="generation_strategy", version="2.0.0", description="Disabled — formal engine only", tags=["formal", "removed"])
    def execute(self, context):
        return self.ok(outputs={"skipped": True, "reason": "replaced_by_formal_generation"}, metadata={"engine": "generation_strategy"})
