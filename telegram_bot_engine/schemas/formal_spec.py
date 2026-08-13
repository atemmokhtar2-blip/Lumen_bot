"""Formal bot specification (legacy AI/formal path compatibility)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class FormalBotSpec:
    name: str = "bot"
    description: str = ""
    language: str = "ar"
    features: list[Any] = field(default_factory=list)
    commands: list[Any] = field(default_factory=list)
    entities: list[Any] = field(default_factory=list)
    buttons: list[Any] = field(default_factory=list)
    services: list[Any] = field(default_factory=list)
    raw_text: str = ""
    meta: dict[str, Any] = field(default_factory=dict)
