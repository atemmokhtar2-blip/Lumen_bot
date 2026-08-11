"""Phase 3 — Template Synthesis Engine.

Composes matched registry capabilities into a coherent, validated pack
for generation. Deterministic only — no web, no LLM.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from ...spec_core.registry import CAPABILITIES, Capability, get_capability
from .models import DetectionReport, DetectionStatus, MatchedCapability
from .search import is_bulk_key

# Soft dependencies: if A is selected, also include B when present in registry
_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "cart_view": ("shop_catalog",),
    "cart_add": ("shop_catalog", "cart_view"),
    "cart_checkout": ("shop_catalog", "cart_view"),
    "coupon_apply": ("shop_catalog",),
    "shop_order": ("shop_catalog",),
    "shop_buy": ("shop_catalog",),
    "shop_my_orders": ("shop_catalog",),
    "draw_winner": ("contests",),
    "join_contest": ("contests",),
    "new_contest": ("contests",),
    "end_contest": ("contests",),
    "welcome_toggle": ("welcome_set",),
    "welcome_show": ("welcome_set",),
    "welcome_test": ("welcome_set",),
    "verify_ok": ("verify_start",),
    "ticket_my": ("ticket_open",),
    "ticket_close": ("ticket_open",),
    "ticket_reply": ("ticket_open",),
    "subscribe": ("plans",),
    "my_sub": ("plans",),
    "book_list": ("book_slot",),
    "book_cancel": ("book_slot",),
    "redeem_points": ("balance",),
    "points_history": ("balance",),
    "grant_points": ("balance",),
    "leaderboard": ("balance",),
    "referral_invite": ("referral_code",),
    "user_unban": ("user_ban",),
    "user_unmute": ("user_mute",),
}

# Category affinity: co-include lightweight companions when category is present
_CATEGORY_COMPANIONS: dict[str, tuple[str, ...]] = {
    "welcome": ("rules",),
    "moderation": ("rules", "user_info"),
    "shop": ("cart_view",),
    "contests": ("draw_winner",),
    "tickets": ("ticket_my",),
    "booking": ("book_list",),
}

_CORE = ("start", "help")


@dataclass
class SynthesisPlan:
    """Validated capability pack ready for generation."""

    keys: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    added_dependencies: list[str] = field(default_factory=list)
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
    return True


def _expand_dependencies(keys: Iterable[str]) -> tuple[list[str], list[str]]:
    selected: list[str] = []
    seen: set[str] = set()
    added_deps: list[str] = []

    def add(k: str, as_dep: bool = False) -> None:
        if k in seen or not _valid_key(k):
            return
        seen.add(k)
        selected.append(k)
        if as_dep:
            added_deps.append(k)

    for k in keys:
        add(k, as_dep=False)

    # iterative dependency expansion (max 2 passes)
    for _ in range(2):
        snapshot = list(selected)
        for k in snapshot:
            for dep in _DEPENDENCIES.get(k, ()):
                before = len(seen)
                add(dep, as_dep=True)
                if len(seen) > before and dep not in snapshot:
                    pass

    # category companions (only if related key already present)
    cats = {CAPABILITIES[k].category for k in selected if k in CAPABILITIES}
    for cat in cats:
        for comp in _CATEGORY_COMPANIONS.get(cat, ()):
            add(comp, as_dep=True)

    for core in _CORE:
        add(core, as_dep=False)

    return selected, added_deps


def _detect_conflicts(keys: list[str]) -> list[str]:
    """Lightweight conflict notes (informational)."""
    conflicts: list[str] = []
    set_keys = set(keys)
    # Example soft conflicts — keep minimal
    if "lock_chat" in set_keys and "welcome_set" in set_keys:
        conflicts.append("lock_chat + welcome_set: الترحيب قد لا يظهر والدردشة مقفلة")
    return conflicts


def synthesize_from_keys(
    keys: Iterable[str],
    *,
    source_status: str = "",
    confidence: float = 0.0,
) -> SynthesisPlan:
    raw = [k for k in keys if _valid_key(k)]
    expanded, deps = _expand_dependencies(raw)
    # stable order: core first, then alpha
    core = [k for k in _CORE if k in expanded]
    rest = sorted(k for k in expanded if k not in _CORE)
    ordered = core + rest
    cats = sorted(
        {
            CAPABILITIES[k].category
            for k in ordered
            if k in CAPABILITIES
        }
    )
    conflicts = _detect_conflicts(ordered)
    warnings: list[str] = []
    if deps:
        warnings.append(f"أُضيفت اعتماديات: {', '.join(deps[:8])}")
    if not ordered:
        status = "empty"
    elif len(ordered) <= 2 and set(ordered).issubset(set(_CORE)):
        status = "partial"
    else:
        status = "ok"
    return SynthesisPlan(
        keys=ordered,
        categories=cats,
        added_dependencies=deps,
        conflicts=conflicts,
        warnings=warnings,
        status=status,
        source_status=source_status,
        confidence=confidence,
    )


def synthesize_from_report(report: DetectionReport) -> SynthesisPlan:
    keys = [m.key for m in report.matched if isinstance(m, MatchedCapability)]
    if not keys:
        keys = [m.key for m in report.matched]
    plan = synthesize_from_keys(
        keys,
        source_status=report.status.value if report.status else "",
        confidence=float(report.confidence or 0),
    )
    if report.status == DetectionStatus.GAP and plan.keys:
        plan.warnings.append("توليد جزئي: بعض الميزات المطلوبة غير متاحة في السجل")
        plan.status = "partial" if plan.status == "ok" else plan.status
    if report.status == DetectionStatus.IMPOSSIBLE:
        plan.status = "empty"
        plan.keys = []
        plan.warnings.append("الطلب مرفوض من بوابة الجدوى")
    return plan


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
