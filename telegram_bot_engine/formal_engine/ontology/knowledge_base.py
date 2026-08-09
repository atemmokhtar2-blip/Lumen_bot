"""
knowledge_base — domain archetype packs permanently removed.
"""

from __future__ import annotations

from typing import Any


def detect_archetype(text: str) -> str:
    _ = text
    return "CUSTOM"


def enrich_from_archetype(archetype: str) -> dict[str, Any]:
    _ = archetype
    return {
        "archetype": "CUSTOM",
        "default_commands": [],
        "default_entities": [],
        "default_buttons": [],
        "features": [],
    }


def list_archetypes() -> list[str]:
    return ["CUSTOM"]


def extract_feature_tags(text: str) -> list[dict[str, Any]]:
    _ = text
    return []


def default_commands_for(archetype: str) -> list[dict[str, Any]]:
    _ = archetype
    return []


def default_buttons_for(archetype: str) -> list[dict[str, Any]]:
    _ = archetype
    return []


def default_handlers_for(archetype: str) -> list[dict[str, Any]]:
    _ = archetype
    return []
