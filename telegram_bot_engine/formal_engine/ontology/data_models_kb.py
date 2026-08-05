"""
data_models_kb — entity packs REMOVED.
Models come from user text only (DSL extractor is primary).
"""

from __future__ import annotations

import re
from typing import Any

# Empty — no canned entity schemas
ENTITY_LIBRARY: dict[str, list[tuple[str, str]]] = {}


def resolve_data_models(archetype: str, text: str) -> list[dict[str, Any]]:
    """Text-grounded models only. archetype argument ignored."""
    _ = archetype
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for m in re.finditer(
        r"(?:كيان|نموذج|entity|model|table)\s+[«\"']?([A-Za-z][A-Za-z0-9_]{1,40})[»\"']?",
        text or "",
        re.I,
    ):
        name = m.group(1)
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"name": name, "fields": [("id", "str")], "source": "text"})
    return out


def lookup_entity(name: str) -> list[tuple[str, str]]:
    """No library packs."""
    return [("id", "str")]
