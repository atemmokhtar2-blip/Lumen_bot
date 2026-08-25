"""
Configuration loading and access.

This module implements the :class:`Configuration` container and the
:class:`ConfigSource` abstraction used to feed values into it.

A ``Configuration`` is built by merging values from one or more
:class:`ConfigSource` instances according to a priority order.  The
result is validated against a :class:`~.schema.ConfigSchema` so that
engines can rely on well-formed values.

No engine, builder, or validator should ever read environment variables
or files directly.  They receive a :class:`Configuration` object instead.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from .schema import ConfigSchema


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

@dataclass
class ConfigSource:
    """A single source of configuration values.

    The ``priority`` determines the merge order — a *higher* number wins.
    The :meth:`load` method must return a flat dictionary of
    ``{section: {field: value}}``.
    """

    name: str
    priority: int = 0
    _data: Optional[Dict[str, Any]] = None

    def load(self) -> Dict[str, Any]:
        """Return the raw configuration dictionary for this source."""
        if self._data is None:
            self._data = {}
        return self._data


class DictSource(ConfigSource):
    """A configuration source backed by an in-memory dictionary."""

    def __init__(self, name: str, data: Mapping[str, Any], priority: int = 0):
        super().__init__(name=name, priority=priority)
        self._data = dict(data)

    def load(self) -> Dict[str, Any]:
        return self._data


class FileSource(ConfigSource):
    """A configuration source backed by a JSON file on disk."""

    def __init__(self, name: str, path: str, priority: int = 0):
        super().__init__(name=name, priority=priority)
        self._path = Path(path)

    def load(self) -> Dict[str, Any]:
        if not self._path.exists():
            return {}
        with self._path.open("r", encoding="utf-8") as fh:
            return json.load(fh)


class EnvironmentSource(ConfigSource):
    """A configuration source backed by environment variables.

    Environment variables follow the convention ``TBE__<SECTION>__<FIELD>``.
    """

    PREFIX = "TBE__"

    def __init__(self, name: str = "environment", priority: int = 0,
                 env: Optional[Mapping[str, str]] = None):
        super().__init__(name=name, priority=priority)
        self._env = env if env is not None else os.environ

    def load(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for key, value in self._env.items():
            if not key.startswith(self.PREFIX):
                continue
            remainder = key[len(self.PREFIX):]
            parts = remainder.split("__", 1)
            if len(parts) != 2:
                continue
            section, field_name = parts
            result.setdefault(section.lower(), {})[field_name.lower()] = value
        return result


# ---------------------------------------------------------------------------
# Configuration container
# ---------------------------------------------------------------------------

class Configuration:
    """Immutable, validated configuration container.

    The configuration is built once from a schema and a list of sources.
    After construction it exposes typed accessors and prevents accidental
    mutation by engines.
    """

    def __init__(self, schema: ConfigSchema, sources: List[ConfigSource]):
        self._schema = schema
        self._sources = sorted(sources, key=lambda s: s.priority)
        self._data: Dict[str, Any] = self._merge()
        self._validate()

    # -- merging -----------------------------------------------------------

    def _merge(self) -> Dict[str, Any]:
        merged: Dict[str, Any] = self._schema.defaults()
        # Lower priority first, higher priority overwrites.
        for source in self._sources:
            raw = source.load()
            for section, fields in raw.items():
                if not isinstance(fields, dict):
                    continue
                bucket = merged.setdefault(section, {})
                for name, value in fields.items():
                    bucket[name] = value
        return merged

    def _validate(self) -> None:
        errors = self._schema.validate(self._data)
        if errors:
            raise ValueError(
                "Configuration validation failed:\n  - " + "\n  - ".join(errors)
            )

    # -- access ------------------------------------------------------------

    @property
    def schema(self) -> ConfigSchema:
        return self._schema

    def section(self, name: str) -> Dict[str, Any]:
        """Return a copy of the values for a configuration section."""
        return dict(self._data.get(name, {}))

    def get(self, section: str, field: str, default: Any = None) -> Any:
        return self._data.get(section, {}).get(field, default)

    def as_dict(self) -> Dict[str, Any]:
        """Return a deep copy of the entire configuration."""
        import copy
        return copy.deepcopy(self._data)

    # -- introspection -----------------------------------------------------

    def __repr__(self) -> str:
        return f"Configuration(sections={list(self._data.keys())})"


__all__ = [
    "ConfigSource",
    "DictSource",
    "FileSource",
    "EnvironmentSource",
    "Configuration",
]
