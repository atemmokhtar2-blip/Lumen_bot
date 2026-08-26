"""Minimal capability catalog after permanent removal of spec_core.

Generation is Cline-only. This module only provides empty/safe symbols so
capability_detection imports do not crash. No deterministic template engine.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Capability:
    key: str
    service: str = ""
    method: str = ""
    description_ar: str = ""
    description_en: str = ""
    default_actor: str = "user"
    permissions: tuple[str, ...] = ()
    needs_target_user: bool = False
    category: str = "general"


CAPABILITIES: dict[str, Capability] = {}
DEFAULT_COMMANDS: dict[str, str] = {
    "start": "start",
    "help": "help",
}


def get_capability(key: str) -> Capability | None:
    return CAPABILITIES.get(str(key or "").strip())


def by_category(category: str) -> list[Capability]:
    cat = str(category or "").strip()
    return [c for c in CAPABILITIES.values() if c.category == cat]


def extract_all(text: str, **_kwargs: Any) -> list[str]:
    """Former capability_extractor — no-op after spec_core removal."""
    return []


def feature_for_command(cmd: str) -> str | None:
    c = str(cmd or "").strip().lstrip("/")
    for feat, command in DEFAULT_COMMANDS.items():
        if command == c or feat == c:
            return feat
    return None


def features_from_text(text: str) -> list[str]:
    return []


def primary_commands() -> dict[str, str]:
    return dict(DEFAULT_COMMANDS)


__all__ = [
    "CAPABILITIES",
    "Capability",
    "DEFAULT_COMMANDS",
    "by_category",
    "extract_all",
    "feature_for_command",
    "features_from_text",
    "get_capability",
    "primary_commands",
]
