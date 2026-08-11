"""Deterministic search over the capability registry.

No embeddings, no external APIs. Token-overlap + category boost only.
Safe for zero-AI path and offline use.
"""
from __future__ import annotations

import re
from typing import Iterable

from ...spec_core.registry import CAPABILITIES, Capability, by_category, get_capability

# Lightweight Arabic/English stopwords — keep matching focused
_STOP = frozenset(
    {
        "a", "an", "the", "and", "or", "for", "to", "of", "in", "on", "with",
        "bot", "telegram", "please", "want", "need", "make", "create", "build",
        "بوت", "تيليجرام", "تلجرام", "عايز", "عاوز", "أريد", "اريد", "مطلوب",
        "يعمل", "فيه", "فيها", "مع", "من", "على", "في", "ال", "و", "أو",
        "نظام", "ميزة", "features", "feature", "please", "لي", "يكون",
    }
)

_TOKEN_RE = re.compile(r"[\w\u0600-\u06FF]{2,}", re.UNICODE)

# Mass-generated CRUD prefixes from registry_scale — downrank unless query is specific
_BULK_PREFIXES = (
    "cohort_", "segment_", "pipeline_", "workflow_", "artifact_", "asset_",
    "inventory_", "sku_", "ledger_", "journal_", "manifest_", "blueprint_",
    "grp_", "group_", "team_", "org_", "tenant_unit_",
)


def tokenize(text: str) -> list[str]:
    raw = (text or "").lower()
    tokens = _TOKEN_RE.findall(raw)
    return [t for t in tokens if t not in _STOP and not t.isdigit()]


def _cap_tokens(cap: Capability) -> set[str]:
    blob = " ".join(
        [
            cap.key.replace("_", " "),
            cap.service.replace("_", " "),
            cap.method.replace("_", " "),
            cap.category.replace("_", " "),
            cap.description_ar or "",
            cap.description_en or "",
        ]
    ).lower()
    return set(tokenize(blob)) | {cap.key, cap.service, cap.category}


def _is_bulk_key(key: str) -> bool:
    k = (key or "").lower()
    return any(k.startswith(p) for p in _BULK_PREFIXES)


def score_capability(query_tokens: Iterable[str], cap: Capability) -> float:
    """Overlap score in [0, 1]. Prefer description/key hits over bulk scale noise."""
    q = set(query_tokens)
    if not q:
        return 0.0
    ct = _cap_tokens(cap)
    if not ct:
        return 0.0
    inter = q & ct
    if not inter:
        key_parts = set(cap.key.split("_"))
        inter = q & key_parts
        if not inter:
            return 0.0
        base = min(0.40, 0.12 * len(inter))
    else:
        j = len(inter) / max(len(q), 1)
        coverage = len(inter) / max(len(ct), 1)
        base = min(1.0, 0.65 * j + 0.35 * coverage + 0.05 * min(len(inter), 4))

    # Strong boost when query token appears in Arabic/English description
    desc = f"{cap.description_ar or ''} {cap.description_en or ''}".lower()
    desc_hits = sum(1 for t in q if len(t) >= 3 and t in desc)
    if desc_hits:
        base = min(1.0, base + 0.12 * desc_hits)

    # Key substring boost (e.g. ترحيب path via welcome after extractor)
    for t in q:
        if t and t in cap.key:
            base = min(1.0, base + 0.15)
            break

    # Penalize mass scale CRUD keys on short/generic queries
    if _is_bulk_key(cap.key) and len(q) <= 5:
        base *= 0.35

    return base


def search_capabilities(
    query: str,
    *,
    limit: int = 20,
    min_score: float = 0.20,
    categories: Iterable[str] | None = None,
) -> list[tuple[Capability, float]]:
    """Rank registry capabilities against free-text query.

    Returns list of (Capability, score) sorted descending by score.
    Default min_score raised to reduce registry_scale noise.
    """
    tokens = tokenize(query)
    if not tokens:
        return []

    cat_filter: set[str] | None = None
    if categories:
        cat_filter = {c.strip().lower() for c in categories if c}

    scored: list[tuple[Capability, float]] = []
    for cap in CAPABILITIES.values():
        if cat_filter and cap.category not in cat_filter:
            continue
        s = score_capability(tokens, cap)
        if s >= min_score:
            scored.append((cap, s))

    scored.sort(key=lambda x: (-x[1], x[0].key))
    return scored[: max(1, int(limit))]


def search_by_category(category: str, *, limit: int = 50) -> list[Capability]:
    cats = by_category()
    items = cats.get((category or "").strip().lower(), [])
    return list(items)[: max(1, int(limit))]


def nearest_keys_for_phrase(phrase: str, *, limit: int = 5) -> list[str]:
    """Best-effort nearest registry keys for a gap phrase."""
    hits = search_capabilities(phrase, limit=limit, min_score=0.12)
    return [c.key for c, _ in hits]


def resolve_key(key: str) -> Capability | None:
    return get_capability(key)


__all__ = [
    "tokenize",
    "score_capability",
    "search_capabilities",
    "search_by_category",
    "nearest_keys_for_phrase",
    "resolve_key",
]
