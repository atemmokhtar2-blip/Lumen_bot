"""Built-in template catalog (Phase 0).

Loads the static JSON registry shipped with the package. No network, no user
input — pure read model for UI and policy later.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from lumen.templates.models import TemplateSpec

logger = logging.getLogger(__name__)

_DATA = Path(__file__).resolve().parent / "data" / "catalog.json"


def _load_raw() -> list[dict]:
    try:
        raw = json.loads(_DATA.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("templates catalog unreadable: %s", type(exc).__name__)
        return []
    if not isinstance(raw, list):
        return []
    return [x for x in raw if isinstance(x, dict)]


@lru_cache(maxsize=1)
def list_templates(*, enabled_only: bool = True) -> tuple[TemplateSpec, ...]:
    out: list[TemplateSpec] = []
    for item in _load_raw():
        spec = TemplateSpec.from_dict(item)
        if spec is None:
            continue
        if enabled_only and not spec.enabled:
            continue
        out.append(spec)
    return tuple(out)


def get_template(template_id: str) -> TemplateSpec | None:
    tid = (template_id or "").strip()
    if not tid:
        return None
    for spec in list_templates(enabled_only=False):
        if spec.id == tid:
            return spec if spec.enabled else None
    return None


def reload_catalog() -> None:
    """Test helper — clear cache after mutating catalog file."""
    list_templates.cache_clear()


__all__ = ["list_templates", "get_template", "reload_catalog"]
