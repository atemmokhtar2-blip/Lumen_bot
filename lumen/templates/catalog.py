"""JSON file catalog adapter implementing TemplateCatalogPort."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Sequence

from lumen.templates.errors import CatalogError
from lumen.templates.models import TemplateSpec

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path(__file__).resolve().parent / "data" / "catalog.json"


class JsonTemplateCatalog:
    """Read-only catalog. Validates every row; skips corrupt rows with log."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _DEFAULT_PATH
        self._cache: tuple[TemplateSpec, ...] | None = None

    def reload(self) -> None:
        self._cache = None

    def _load(self) -> tuple[TemplateSpec, ...]:
        if self._cache is not None:
            return self._cache
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise CatalogError(f"catalog_missing:{self._path}") from exc
        except Exception as exc:
            raise CatalogError(f"catalog_unreadable:{type(exc).__name__}") from exc
        if not isinstance(raw, list):
            raise CatalogError("catalog_not_a_list")
        specs: list[TemplateSpec] = []
        seen: set[str] = set()
        for i, row in enumerate(raw):
            if not isinstance(row, dict):
                logger.warning("templates catalog row %s ignored (not object)", i)
                continue
            try:
                spec = TemplateSpec.from_dict(row)
            except Exception as exc:
                logger.warning("templates catalog row %s invalid: %s", i, exc)
                continue
            if spec.id in seen:
                logger.warning("templates catalog duplicate id=%s skipped", spec.id)
                continue
            seen.add(spec.id)
            specs.append(spec)
        if not specs:
            raise CatalogError("catalog_empty_after_validation")
        self._cache = tuple(specs)
        return self._cache

    def list_enabled(self) -> Sequence[TemplateSpec]:
        return tuple(s for s in self._load() if s.enabled)

    def list_all(self) -> Sequence[TemplateSpec]:
        return self._load()

    def get(self, template_id: str) -> TemplateSpec | None:
        """Resolve by full id or short_id (Telegram callback arg)."""
        tid = (template_id or "").strip()
        if not tid:
            return None
        for s in self._load():
            if not s.enabled:
                continue
            if s.id == tid or s.short_id == tid:
                return s
        return None


# Process-wide default catalog (tests may construct their own)
_default = JsonTemplateCatalog()


def list_templates(*, enabled_only: bool = True) -> tuple[TemplateSpec, ...]:
    cat = _default
    return tuple(cat.list_enabled() if enabled_only else cat.list_all())


def get_template(template_id: str) -> TemplateSpec | None:
    return _default.get(template_id)


def reload_catalog() -> None:
    _default.reload()


__all__ = [
    "JsonTemplateCatalog",
    "list_templates",
    "get_template",
    "reload_catalog",
]
