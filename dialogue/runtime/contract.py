"""Stable dialogue contracts — do not break without a migration plan."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class DialogueRequest:
    text: str
    sender_id: str
    plan_id: str = "free"
    language: str = "ar"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DialogueResponse:
    text: str
    intent: str = ""
    confidence: float = 0.0
    engine: str = ""
    slots: dict[str, Any] = field(default_factory=dict)
    # If False, caller may fall through to legacy generation paths
    handled: bool = True


@runtime_checkable
class DialogueEngine(Protocol):
    name: str

    def available(self) -> bool:
        ...

    async def handle(self, request: DialogueRequest) -> DialogueResponse | None:
        ...
