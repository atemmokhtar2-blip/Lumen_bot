"""Domain lean packs — minimum viable feature sets for catalog bots.

Used by acceptance_gate and hybrid path so every major domain gets a
complete command surface (not start/help only).
"""
from __future__ import annotations

from typing import Iterable

# domain_key -> ordered feature keys (must exist in CAPABILITIES)
LEAN_PACKS: dict[str, tuple[str, ...]] = {
    "ecommerce": (
        "shop_catalog",
        "cart_view",
        "cart_add",
        "cart_checkout",
        "shop_my_orders",
    ),
    "group_moderation": (
        "welcome_set",
        "welcome_show",
        "user_ban",
        "user_warn",
        "delete_message",
        "rules",
    ),
    "tasks": (
        "task_add",
        "task_list",
        "task_done",
    ),
    "notes": (
        "note_add",
        "note_list",
    ),
    "tickets": (
        "ticket_open",
        "ticket_my",
        "faq_show",
    ),
    "healthcare": (
        "clinic_book",
        "clinic_my",
        "clinic_cancel",
        "book_slot",
        "book_list",
        "book_cancel",
    ),
    "crm": (
        "lead_capture",
        "lead_list",
        "lead_status",
        "followup_set",
    ),
    "education": (
        "course_list",
        "quiz_start",
        "progress_view",
    ),
    "cybersecurity": (
        "sec_dns_check",
        "sec_tls_check",
        "sec_http_check",
    ),
    "echo": (
        "echo",
    ),
    "pdf": (
        "pdf_start",
        "pdf_done",
        "pdf_clear",
        "pdf_status",
        "images_to_pdf",
    ),
    "fitness": (
        "gym_book",
        "gym_schedule",
        "book_slot",
        "book_list",
    ),
    "restaurant": (
        "shop_catalog",
        "cart_add",
        "cart_view",
        "cart_checkout",
    ),
    "auction": (
        "auction_list",
        "auction_bid",
        "auction_my_bids",
    ),
    "realestate": (
        "shop_catalog",
        "lead_capture",
        "lead_list",
    ),
}

_DOMAIN_ALIASES = {
    "ecommerce": "ecommerce",
    "marketplace": "ecommerce",
    "group_moderation": "group_moderation",
    "tasks": "tasks",
    "projects": "tasks",
    "healthcare": "healthcare",
    "education": "education",
    "crm": "crm",
    "cybersecurity": "cybersecurity",
    "social": "group_moderation",
    "fitness": "fitness",
    "restaurant": "restaurant",
    "auction": "auction",
    "realestate": "realestate",
    "gaming": "echo",
}


def pack_for_domain(primary: str | None) -> tuple[str, ...]:
    if not primary:
        return ()
    key = _DOMAIN_ALIASES.get(str(primary).strip().lower(), str(primary).strip().lower())
    return LEAN_PACKS.get(key, ())


def merge_keys(*groups: Iterable[str], catalog: set[str] | None = None) -> list[str]:
    out: list[str] = []
    for group in groups:
        for k in group:
            k = str(k).strip()
            if not k or k in out:
                continue
            if catalog is not None and k not in catalog:
                continue
            out.append(k)
    return out


__all__ = ["LEAN_PACKS", "merge_keys", "pack_for_domain"]
