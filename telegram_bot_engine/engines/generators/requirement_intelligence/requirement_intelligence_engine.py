"""Requirement Intelligence — Formal (lazy)."""
from __future__ import annotations
from ...base.base_engine import BaseEngine

class RequirementIntelligenceEngine(BaseEngine):
    def __init__(self) -> None:
        super().__init__(name="requirement_intelligence", version="2.0.0", description="Formal requirements", tags=["formal"])
    def execute(self, context):
        if context.artefacts.get("formal_bot_spec") is not None:
            return self.ok(outputs={"reused": True}, metadata={"engine": "requirement_intelligence"})
        from ..formal_understanding.formal_understanding_engine import FormalUnderstandingEngine
        return FormalUnderstandingEngine().execute(context)
