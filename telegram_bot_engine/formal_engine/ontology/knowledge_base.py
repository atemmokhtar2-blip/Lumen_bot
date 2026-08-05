"""
knowledge_base — ALL archetype/domain packs REMOVED.
Neutral shims only. Formal path uses DSL extractor.
"""

from __future__ import annotations

from typing import Any

BOT_ARCHETYPES: dict[str, dict[str, Any]] = {}


def detect_archetype(text: str) -> str:
    return "CUSTOM"


def enrich_from_archetype(archetype: str) -> dict[str, Any]:
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
    """No feature pack scoring."""
    return []


def default_commands_for(archetype: str) -> list[dict[str, Any]]:
    return []


def default_buttons_for(archetype: str) -> list[dict[str, Any]]:
    return []


def default_handlers_for(archetype: str) -> list[dict[str, Any]]:
    return []
