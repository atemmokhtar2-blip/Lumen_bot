"""Bootstrap stub — legacy deterministic engine registry removed.

Product generation is Cline-only via engine_router / cline_runtime.
This module remains only so any residual import of ``bootstrap`` fails clearly.
"""
from __future__ import annotations

from typing import Any, Optional


def build_configuration(sources: Optional[list] = None) -> Any:
    raise RuntimeError(
        "deterministic_engine_removed: build_configuration is gone; "
        "use lumen.engine.services.engine_router / cline_runtime"
    )


def bootstrap(
    config: Optional[Any] = None,
    sources: Optional[list] = None,
) -> tuple:
    raise RuntimeError(
        "deterministic_engine_removed: PipelineOrchestrator / CoreEngineManager "
        "and catalog generators were deleted. Generation path is Cline-only."
    )


ENGINE_META: dict = {}
