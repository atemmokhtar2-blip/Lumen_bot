"""Formal Understanding Engine — DSL Relations & Operations extraction."""
from __future__ import annotations
from typing import Any, Dict

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine


class FormalUnderstandingEngine(BaseEngine):
    def __init__(self) -> None:
        super().__init__(
            name="formal_understanding",
            version="3.0.0",
            description="Custom DSL extraction: Relations & Operations from text",
            tags=["understanding", "formal", "dsl", "core"],
        )

    def execute(self, context: GenerationContext) -> StageResult:
        request = (context.request or "").strip()
        if not request:
            return self.failed(["Empty user request"])
        try:
            from ....formal_engine.dsl.extractor import extract_dsl
            from ....formal_engine.inference.engine import infer

            program = extract_dsl(request)
            inference = infer(program)
        except Exception as exc:
            return self.failed([f"DSL formal understanding failed: {exc}"])

        outputs: Dict[str, Any] = {
            "engine_path": "dsl_formal",
            "dsl_relations": len(program.relations),
            "dsl_operations": len(program.operations),
            "entities": [e.name for e in program.entities],
            "actions": list(inference.actions),
            "loops": [l.name for l in inference.loops],
            "decisions": [d.name for d in inference.decisions],
            "schemas": [s.table for s in inference.schemas],
            "source_hash": program.source_hash,
        }
        context.artefacts["dsl_program"] = program
        context.artefacts["dsl_inference"] = inference
        context.artefacts["formal_understanding_report"] = outputs
        return self.ok(outputs=outputs, metadata={"engine": "formal_understanding", "path": "dsl_formal"})
