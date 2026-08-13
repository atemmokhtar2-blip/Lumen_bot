"""
Compose blueprint stage — assembles a blueprint from the parsed intent.

This stage takes the ``intent`` artefact produced by the parse stage and
calls the ``"blueprint_composer"`` engine to build a complete
:class:`~telegram_bot_engine.blueprint.Blueprint`.

If no composer engine is registered, a minimal fallback blueprint is
produced so the pipeline can still progress during development.
"""

from __future__ import annotations

from typing import List

from ...blueprint import Blueprint, BotMeta, ProjectSpec
from ...core.context import GenerationContext
from ...core.result import StageResult
from ...registry import EngineRegistry
from ..base_stage import BaseStage


class ComposeBlueprintStage(BaseStage):
    """Composes a blueprint from the parsed intent."""

    stage_name = "compose_blueprint"
    requires: List[str] = ["intent"]
    provides: List[str] = ["blueprint"]

    def __init__(self, registry: EngineRegistry) -> None:
        super().__init__()
        self._registry = registry

    def execute(self, context: GenerationContext) -> StageResult:
        composer = self._registry.get_engine("blueprint_composer")
        if composer is not None:
            result = composer.execute(context)
            if not result.success:
                return result
            blueprint = result.outputs.get("blueprint")
            if blueprint is None:
                return StageResult.failed(
                    self.name,
                    ["Blueprint composer did not produce a 'blueprint' output."],
                )
            context.attach_blueprint(blueprint)
            context.set("blueprint", blueprint)
            return StageResult.ok(
                self.name,
                outputs={"blueprint": blueprint},
                metadata={"engine": composer.name},
            )

        blueprint = self._fallback_blueprint(context.get("intent"))
        context.attach_blueprint(blueprint)
        context.set("blueprint", blueprint)
        return StageResult.ok(
            self.name,
            outputs={"blueprint": blueprint},
            metadata={"source": "fallback"},
        )

    @staticmethod
    def _fallback_blueprint(intent: dict) -> Blueprint:
        raw = intent.get("raw", "telegram bot")
        name = raw.replace(" ", "_")[:40] or "generated_bot"
        meta = BotMeta(
            name=name,
            display_name=raw,
            description=raw,
            bot_type=intent.get("bot_type", "general"),
        )
        project = ProjectSpec(name=name, description=raw)
        return Blueprint(meta=meta, project=project)


__all__ = ["ComposeBlueprintStage"]
