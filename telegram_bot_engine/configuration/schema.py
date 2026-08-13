"""
Configuration schema definitions.

A schema describes the *shape* of the configuration: which sections exist,
which fields live inside each section, their types, defaults, and
constraints.  The schema is the single source of truth for what the
configuration may contain.

Design rationale
----------------
Keeping the schema separate from the loader means we can:

* Validate configuration loaded from any source before it is used.
* Generate documentation for available options automatically.
* Detect typos or unknown keys early, instead of at runtime.

This module knows nothing about how configuration is loaded (files,
environment, etc.) — that responsibility lives in :mod:`.config`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Field-level definition
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FieldSchema:
    """Describes a single configuration field.

    Attributes:
        name: Machine name of the field (e.g. ``"max_workers"``).
        type: Python type the value must be convertible to.
        default: Default value used when the field is missing.
        required: When ``True`` the field must be present (no default).
        description: Human-readable explanation.
        choices: Optional list of allowed values.
        validator: Optional callable that receives the value and returns
            ``True`` when the value is acceptable.
        env_var: Optional name of an environment variable that can supply
            the value.  When set, the loader will read the environment
            variable if the explicit configuration does not provide one.
    """

    name: str
    type: type
    default: Any = None
    required: bool = False
    description: str = ""
    choices: Optional[List[Any]] = None
    validator: Optional[Callable[[Any], bool]] = None
    env_var: Optional[str] = None

    def validate_value(self, value: Any) -> List[str]:
        """Return a list of error messages for *value* (empty when valid)."""
        errors: List[str] = []

        if not isinstance(value, self.type):
            # Allow ints to come from strings when the type is numeric.
            coerced = _try_coerce(value, self.type)
            if coerced is None:
                errors.append(
                    f"Field '{self.name}' must be of type {self.type.__name__}, "
                    f"got {type(value).__name__}."
                )
                return errors
            value = coerced

        if self.choices is not None and value not in self.choices:
            errors.append(
                f"Field '{self.name}' must be one of {self.choices}, "
                f"got {value!r}."
            )

        if self.validator is not None and not self.validator(value):
            errors.append(
                f"Field '{self.name}' failed custom validation "
                f"(value={value!r})."
            )

        return errors


def _try_coerce(value: Any, target_type: type) -> Any:
    """Attempt to coerce *value* to *target_type*; return ``None`` on failure."""
    if target_type is int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    if target_type is float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if target_type is str:
        try:
            return str(value)
        except (TypeError, ValueError):
            return None
    if target_type is bool:
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)
    return None


# ---------------------------------------------------------------------------
# Section-level definition
# ---------------------------------------------------------------------------

@dataclass
class SectionSchema:
    """Describes a named group of configuration fields.

    Sections keep the configuration flat structure readable while still
    being logically grouped (e.g. ``logging``, ``pipeline``, ``output``).
    """

    name: str
    description: str = ""
    fields: List[FieldSchema] = field(default_factory=list)

    def field_names(self) -> List[str]:
        return [f.name for f in self.fields]

    def get_field(self, name: str) -> Optional[FieldSchema]:
        for f in self.fields:
            if f.name == name:
                return f
        return None


# ---------------------------------------------------------------------------
# Top-level schema
# ---------------------------------------------------------------------------

@dataclass
class ConfigSchema:
    """The complete configuration schema for the whole engine."""

    sections: List[SectionSchema] = field(default_factory=list)

    def section_names(self) -> List[str]:
        return [s.name for s in self.sections]

    def get_section(self, name: str) -> Optional[SectionSchema]:
        for s in self.sections:
            if s.name == name:
                return s
        return None

    def validate(self, data: Dict[str, Any]) -> List[str]:
        """Validate a full configuration dictionary.

        Returns a list of human-readable error messages.  An empty list
        means the configuration is valid.
        """
        errors: List[str] = []

        known_sections = set(self.section_names())
        for key in data:
            if key not in known_sections:
                errors.append(f"Unknown configuration section '{key}'.")

        for section in self.sections:
            section_data = data.get(section.name, {})
            if not isinstance(section_data, dict):
                errors.append(
                    f"Section '{section.name}' must be a mapping, "
                    f"got {type(section_data).__name__}."
                )
                continue

            known_fields = set(section.field_names())
            for key in section_data:
                if key not in known_fields:
                    errors.append(
                        f"Unknown field '{key}' in section '{section.name}'."
                    )

            for field_schema in section.fields:
                if field_schema.name in section_data:
                    errors.extend(
                        field_schema.validate_value(section_data[field_schema.name])
                    )
                elif field_schema.required:
                    errors.append(
                        f"Required field '{field_schema.name}' is missing "
                        f"in section '{section.name}'."
                    )

        return errors

    def defaults(self) -> Dict[str, Any]:
        """Return a configuration dictionary populated only with defaults."""
        result: Dict[str, Any] = {}
        for section in self.sections:
            section_defaults: Dict[str, Any] = {}
            for f in section.fields:
                if f.default is not None or not f.required:
                    section_defaults[f.name] = f.default
            result[section.name] = section_defaults
        return result


__all__ = [
    "FieldSchema",
    "SectionSchema",
    "ConfigSchema",
]
