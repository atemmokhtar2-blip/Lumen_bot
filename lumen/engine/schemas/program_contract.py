"""Program / planning contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ProgramEntity:
    name: str = ""
    attributes: list[str] = field(default_factory=list)
    kind: str = ""


@dataclass
class ProgramButton:
    label: str = ""
    callback: str = ""
    action: str = ""


@dataclass
class ProgramCommand:
    name: str = ""
    description: str = ""
    handler: str = ""


@dataclass
class ProgramService:
    name: str = ""
    methods: list[str] = field(default_factory=list)


@dataclass
class ProgramContract:
    title: str = ""
    description: str = ""
    language: str = "ar"
    entities: list[Any] = field(default_factory=list)
    buttons: list[Any] = field(default_factory=list)
    commands: list[Any] = field(default_factory=list)
    services: list[Any] = field(default_factory=list)
    features: list[Any] = field(default_factory=list)
    integrations: list[Any] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    readiness: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""
