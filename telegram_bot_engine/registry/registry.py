"""
Engine registry — central catalogue of all engine components.

The registry stores instances of :class:`~core.contracts.Engine`,
:class:`~core.contracts.Builder`, and
:class:`~core.contracts.Validator`.  Components are registered with a
*type* (``"engine"``, ``"builder"``, ``"validator"``) and a unique name.

The registry is deliberately dumb: it does not instantiate components,
it does not run them, and it knows nothing about the pipeline.  It only
maps names to instances and provides query helpers.

Auto-discovery of components from packages is performed lazily by
:mod:`telegram_bot_engine.registry.discovery` (added in a later phase).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Type, TypeVar

from ..core.contracts import Builder, Component, Engine, Validator
from ..logging import get_logger

T = TypeVar("T", bound=Component)

_logger = get_logger("registry")


@dataclass
class RegistryEntry:
    """A single entry in the registry."""

    type: str  # "engine" | "builder" | "validator"
    name: str
    instance: Component
    metadata: Dict = field(default_factory=dict)


class EngineRegistry:
    """Central registry for all engine components.

    The registry is the *only* place where the pipeline obtains
    components.  This indirection lets us swap implementations, add new
    ones, or mock them in tests without touching the pipeline.
    """

    def __init__(self) -> None:
        self._entries: Dict[str, Dict[str, RegistryEntry]] = {
            "engine": {},
            "builder": {},
            "validator": {},
        }

    # -- registration ------------------------------------------------------

    def register_engine(self, engine: Engine,
                        metadata: Optional[Dict] = None) -> None:
        self._register("engine", engine, metadata)

    def register_builder(self, builder: Builder,
                         metadata: Optional[Dict] = None) -> None:
        self._register("builder", builder, metadata)

    def register_validator(self, validator: Validator,
                           metadata: Optional[Dict] = None) -> None:
        self._register("validator", validator, metadata)

    def _register(self, kind: str, component: Component,
                  metadata: Optional[Dict]) -> None:
        if not component.name:
            raise ValueError(f"{kind} component must have a name.")
        bucket = self._entries[kind]
        if component.name in bucket:
            _logger.warning(
                "Overwriting already-registered component",
                {"kind": kind, "name": component.name},
            )
        bucket[component.name] = RegistryEntry(
            type=kind,
            name=component.name,
            instance=component,
            metadata=metadata or {},
        )
        _logger.info(
            "Registered component",
            {"kind": kind, "name": component.name,
             "version": component.version},
        )

    # -- lookup ------------------------------------------------------------

    def get_engine(self, name: str) -> Optional[Engine]:
        entry = self._entries["engine"].get(name)
        return entry.instance if entry else None

    def get_builder(self, name: str) -> Optional[Builder]:
        entry = self._entries["builder"].get(name)
        return entry.instance if entry else None

    def get_validator(self, name: str) -> Optional[Validator]:
        entry = self._entries["validator"].get(name)
        return entry.instance if entry else None

    # -- enumeration -------------------------------------------------------

    def engines(self) -> List[Engine]:
        return [e.instance for e in self._entries["engine"].values()]

    def builders(self) -> List[Builder]:
        return [e.instance for e in self._entries["builder"].values()]

    def validators(self) -> List[Validator]:
        return [e.instance for e in self._entries["validator"].values()]

    def engine_names(self) -> List[str]:
        return list(self._entries["engine"].keys())

    def builder_names(self) -> List[str]:
        return list(self._entries["builder"].keys())

    def validator_names(self) -> List[str]:
        return list(self._entries["validator"].keys())

    def all_entries(self) -> Iterator[RegistryEntry]:
        for bucket in self._entries.values():
            for entry in bucket.values():
                yield entry

    # -- introspection -----------------------------------------------------

    def count(self) -> Dict[str, int]:
        return {kind: len(bucket) for kind, bucket in self._entries.items()}

    def is_empty(self) -> bool:
        return all(len(b) == 0 for b in self._entries.values())

    def __repr__(self) -> str:
        c = self.count()
        return (
            f"EngineRegistry(engines={c['engine']}, "
            f"builders={c['builder']}, validators={c['validator']})"
        )


__all__ = ["EngineRegistry", "RegistryEntry"]
