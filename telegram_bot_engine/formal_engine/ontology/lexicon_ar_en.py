"""
lexicon_ar_en — dictionaries and domain phrase templates REMOVED.

Formal Logic & DSL Engine path does not use phrase→archetype scoring packs.
Kept as a thin compatibility shim so old imports do not crash.
All scoring functions return empty / neutral results.
"""

from __future__ import annotations

# Dictionaries intentionally emptied (surgical removal of template layer).
INTENT_VERBS: tuple[str, ...] = ()
DOMAIN_PHRASES: dict[str, tuple[str, ...]] = {}
FEATURE_PHRASES: list[tuple[str, tuple[str, ...]]] = []
TECH_PHRASES: dict[str, tuple[str, ...]] = {}
QUALITY_PHRASES: dict[str, tuple[str, ...]] = {}


def score_domains(text: str) -> dict[str, int]:
    """Neutral — no domain scoring packs."""
    return {}


def extract_features_fast(text: str) -> list[str]:
    """Neutral — no feature phrase packs."""
    return []


def detect_tech(text: str) -> list[str]:
    return []


def detect_quality(text: str) -> list[str]:
    return []
