"""
Generate stage — runs generator engines in CoreEngineManager order.

Respects dependency priorities registered in bootstrap (priority 10→151).
Engines that already ran in earlier stages (intent_parser, blueprint_composer)
are skipped. Quality-gate failures are soft-failed so later engines still run.
"""

from __future__ import annotations

from typing import Any, List, Optional

from ...core.context import GenerationContext
from ...core.result import StageResult
from ...registry import EngineRegistry
from ..base_stage import BaseStage


# Already executed in parse / compose stages
# Already executed in parse / compose stages — do not re-run here.
_PRECEDING_ENGINES = {"analyzer", "intent_parser", "blueprint_composer"}


class GenerateStage(BaseStage):
    """Runs all generator engines in manager dependency order."""

    stage_name = "generate"
    requires: List[str] = ["blueprint"]
    provides: List[str] = ["generated_files"]

    def __init__(
        self,
        registry: EngineRegistry,
        manager: Optional[Any] = None,
    ) -> None:
        super().__init__()
        self._registry = registry
        self._manager = manager

    def execute(self, context: GenerationContext) -> StageResult:
        if context.blueprint is None:
            return StageResult.failed(
                self.name, ["No blueprint attached to the context."]
            )

        engines = self._ordered_engines()
        errors: List[str] = []
        warnings: List[str] = []
        ran: List[str] = []
        failed: List[str] = []

        for engine in engines:
            self._log.info(
                "Running generator engine",
                {"engine": engine.name, "index": len(ran) + 1, "total": len(engines)},
            )
            try:
                result = engine.execute(context)
            except Exception as exc:  # noqa: BLE001
                msg = f"Engine '{engine.name}' crashed: {exc}"
                errors.append(msg)
                failed.append(engine.name)
                self._log.exception(
                    "Generator engine crashed",
                    {"engine": engine.name},
                )
                continue

            ran.append(engine.name)
            if not result.success:
                hard = [
                    e for e in (result.errors or [])
                    if "crashed" in e.lower() or "no blueprint" in e.lower()
                ]
                soft = [e for e in (result.errors or []) if e not in hard]
                # Soft quality-gate / readiness failures never abort the chain
                for e in soft:
                    warnings.append(f"[{engine.name}] {e}")
                errors.extend(hard)
                warnings.extend(result.warnings or [])
                if hard:
                    failed.append(engine.name)
            else:
                warnings.extend(result.warnings or [])

        context.set("generated_files", list(context.created_files))
        context.set(
            "engine_run_report",
            {
                "ran": ran,
                "failed": failed,
                "total": len(engines),
            },
        )

        if errors:
            return StageResult.failed(
                self.name,
                errors=errors,
                warnings=warnings,
                metadata={
                    "engines_ran": ran,
                    "engines_failed": failed,
                    "engines_total": len(engines),
                },
            )
        return StageResult.ok(
            self.name,
            outputs={"files": list(context.created_files)},
            warnings=warnings,
            metadata={
                "engines_ran": ran,
                "engines_failed": failed,
                "engines_total": len(engines),
            },
        )

    def _ordered_engines(self) -> List:
        """Order engines by CoreEngineManager queue priority when available."""
        by_name = {e.name: e for e in self._registry.engines()}
        ordered: List = []
        seen = set()

        if self._manager is not None:
            try:
                queue = self._manager.queue_order()
                for item in queue:
                    eid = getattr(item, "engine_id", None) or str(item)
                    if eid in _PRECEDING_ENGINES:
                        continue
                    eng = by_name.get(eid)
                    if eng is None:
                        # manager id may match engine name
                        eng = by_name.get(eid.replace("-", "_"))
                    if eng is not None and eng.name not in seen:
                        ordered.append(eng)
                        seen.add(eng.name)
            except Exception:
                ordered = []
                seen = set()

        # Append any registry engines not in manager queue
        rest = [
            e for e in self._registry.engines()
            if e.name not in _PRECEDING_ENGINES and e.name not in seen
        ]
        rest.sort(key=lambda e: getattr(e, "metadata", {}).get("order", 100))
        ordered.extend(rest)
        return ordered


__all__ = ["GenerateStage"]
