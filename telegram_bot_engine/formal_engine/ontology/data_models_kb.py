"""data_models_kb — no entity library packs. Models from user text only."""
from __future__ import annotations
import re
from typing import Any

def resolve_data_models(archetype: str, text: str) -> list[dict[str, Any]]:
    _ = archetype
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    pattern = (
        r"(?:كيان|نموذج|entity|model|table)\s+"
        r"[«\"']?([A-Za-z][A-Za-z0-9_]{1,40})[»\"']?"
    )
    for m in re.finditer(pattern, text or "", re.I):
        name = m.group(1)
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "name": name,
            "fields": [],
            "field_names": [],
            "relations": [],
            "source": "text",
        })
    return out

def lookup_entity(name: str) -> list[tuple[str, str]]:
    _ = name
    return []
