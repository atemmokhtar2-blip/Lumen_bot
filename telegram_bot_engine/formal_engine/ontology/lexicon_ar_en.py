"""lexicon — phrase/domain templates REMOVED. Neutral shims only."""
from __future__ import annotations

INTENT_VERBS: tuple[str, ...] = ()
DOMAIN_PHRASES: dict[str, tuple[str, ...]] = {}
FEATURE_PHRASES: list[tuple[str, tuple[str, ...]]] = []
TECH_PHRASES: dict[str, tuple[str, ...]] = {}
QUALITY_PHRASES: dict[str, tuple[str, ...]] = {}


def score_domains(text: str) -> dict[str, int]:
    return {}


def extract_features_fast(text: str) -> list[str]:
    return []


def detect_tech(text: str) -> list[str]:
    return []


def score_qualities(text: str) -> dict[str, int]:
    return {}
