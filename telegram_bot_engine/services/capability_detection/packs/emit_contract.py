"""Emit contract — which (service, method) pairs the Zero-AI emitters support.

Packs that only use known pairs are **generation-safe**.
Unknown methods are allowed only as explicit stub overlays (documented risk).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ....spec_core.registry import CAPABILITIES

# Services that coding.py / handlers can emit real modules for
KNOWN_SERVICES: frozenset[str] = frozenset({
    "moderation", "tasks", "notes", "welcome", "tickets", "content",
    "security", "market", "generic", "shop", "cart", "points", "subs",
    "booking", "notify", "growth", "utils", "gate", "core", "admin",
    "crm", "edu", "clinic", "wallet", "polls", "faq", "reminders",
    "translate", "ocr", "scheduler",
})

# Methods with dedicated branches in coding_handlers / market templates
# (subset of high-value methods; unknown methods fall back to generic stub)
KNOWN_METHODS: frozenset[str] = frozenset({
    "ban", "unban", "mute", "unmute", "kick", "warn", "promote", "demote",
    "pin", "delete", "lock", "unlock",
    "set_message", "toggle", "format_welcome", "get_settings",
    "open_ticket", "close_ticket", "list_tickets", "reply_ticket",
    "add_task", "list_tasks", "done_task", "delete_task",
    "add_note", "list_notes", "delete_note",
    "rules", "faq", "about", "announce",
    "catalog", "add_to_cart", "view_cart", "checkout", "apply_coupon",
    "balance", "grant", "debit", "leaderboard", "redeem",
    "plans", "subscribe", "my_sub",
    "book_slot", "list_bookings", "cancel_booking",
    "verify_start", "verify_ok",
    "start", "help", "echo", "random_pick",
    "broadcast_segment", "smart_broadcast",
    "referral_code", "referral_stats",
    "translate", "translate_toggle", "ocr_image", "ocr_hint",
    "schedule_note", "job_list", "job_cancel",
})


@dataclass
class EmitAssessment:
    key: str
    service: str
    method: str
    safe: bool
    level: str  # safe | stub | unknown_service
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "service": self.service,
            "method": self.method,
            "safe": self.safe,
            "level": self.level,
            "notes": list(self.notes),
        }


def assess_capability(key: str, service: str, method: str) -> EmitAssessment:
    notes: list[str] = []
    svc = (service or "").strip().lower()
    meth = (method or "").strip().lower()
    if svc not in KNOWN_SERVICES:
        return EmitAssessment(
            key=key, service=svc, method=meth, safe=False,
            level="unknown_service",
            notes=[f"service {svc!r} has no deterministic emitter module"],
        )
    if meth in KNOWN_METHODS:
        return EmitAssessment(
            key=key, service=svc, method=meth, safe=True,
            level="safe", notes=["known emitter method"],
        )
    # service known but method not — generic stub path
    notes.append(
        f"method {meth!r} not in known emitter branches; "
        "will fall back to generic/stub handler if selected"
    )
    return EmitAssessment(
        key=key, service=svc, method=meth, safe=False,
        level="stub", notes=notes,
    )


def assess_pack_capabilities(capabilities: list[Any]) -> list[EmitAssessment]:
    out: list[EmitAssessment] = []
    for c in capabilities:
        key = getattr(c, "key", None) or (c.get("key") if isinstance(c, dict) else "")
        service = getattr(c, "service", None) or (c.get("service") if isinstance(c, dict) else "")
        method = getattr(c, "method", None) or (c.get("method") if isinstance(c, dict) else "")
        out.append(assess_capability(str(key), str(service), str(method)))
    return out


def known_service_method_pairs(*, limit: int = 200) -> list[tuple[str, str]]:
    """Sample existing registry pairs as authoring reference."""
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for cap in CAPABILITIES.values():
        if cap.service in KNOWN_SERVICES and cap.method in KNOWN_METHODS:
            t = (cap.service, cap.method)
            if t not in seen:
                seen.add(t)
                pairs.append(t)
        if len(pairs) >= limit:
            break
    return pairs


__all__ = [
    "KNOWN_SERVICES",
    "KNOWN_METHODS",
    "EmitAssessment",
    "assess_capability",
    "assess_pack_capabilities",
    "known_service_method_pairs",
]
