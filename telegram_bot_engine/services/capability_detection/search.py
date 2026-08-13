"""Deterministic search over the capability registry.

Phase-1 hardened:
  - Prefer PRIMARY (seed) categories from the hand-authored registry
  - Heavily down-rank mass registry_scale CRUD noise
  - No embeddings / no web
"""
from __future__ import annotations

import re
from typing import Iterable

from ...spec_core.registry import CAPABILITIES, Capability, by_category, get_capability

_STOP = frozenset(
    {
        "a", "an", "the", "and", "or", "for", "to", "of", "in", "on", "with",
        "bot", "telegram", "please", "want", "need", "make", "create", "build",
        "بوت", "تيليجرام", "تلجرام", "عايز", "عاوز", "أريد", "اريد", "مطلوب",
        "يعمل", "فيه", "فيها", "مع", "من", "على", "في", "ال", "و", "أو",
        "نظام", "ميزة", "features", "feature", "please", "لي", "يكون", "هذا",
        "that", "this", "only", "فقط", "جدا", "جداً", "simple", "بسيط",
    }
)

_TOKEN_RE = re.compile(r"[\w\u0600-\u06FF]{2,}", re.UNICODE)

# Hand-authored product categories (registry.py core packs) — search prefers these
PRIMARY_CATEGORIES = frozenset(
    {
        "core", "content", "community", "moderation", "welcome", "gate",
        "tasks", "notes", "reminders", "tickets", "crm", "security",
        "shop", "payments", "subscriptions", "points", "contests", "i18n",
        "booking", "edu", "hr", "utils", "cart", "growth", "retention",
        "admin", "gamification", "creator", "wallet", "notify", "forms",
        "events", "jobs", "restaurant", "fitness", "realestate", "clinic",
        "auction", "delivery", "onboarding", "pricing", "services",
        "integrations", "compliance", "waitlist",
    }
)

# Mass-generated prefixes from registry_scale
_BULK_PREFIXES = (
    "cohort_", "segment_", "pipeline_", "workflow_", "artifact_", "asset_",
    "inventory_", "sku_", "ledger_", "journal_", "manifest_", "blueprint_",
    "grp_", "group_", "team_", "org_", "tenant_unit_", "clinic2_", "result_",
    "album_", "artist_", "blog_", "feed_", "gallery_", "partner_", "sponsor_",
    "store_", "store2_",
)

_BULK_CATEGORIES = frozenset(
    {
        "logistics", "saas", "finance", "marketplace", "commerce",
        "analytics", "support", "ops", "facilities", "iot",
        "clinic_ops", "groups2", "tickets2", "events2", "jobs2", "forms2",
        "kb2", "auctions2", "ads_ops", "bot_cmds", "bot_flows", "bot_states",
        "bot_kbs", "bot_msgs", "notifs", "members", "cohorts",
    }
)

_CRUD_SUFFIXES = (
    "_create", "_approve", "_archive", "_assign", "_audit", "_cancel",
    "_claim", "_close", "_delete", "_duplicate", "_export", "_favorite",
    "_filter", "_follow", "_history", "_import_data", "_list", "_pin",
    "_restore", "_search", "_share", "_stats", "_unfavorite", "_unpin",
    "_update", "_view",
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


def is_bulk_key(key: str, category: str = "") -> bool:
    k = (key or "").lower()
    cat = (category or "").lower()
    if cat in _BULK_CATEGORIES:
        return True
    if any(k.startswith(p) for p in _BULK_PREFIXES):
        return True
    if cat and cat not in PRIMARY_CATEGORIES:
        if any(k.endswith(sfx) for sfx in _CRUD_SUFFIXES):
            return True
    return False


def score_capability(query_tokens: Iterable[str], cap: Capability) -> float:
    """Overlap score in [0, 1]. Primary categories ranked far above scale noise."""
    q = set(query_tokens)
    if not q:
        return 0.0
    if is_bulk_key(cap.key, cap.category):
        desc = f"{cap.description_ar or ''} {cap.description_en or ''}".lower()
        strong = sum(1 for t in q if len(t) >= 4 and t in desc)
        if strong < 2:
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

    desc = f"{cap.description_ar or ''} {cap.description_en or ''}".lower()
    desc_hits = sum(1 for t in q if len(t) >= 3 and t in desc)
    if desc_hits:
        base = min(1.0, base + 0.14 * desc_hits)

    for t in q:
        if t and t in cap.key:
            base = min(1.0, base + 0.18)
            break

    if cap.category in PRIMARY_CATEGORIES:
        base = min(1.0, base + 0.12)
    else:
        base *= 0.25

    return base


def search_capabilities(
    query: str,
    *,
    limit: int = 20,
    min_score: float = 0.28,
    categories: Iterable[str] | None = None,
    primary_only: bool = True,
) -> list[tuple[Capability, float]]:
    """Rank registry capabilities against free-text query."""
    tokens = tokenize(query)
    if not tokens:
        return []

    cat_filter: set[str] | None = None
    if categories:
        cat_filter = {c.strip().lower() for c in categories if c}
    elif primary_only:
        cat_filter = set(PRIMARY_CATEGORIES)

    scored: list[tuple[Capability, float]] = []
    for cap in CAPABILITIES.values():
        if cat_filter and cap.category not in cat_filter:
            continue
        if is_bulk_key(cap.key, cap.category) and primary_only:
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
    hits = search_capabilities(phrase, limit=limit, min_score=0.18, primary_only=True)
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
    "PRIMARY_CATEGORIES",
    "is_bulk_key",
]
