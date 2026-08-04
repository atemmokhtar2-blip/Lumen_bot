"""Semantic Understanding — Formal (lazy)."""
from __future__ import annotations
from ...base.base_engine import BaseEngine

class SemanticUnderstandingEngine(BaseEngine):
    def __init__(self) -> None:
        super().__init__(name="semantic_understanding", version="2.0.0", description="Formal semantic", tags=["formal"])
    def execute(self, context):
        from ..formal_understanding.formal_understanding_engine import FormalUnderstandingEngine
        return FormalUnderstandingEngine().execute(context)
