"""Canonical command ↔ capability map (single source of truth).

Every layer that maps /slash → feature or feature → /slash MUST use this module.
Do not invent parallel alias tables in extract / bridge / seal / main_emit / gate.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Iterable

# Primary feature → telegram command id (menu + CommandHandler default)
# Kept here; builder.DEFAULT_COMMANDS re-exports for backward compatibility.
PRIMARY: dict[str, str] = {
    "start": "start",
    "help": "help",
    "about": "about",
    "ping": "ping",
    "my_id": "id",
    "rules": "rules",
    "announce": "announce",
    "user_ban": "ban",
    "user_unban": "unban",
    "user_mute": "mute",
    "user_unmute": "unmute",
    "user_kick": "kick",
    "user_warn": "warn",
    "user_promote": "promote",
    "user_demote": "demote",
    "pin_message": "pin",
    "delete_message": "delmsg",
    "task_add": "add",
    "task_list": "list",
    "task_done": "done",
    "task_delete": "delete",
    "task_clear": "clear",
    "note_add": "note",
    "note_list": "notes",
    "note_delete": "delnote",
    "welcome_set": "setwelcome",
    "welcome_toggle": "welcometoggle",
    "welcome_show": "welcomeshow",
    "welcome_test": "welcometest",
    "ticket_open": "ticket",
    "ticket_close": "closeticket",
    "ticket_list": "tickets",
    "ticket_my": "mytickets",
    "ticket_reply": "replyticket",
    "ticket_status": "ticketstatus",
    "faq_show": "faq",
    "broadcast_admin": "broadcast",
    "shop_catalog": "shop",
    "shop_add_item": "addproduct",
    "shop_order": "order",
    "shop_buy": "buy",
    "shop_orders": "orders",
    "shop_my_orders": "myorders",
    "wallet_balance": "balance",
    "wallet_topup": "topup",
    "wallet_history": "wallethistory",
    "wallet_transfer": "transfer",
    "cart_add": "cartadd",
    "cart_view": "cart",
    "cart_checkout": "cartcheckout",
    "plans": "plans",
    "subscribe": "subscribe",
    "my_sub": "mysub",
    "book_slot": "bookslot",
    "book_list": "booklist",
    "book_cancel": "bookcancel",
    "lang": "lang",
}

# Extra user-facing slash forms → feature (never invent features outside registry)
# Primary command from PRIMARY is also registered automatically in reverse().
EXTRA_ALIASES: dict[str, str] = {
    "products": "shop_catalog",
    "product": "shop_catalog",
    "catalog": "shop_catalog",
    "book": "book_slot",
    "booking": "book_slot",
    "faqs": "faq_show",
    "wallet": "wallet_balance",
    "cartcheck": "cart_checkout",
    "language": "lang",
}


@lru_cache(maxsize=1)
def _capabilities() -> frozenset[str]:
    try:
        from telegram_bot_engine.spec_core.registry import CAPABILITIES

        return frozenset(CAPABILITIES.keys())
    except Exception:
        return frozenset()


@lru_cache(maxsize=1)
def primary_commands() -> dict[str, str]:
    """feature → primary command id (registry-valid features only)."""
    caps = _capabilities()
    out: dict[str, str] = {}
    for feat, cmd in PRIMARY.items():
        if caps and feat not in caps:
            continue
        out[feat] = cmd
    # fill remaining capabilities with compact id
    for feat in caps:
        out.setdefault(feat, feat.replace("_", "")[:32])
    return out


@lru_cache(maxsize=1)
def reverse_map() -> dict[str, str]:
    """command id (any alias) → feature. Single reverse table for the whole engine."""
    caps = _capabilities()
    out: dict[str, str] = {}
    for feat, cmd in primary_commands().items():
        if isinstance(cmd, str) and cmd.strip():
            out.setdefault(cmd.strip().lower(), feat)
    for cmd, feat in EXTRA_ALIASES.items():
        if caps and feat not in caps:
            continue
        out[cmd.strip().lower()] = feat
    return out


def feature_for_command(cmd: str) -> str | None:
    if not cmd:
        return None
    return reverse_map().get(str(cmd).strip().lower())


def commands_for_feature(feat: str) -> list[str]:
    """All slash forms that should invoke *feat* (primary first)."""
    primary = primary_commands().get(feat)
    aliases = [cmd for cmd, f in reverse_map().items() if f == feat]
    ordered: list[str] = []
    if primary:
        ordered.append(primary)
    for a in sorted(aliases):
        if a not in ordered:
            ordered.append(a)
    return ordered


_SLASH_RE = re.compile(r"(?<!\w)/([A-Za-z][A-Za-z0-9_]{0,31})")


def slash_commands_in_text(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for m in _SLASH_RE.finditer(text or ""):
        cid = m.group(1).lower()
        if cid not in seen:
            seen.add(cid)
            out.append(cid)
    return out


def features_from_text(text: str, *, include_core: bool = True) -> list[str]:
    """Resolve every /slash in *text* to registry features (deduped, stable order)."""
    caps = _capabilities()
    feats: list[str] = []
    if include_core:
        for core in ("start", "help"):
            if not caps or core in caps:
                feats.append(core)
    rev = reverse_map()
    for cid in slash_commands_in_text(text):
        if cid in {"start", "help", "cancel", "lang"}:
            if cid == "lang" and (not caps or "lang" in caps) and "lang" not in feats:
                feats.append("lang")
            continue
        feat = rev.get(cid)
        if feat and feat not in feats:
            if not caps or feat in caps:
                feats.append(feat)
    return feats


def protected_features(text: str) -> set[str]:
    """Features the user explicitly named — must never be domain-stripped."""
    return set(features_from_text(text, include_core=False))


def is_registry_feature(name: str) -> bool:
    caps = _capabilities()
    if not caps:
        return True
    return name in caps


__all__ = [
    "PRIMARY",
    "EXTRA_ALIASES",
    "primary_commands",
    "reverse_map",
    "feature_for_command",
    "commands_for_feature",
    "slash_commands_in_text",
    "features_from_text",
    "protected_features",
    "is_registry_feature",
]
