"""Phase 3 — Template Synthesis Engine (hardened).

Pipeline: Filter noise → Category coherence → Dependency expand → Cap size.
Deterministic only — no web, no LLM.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable

from .catalog import CAPABILITIES, get_capability
from .models import DetectionReport, DetectionStatus, MatchedCapability
from .search import PRIMARY_CATEGORIES, is_bulk_key

# ---------------------------------------------------------------------------
# Dependency graph (seed product capabilities only)
# ---------------------------------------------------------------------------
_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    # shop / cart
    "cart_view": ("shop_catalog",),
    "cart_add": ("shop_catalog", "cart_view"),
    "cart_clear": ("cart_view",),
    "cart_checkout": ("shop_catalog", "cart_view"),
    "coupon_apply": ("shop_catalog",),
    "coupon_create": ("shop_catalog",),
    "shop_order": ("shop_catalog",),
    "shop_buy": ("shop_catalog",),
    "shop_my_orders": ("shop_catalog",),
    "shop_orders": ("shop_catalog",),
    "product_search": ("shop_catalog",),
    "product_info": ("shop_catalog",),
    "wishlist_view": ("shop_catalog",),
    "wishlist_add": ("shop_catalog",),
    # contests
    "draw_winner": ("contests",),
    "join_contest": ("contests",),
    "new_contest": ("contests",),
    "end_contest": ("contests",),
    "my_entries": ("contests",),
    "contest_info": ("contests",),
    # welcome / gate
    "welcome_toggle": ("welcome_set",),
    "welcome_show": ("welcome_set",),
    "welcome_test": ("welcome_set",),
    "goodbye_set": ("welcome_set",),
    "verify_ok": ("verify_start",),
    # tickets
    "ticket_my": ("ticket_open",),
    "ticket_close": ("ticket_open",),
    "ticket_reply": ("ticket_open",),
    "ticket_list": ("ticket_open",),
    "ticket_status": ("ticket_open",),
    # subscriptions
    "subscribe": ("plans",),
    "my_sub": ("plans",),
    "sub_status": ("plans",),
    "grant_sub": ("plans",),
    "revoke_sub": ("plans",),
    # booking
    "book_list": ("book_slot",),
    "book_cancel": ("book_slot",),
    "book_admin_list": ("book_slot",),
    # points
    "redeem_points": ("balance",),
    "points_history": ("balance",),
    "grant_points": ("balance",),
    "debit_points": ("balance",),
    "leaderboard": ("balance",),
    # growth
    "referral_invite": ("referral_code",),
    "referral_stats": ("referral_code",),
    # moderation pairs
    "user_unban": ("user_ban",),
    "user_unmute": ("user_mute",),
    "user_demote": ("user_promote",),
}

# Soft companions: only added when category is dominant (not from weak noise)
_CATEGORY_COMPANIONS: dict[str, tuple[str, ...]] = {
    "welcome": ("rules",),
    "moderation": ("rules",),
    "shop": (),  # don't auto-add cart unless asked
    "contests": (),
    "tickets": ("ticket_my",),
    "booking": ("book_list",),
    "points": (),
    "subscriptions": (),
}

_CORE = ("start", "help")

# Keys that are often search-noise unless user text supports them
_NOISE_UNLESS_HINT: dict[str, tuple[str, ...]] = {
    "lang": ("لغه", "لغة", "language", "i18n", "ترجمة واجهة", "عربي", "english"),
    "contests": ("مسابق", "contest", "سحب", "فائز", "giveaway", "تحدي"),
    "join_contest": ("مسابق", "contest", "انضم"),
    "draw_winner": ("سحب", "فائز", "draw"),
    "achievement_list": ("انجاز", "إنجاز", "achievement"),
    "note_add": ("ملاحظ", "note", "نوت"),
    "ticket_open": ("تذكر", "ticket", "دعم", "support"),
    "clinic_book": ("عياد", "clinic", "طبيب"),
    "clinic_my": ("عياد", "clinic"),
    "clinic_cancel": ("عياد", "clinic"),
    "clinic_slots": ("عياد", "clinic"),
}

_MIN_SCORE_EXTRACTOR = 0.0  # extractor source always kept
_MIN_SCORE_SEARCH = 0.45
_MAX_PACK = 14


@dataclass
class SynthesisPlan:
    keys: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    added_dependencies: list[str] = field(default_factory=list)
    pruned: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    status: str = "ok"  # ok | partial | empty
    source_status: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "keys": list(self.keys),
            "categories": list(self.categories),
            "added_dependencies": list(self.added_dependencies),
            "pruned": list(self.pruned),
            "conflicts": list(self.conflicts),
            "warnings": list(self.warnings),
            "status": self.status,
            "source_status": self.source_status,
            "confidence": round(self.confidence, 3),
        }


def _valid_key(key: str) -> bool:
    if not key or key not in CAPABILITIES:
        return False
    cap = CAPABILITIES[key]
    if is_bulk_key(key, cap.category):
        return False
    if cap.category not in PRIMARY_CATEGORIES and cap.category not in {
        "core", "welcome", "moderation", "shop", "cart", "points", "contests",
        "tickets", "subscriptions", "booking", "growth", "content", "community",
        "gate", "utils", "i18n", "payments", "admin", "notes", "tasks", "reminders",
        "crm", "security", "edu", "hr", "clinic", "wallet", "gamification",
    }:
        return False
    return True


def _text_hints(request: str) -> str:
    return (request or "").lower()


def _hint_supports(key: str, text: str) -> bool:
    hints = _NOISE_UNLESS_HINT.get(key)
    if not hints:
        return True
    return any(h in text for h in hints)


def _filter_matches(
    matched: list[MatchedCapability] | list[str],
    *,
    request: str = "",
) -> tuple[list[str], list[str], dict[str, float]]:
    """Keep high-signal keys only. Returns (kept, pruned, scores)."""
    text = _text_hints(request)
    kept: list[str] = []
    pruned: list[str] = []
    scores: dict[str, float] = {}
    seen: set[str] = set()

    items: list[tuple[str, float, str]] = []
    for m in matched or []:
        if isinstance(m, MatchedCapability):
            items.append((m.key, float(m.score or 0), m.source or "search"))
        elif isinstance(m, str):
            items.append((m, 1.0, "extractor"))

    for key, score, source in items:
        if key in seen:
            continue
        seen.add(key)
        if not _valid_key(key):
            pruned.append(key)
            continue
        if key in _CORE:
            kept.append(key)
            scores[key] = max(score, 1.0)
            continue
        # extractor / core source trusted
        if source in {"extractor", "core"} and score >= _MIN_SCORE_EXTRACTOR:
            # Only prune noise keys when we have user text to judge against
            if text and key in _NOISE_UNLESS_HINT and not _hint_supports(key, text):
                pruned.append(key)
                continue
            kept.append(key)
            scores[key] = score
            continue
        # search source: stricter
        if score < _MIN_SCORE_SEARCH:
            pruned.append(key)
            continue
        if not _hint_supports(key, text):
            pruned.append(key)
            continue
        kept.append(key)
        scores[key] = score

    return kept, pruned, scores


def _dominant_categories(keys: list[str], scores: dict[str, float]) -> set[str]:
    if not keys:
        return set()
    weights: Counter[str] = Counter()
    for k in keys:
        if k in _CORE:
            continue
        cap = get_capability(k)
        if not cap:
            continue
        weights[cap.category] += max(scores.get(k, 0.5), 0.3)
    if not weights:
        return set()
    top = weights.most_common(3)
    # keep categories within 40% of top weight
    threshold = top[0][1] * 0.4
    return {c for c, w in top if w >= threshold}


def _coherence_filter(
    keys: list[str],
    scores: dict[str, float],
    *,
    request: str = "",
) -> tuple[list[str], list[str]]:
    """Drop outlier categories unless text clearly supports them."""
    text = _text_hints(request)
    dom = _dominant_categories(keys, scores)
    if not dom:
        return keys, []
    kept: list[str] = []
    pruned: list[str] = []
    for k in keys:
        if k in _CORE:
            kept.append(k)
            continue
        cap = get_capability(k)
        if not cap:
            pruned.append(k)
            continue
        if cap.category in dom:
            kept.append(k)
            continue
        # allow if strong score + text hint
        if scores.get(k, 0) >= 0.85 and _hint_supports(k, text):
            kept.append(k)
            continue
        # always allow explicit extractor-level product keys if hint matches
        if _hint_supports(k, text) and scores.get(k, 0) >= 0.7:
            kept.append(k)
            continue
        pruned.append(k)
    return kept, pruned


def _pack_dependency_map() -> dict[str, tuple[str, ...]]:
    """Optional dependencies declared in loaded capability packs."""
    try:
        from .packs import loaded_packs
        out: dict[str, tuple[str, ...]] = {}
        for pack in loaded_packs().values():
            for c in pack.capabilities:
                if c.dependencies:
                    out[c.key] = tuple(c.dependencies)
        return out
    except Exception:
        return {}


def _expand_dependencies(keys: Iterable[str]) -> tuple[list[str], list[str]]:
    selected: list[str] = []
    seen: set[str] = set()
    added_deps: list[str] = []
    pack_deps = _pack_dependency_map()

    def add(k: str, as_dep: bool = False) -> None:
        if k in seen or not _valid_key(k):
            return
        seen.add(k)
        selected.append(k)
        if as_dep:
            added_deps.append(k)

    for k in keys:
        add(k, as_dep=False)

    for _ in range(2):
        snapshot = list(selected)
        for k in snapshot:
            for dep in _DEPENDENCIES.get(k, ()) + pack_deps.get(k, ()):
                add(dep, as_dep=True)

    # companions only for dominant categories already in pack
    cats = {
        CAPABILITIES[k].category
        for k in selected
        if k in CAPABILITIES and k not in _CORE
    }
    for cat in cats:
        for comp in _CATEGORY_COMPANIONS.get(cat, ()):
            add(comp, as_dep=True)

    for core in _CORE:
        add(core, as_dep=False)

    return selected, added_deps


def _cap_pack(keys: list[str], scores: dict[str, float]) -> list[str]:
    if len(keys) <= _MAX_PACK:
        return keys
    core = [k for k in keys if k in _CORE]
    rest = [k for k in keys if k not in _CORE]
    rest.sort(key=lambda k: (-scores.get(k, 0.5), k))
    return core + rest[: max(0, _MAX_PACK - len(core))]


def _detect_conflicts(keys: list[str]) -> list[str]:
    conflicts: list[str] = []
    s = set(keys)
    if "lock_chat" in s and "welcome_set" in s:
        conflicts.append("lock_chat + welcome_set: الترحيب قد لا يظهر مع قفل الدردشة")
    if "echo" in s and len(s) > 5:
        conflicts.append("echo مع حزمة كبيرة: الرد الآلي قد يتعارض مع handlers أخرى")
    return conflicts


def synthesize_from_keys(
    keys: Iterable[str],
    *,
    scores: dict[str, float] | None = None,
    request: str = "",
    source_status: str = "",
    confidence: float = 0.0,
) -> SynthesisPlan:
    scores = dict(scores or {})
    raw = [k for k in keys if _valid_key(k)]
    for k in raw:
        scores.setdefault(k, 1.0)

    # noise filter (string path — treat as extractor)
    matched = [MatchedCapability(
        key=k,
        service=(get_capability(k).service if get_capability(k) else ""),
        method=(get_capability(k).method if get_capability(k) else ""),
        category=(get_capability(k).category if get_capability(k) else ""),
        description_ar=(get_capability(k).description_ar if get_capability(k) else ""),
        description_en=(get_capability(k).description_en if get_capability(k) else ""),
        score=scores.get(k, 1.0),
        source="extractor",
    ) for k in raw]
    kept, pruned1, sc = _filter_matches(matched, request=request)
    scores.update(sc)
    kept2, pruned2 = _coherence_filter(kept, scores, request=request)
    expanded, deps = _expand_dependencies(kept2)
    for d in deps:
        scores.setdefault(d, 0.6)
    ordered = _cap_pack(expanded, scores)
    # stable: core first then alpha among rest for determinism after score cap
    core = [k for k in _CORE if k in ordered]
    rest = sorted(k for k in ordered if k not in _CORE)
    # re-sort rest by score desc then name
    rest.sort(key=lambda k: (-scores.get(k, 0.5), k))
    ordered = core + rest

    cats = sorted({
        CAPABILITIES[k].category
        for k in ordered
        if k in CAPABILITIES
    })
    conflicts = _detect_conflicts(ordered)
    pruned = list(dict.fromkeys(pruned1 + pruned2))
    warnings: list[str] = []
    if deps:
        warnings.append("أُضيفت اعتماديات: " + "، ".join(deps[:8]))
    if pruned:
        warnings.append("تُصفية ضوضاء: " + "، ".join(pruned[:8]))

    if not ordered or set(ordered).issubset(set(_CORE)):
        status = "empty" if not ordered else "partial"
    else:
        status = "ok"

    return SynthesisPlan(
        keys=ordered,
        categories=cats,
        added_dependencies=deps,
        pruned=pruned,
        conflicts=conflicts,
        warnings=warnings,
        status=status,
        source_status=source_status,
        confidence=confidence,
    )


def synthesize_from_report(report: DetectionReport) -> SynthesisPlan:
    matched = list(report.matched or [])
    # Build from scored matches directly
    kept, pruned1, scores = _filter_matches(matched, request=report.request or "")
    kept2, pruned2 = _coherence_filter(kept, scores, request=report.request or "")
    expanded, deps = _expand_dependencies(kept2)
    for d in deps:
        scores.setdefault(d, 0.6)
    ordered = _cap_pack(expanded, scores)
    core = [k for k in _CORE if k in ordered]
    rest = sorted(k for k in ordered if k not in _CORE)
    rest.sort(key=lambda k: (-scores.get(k, 0.5), k))
    ordered = core + rest

    cats = sorted({
        CAPABILITIES[k].category
        for k in ordered
        if k in CAPABILITIES
    })
    conflicts = _detect_conflicts(ordered)
    pruned = list(dict.fromkeys(pruned1 + pruned2))
    warnings: list[str] = []
    if deps:
        warnings.append("أُضيفت اعتماديات: " + "، ".join(deps[:8]))
    if pruned:
        warnings.append("تُصفية ضوضاء: " + "، ".join(pruned[:8]))

    status = "ok"
    if report.status == DetectionStatus.IMPOSSIBLE:
        return SynthesisPlan(
            keys=[],
            status="empty",
            source_status=report.status.value,
            confidence=float(report.confidence or 0),
            warnings=["الطلب مرفوض من بوابة الجدوى"],
            pruned=pruned,
        )
    if not ordered or set(ordered).issubset(set(_CORE)):
        status = "empty" if not ordered else "partial"
    if report.status == DetectionStatus.GAP and ordered:
        status = "partial"
        warnings.append("توليد جزئي: بعض الميزات المطلوبة غير متاحة في السجل")

    return SynthesisPlan(
        keys=ordered,
        categories=cats,
        added_dependencies=deps,
        pruned=pruned,
        conflicts=conflicts,
        warnings=warnings,
        status=status,
        source_status=report.status.value if report.status else "",
        confidence=float(report.confidence or 0),
    )


def synthesize_for_request(request: str) -> tuple[DetectionReport, SynthesisPlan]:
    from .engine import detect_capabilities

    report = detect_capabilities(request or "")
    plan = synthesize_from_report(report)
    return report, plan


__all__ = [
    "SynthesisPlan",
    "synthesize_from_keys",
    "synthesize_from_report",
    "synthesize_for_request",
]
