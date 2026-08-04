"""
Parse stage — extracts a structured intent from the user's request.

This stage is the entry point of the pipeline.  It receives the raw
natural-language request stored in the context and converts it into a
structured *intent* dictionary that later stages can rely on without
parsing free text again.

The actual parsing logic is delegated to an engine named
``"intent_parser"`` registered in the registry.  This keeps the stage
thin: it only coordinates, it does not understand natural language.

If no ``intent_parser`` engine is registered, the stage falls back to a
minimal heuristic so the pipeline can still run during early
development.
"""

from __future__ import annotations

from typing import List

from ...core.context import GenerationContext
from ...core.result import StageResult
from ...registry import EngineRegistry
from ..base_stage import BaseStage


class ParseStage(BaseStage):
    """Parses the user request into a structured intent."""

    stage_name = "parse"
    requires: List[str] = []
    provides: List[str] = ["intent"]

    def __init__(self, registry: EngineRegistry) -> None:
        super().__init__()
        self._registry = registry

    def execute(self, context: GenerationContext) -> StageResult:
        # 1) Analyzer first (priority 10) — deep request analysis
        analyzer = self._registry.get_engine("analyzer")
        if analyzer is not None:
            try:
                ares = analyzer.execute(context)
                if ares.success:
                    # analysis_report is set by the analyzer itself
                    pass
                else:
                    # Soft: continue to intent even if analyzer quality gate fails
                    pass
            except Exception:
                pass

        # 2) Intent parser (priority 20)
        parser = self._registry.get_engine("intent_parser")
        if parser is not None:
            result = parser.execute(context)
            if not result.success:
                return result
            intent = result.outputs.get("intent")
            if intent is None:
                return StageResult.failed(
                    self.name,
                    ["Intent parser did not produce an 'intent' output."],
                )
            context.set("intent", intent)
            return StageResult.ok(
                self.name,
                outputs={"intent": intent},
                metadata={"engine": parser.name, "analyzer": analyzer is not None},
            )

        # Fallback heuristic — enough to keep the pipeline moving.
        intent = self._fallback_parse(context.request)
        context.set("intent", intent)
        return StageResult.ok(
            self.name,
            outputs={"intent": intent},
            metadata={"source": "fallback"},
        )

    @staticmethod
    def _fallback_parse(request: str) -> dict:
        request = request.strip()
        return {
            "raw": request,
            "bot_type": "general",
            "keywords": [w for w in request.split() if len(w) > 2][:10],
            "language": "python",
        }


__all__ = ["ParseStage"]
