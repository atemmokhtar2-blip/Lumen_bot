"""REMOVED — replaced by Formal Understanding Engine."""
from __future__ import annotations
from ...base.base_engine import BaseEngine

class RequirementNormalizationEngine(BaseEngine):
    def __init__(self) -> None:
        super().__init__(name="requirement_normalization", version="2.0.0", description="Replaced by formal_understanding", tags=["formal", "removed"])
    def execute(self, context):
        from ..formal_understanding.formal_understanding_engine import FormalUnderstandingEngine
        return FormalUnderstandingEngine().execute(context)
