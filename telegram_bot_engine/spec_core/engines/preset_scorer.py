"""Preset scoring engine.

The large keyword catalog lives in ``data/preset_keywords.json`` and the
legacy ``presets`` module remains a compatibility facade. Imports are lazy so
this engine can be used by diagnostics without creating an import cycle.
"""
from __future__ import annotations

from collections.abc import Iterable


def normalize(text: str) -> str:
    """Normalize Arabic/English text using the canonical preset scorer."""
    from .. import presets
    return presets._norm(text)


def token_hit(text: str, key: str) -> bool:
    """Boundary-aware keyword match using the canonical implementation."""
    from .. import presets
    return presets._token_hit(text, key)


def score_keys(text: str, keys: Iterable[str], weight: float = 1.0) -> float:
    """Score one keyword family without loading any template payload."""
    from .. import presets
    return presets._score_keys(text, keys, weight)


def rank_presets(request: str) -> list[tuple[str, float]]:
    """Return the canonical multi-intent preset ranking."""
    from .. import presets
    return presets.score_presets(request)


def detect_preset(request: str) -> str | None:
    ranked = rank_presets(request)
    return ranked[0][0] if ranked else None


__all__ = ["normalize", "token_hit", "score_keys", "rank_presets", "detect_preset"]
