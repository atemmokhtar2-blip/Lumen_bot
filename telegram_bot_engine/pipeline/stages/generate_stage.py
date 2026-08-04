"""
Generate stage — runs all generator engines to materialise the project.

This stage iterates over every registered engine (except the intent
parser and blueprint composer which already ran) and asks it to
contribute to the generated project.  Each engine writes artefacts to
the context's work directory using the builders.

Engines declare an optional ``order`` in their metadata so that the
stage can run them in a deterministic sequence (e.g. scaffolding
before handlers).
"""

from __future__ import annotations

from typing import List

from ...core.context import GenerationContext
from ...core.result import StageResult
from ...registry import EngineRegistry
from ..base_stage import BaseStage


# Engines that are part of the "understanding" phase and should not run
# during generation.
_PRECEDING_ENGINES = {"intent_parser", "blueprint_composer"}


class GenerateStage(BaseStage):
    """Runs all generator engines to build the project files."""

    stage_name = "generate"
    requires: List[str] = ["blueprint"]
    provides: List[str] = ["generated_files"]

    def __init__(self, registry: EngineRegistry) -> None:
        super().__init__()
        self._registry = registry

    def execute(self, context: GenerationContext) -> StageResult:
        if context.blueprint is None:
            return StageResult.failed(
                self.name, ["No blueprint attached to the context."]
            )

        engines = [
            e for e in self._registry.engines()
            if e.name not in _PRECEDING_ENGINES
        ]
        # Sort by optional ``order`` metadata (default 100).
        engines.sort(key=lambda e: getattr(e, "metadata", {}).get("order", 100))

        errors: List[str] = []
        warnings: List[str] = []
        ran: List[str] = []

        for engine in engines:
            self._log.info("Running generator engine", {"engine": engine.name})
            try:
                result = engine.execute(context)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Engine '{engine.name}' crashed: {exc}")
                self._log.exception("Generator engine crashed",
                                    {"engine": engine.name})
                continue
            ran.append(engine.name)
            if not result.success:
                # Soft-fail quality gates: keep them as warnings so the
                # pipeline can still package whatever was produced.
                # Only hard-fail when an engine crashed or reported a
                # true blocking error (missing blueprint / crash).
                hard = [
                    e for e in (result.errors or [])
                    if "crashed" in e.lower()
                    or "no blueprint" in e.lower()
                ]
                soft = [
                    e for e in (result.errors or [])
                    if e not in hard
                ]
                errors.extend(hard)
                warnings.extend(soft)
                warnings.extend(result.warnings or [])
            else:
                warnings.extend(result.warnings or [])

        context.set("generated_files", list(context.created_files))

        if errors:
            return StageResult.failed(
                self.name,
                errors=errors,
                warnings=warnings,
                metadata={"engines_ran": ran},
            )
        return StageResult.ok(
            self.name,
            outputs={"files": list(context.created_files)},
            warnings=warnings,
            metadata={"engines_ran": ran},
        )


__all__ = ["GenerateStage"]
