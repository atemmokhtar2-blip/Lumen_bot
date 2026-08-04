"""Formal Understanding Engine — replaces semantic/requirement/intent/normalization."""
from __future__ import annotations
from typing import Any, Dict
from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from ....formal_engine.understanding.requirement_extractor import extract_formal_spec
from ....formal_engine.schemas.formal_spec import FormalBotSpec

class FormalUnderstandingEngine(BaseEngine):
    def __init__(self) -> None:
        super().__init__(
            name="formal_understanding",
            version="1.0.0",
            description="Deterministic formal understanding of any Telegram bot specification",
            tags=["understanding", "formal", "core"],
        )

    def execute(self, context: GenerationContext) -> StageResult:
        request = (context.request or "").strip()
        if not request:
            return self.failed(["Empty user request"])
        try:
            spec: FormalBotSpec = extract_formal_spec(request)
        except Exception as exc:
            return self.failed([f"Formal understanding failed: {exc}"])

        outputs: Dict[str, Any] = {
            "formal_bot_spec": spec.model_dump(mode="json"),
            "bot_name": spec.bot_name,
            "bot_type": spec.bot_type.value,
            "capabilities": list(spec.capabilities),
            "features": [f.model_dump() for f in spec.features],
            "languages": [l.value for l in spec.languages],
            "database": spec.database.value,
            "requires_payments": spec.requires_payments,
            "requires_admin_panel": spec.requires_admin_panel,
            "requires_async_queue": spec.requires_async_queue,
            "requires_file_handling": spec.requires_file_handling,
            "ui": spec.ui.model_dump(mode="json"),
            "quality": spec.quality.model_dump(mode="json"),
            "hard_constraints": list(spec.hard_constraints),
        }
        context.artefacts["formal_bot_spec"] = spec
        context.artefacts["formal_bot_spec_dict"] = outputs["formal_bot_spec"]
        context.artefacts["semantic_understanding_report"] = {
            "source": "formal_understanding",
            "bot_name": spec.bot_name,
            "bot_type": spec.bot_type.value,
            "unified_intent": spec.description[:500],
            "confidence": 1.0,
        }
        context.artefacts["requirement_intelligence_report"] = {
            "source": "formal_understanding",
            "features": outputs["features"],
            "capabilities": outputs["capabilities"],
        }
        context.artefacts["intent_report"] = {
            "source": "formal_understanding",
            "bot_type": spec.bot_type.value,
            "name": spec.bot_name,
        }
        return self.ok(outputs=outputs, metadata={"engine": "formal_understanding"})
