"""Intent Parser — Formal Understanding (lazy)."""
from __future__ import annotations
from ..base.base_engine import BaseEngine

class IntentParserEngine(BaseEngine):
    def __init__(self) -> None:
        super().__init__(name="intent_parser", version="2.0.0", description="Formal intent", tags=["formal"])
    def execute(self, context):
        if context.artefacts.get("formal_bot_spec") is not None:
            return self.ok(outputs={"reused": True}, metadata={"engine": "intent_parser"})
        from .formal_understanding.formal_understanding_engine import FormalUnderstandingEngine
        return FormalUnderstandingEngine().execute(context)
