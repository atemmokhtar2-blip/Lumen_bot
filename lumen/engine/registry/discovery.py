"""Auto-discovery of generation engines.

Legacy catalog/deterministic generators were removed permanently.
Product generation path is Cline-only (see engine_router / cline_runtime).
This module remains so bootstrap/registry call sites do not break.
"""
from __future__ import annotations

from typing import List, Type

from .registry import EngineRegistry
from ..core.contracts import Engine


# Empty: no pipeline generator engines are registered.
# Git/live process drivers live under lumen.engine.services.* and are not
# Engine-registry stages.
ENGINE_CLASSES: List[Type[Engine]] = []


def discover_and_register(registry: EngineRegistry) -> None:
    """No-op discovery — Cline path does not use the legacy engine registry."""
    for cls in ENGINE_CLASSES:
        engine = cls()
        registry.register_engine(engine)


def get_engine_classes() -> List[Type[Engine]]:
    return list(ENGINE_CLASSES)
