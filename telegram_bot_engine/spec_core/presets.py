"""Zero-AI presets: map plain-language requests to BotSpec packs.

Used when the user asks for a common bot type (e.g. group management)
without going through the button builder or any LLM.
"""
from __future__ import annotations

import re
from typing import Iterable

from .builder import BuilderSession
from .schema import BotSpec

# keyword packs (Arabic + English), lowercase match
_GROUP_KEYS = (
    "اداره مجموعات",
    "إدارة مجموعات",
    "ادارة مجموعات",
    "إدارة جروب",
    "ادارة جروب",
    "إدارة مجموعة",
    "مشرف",
    "moderation",
    "group management",
    "group admin",
    "admin bot",
    "حظر",
    "كتم",
    "طرد",
    "ترحيب",
)
_TASK_KEYS = (
    "مهام",
    "task",
    "todo",
    "to-do",
)
_SUPPORT_KEYS = (
    "تذاكر",
    "دعم",
    "support",
    "ticket",
    "helpdesk",
)
_NOTES_KEYS = (
    "ملاحظات",
    "notes",
)
_SECURITY_KEYS = (
    "امن", "أمن", "سيبراني", "security", "cyber", "phishing", "تصيد", "تصيّد",
    "بلاغ", "incident", "soc", "توعية",
)

_GROUP_CAPS = (
    "start",
    "help",
    "rules",
    "announce",
    "user_ban",
    "user_unban",
    "user_mute",
    "user_unmute",
    "user_kick",
    "user_warn",
    "user_promote",
    "user_demote",
    "pin_message",
    "delete_message",
    "welcome_set",
    "welcome_toggle",
    "welcome_show",
    "welcome_test",
    "my_id",
)
_TASK_CAPS = ("start", "help", "task_add", "task_list", "task_done", "task_delete", "task_clear")
_SUPPORT_CAPS = (
    "start",
    "help",
    "ticket_open",
    "ticket_my",
    "ticket_list",
    "ticket_reply",
    "ticket_close",
    "ticket_status",
)
_NOTES_CAPS = ("start", "help", "note_add", "note_list", "note_delete")
_SECURITY_CAPS = (
    "start", "help", "sec_report_phish", "sec_report_incident",
    "sec_checklist", "sec_list_reports", "sec_close_report", "rules", "my_id",
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _has_any(text: str, keys: Iterable[str]) -> bool:
    t = _norm(text)
    return any(k in t for k in keys)


def detect_preset(request: str) -> str | None:
    """Return preset id or None.

    Order: most specific packs first. Generic "bot" requests fall through
    to caller (use default_spec_from_request for guaranteed delivery).
    """
    if _has_any(request, _GROUP_KEYS):
        return "group_management"
    if _has_any(request, _SUPPORT_KEYS):
        return "support_tickets"
    if _has_any(request, _TASK_KEYS):
        return "tasks"
    if _has_any(request, _NOTES_KEYS):
        return "notes"
    if _has_any(request, _SECURITY_KEYS):
        return "security_ops"
    return None


def is_bot_request(request: str) -> bool:
    t = _norm(request)
    keys = (
        "بوت", "bot", "telegram", "تيليجرام", "تليجرام", "tg ",
        "اعمل", "أنشئ", "انشئ", "سوي", "أبغى", "ابي", "أريد", "عايز", "عاوز",
        "create", "make", "build",
    )
    return any(k in t for k in keys)


# Full marketplace-grade default pack: group admin + welcome + tickets + basics
_DEFAULT_CAPS = tuple(dict.fromkeys(
    list(_GROUP_CAPS) + list(_SUPPORT_CAPS) + ["ping", "about"]
))


def default_spec_from_request(request: str, *, user_id: int = 0) -> BotSpec:
    """Always-on high-quality pack when the user asks for a bot.

    Guarantees delivery without AI. Biased toward group operations because
    that is the highest-demand product surface.
    """
    preset = detect_preset(request) or "group_management"
    # If pure generic bot request with no domain, still use group_management
    # as the market default (admins + welcome + tools).
    if preset == "group_management" and _has_any(request, _SUPPORT_KEYS):
        preset = "support_tickets"
    s = session_for_preset(preset, user_id=user_id)
    # Enrich default name from request snippet
    if not s.bot_name or s.bot_name in {"group_admin_bot", "custom_bot", "my_bot"}:
        s.set_name("market_bot")
    return s.to_spec()


def session_for_preset(preset: str, *, user_id: int = 0, bot_name: str = "") -> BuilderSession:
    s = BuilderSession(user_id=user_id)
    if preset == "group_management":
        s.set_name(bot_name or "group_admin_bot")
        s.set_description("بوت إدارة مجموعات: حظر/كتم/طرد/ترحيب/قوانين")
        for k in _GROUP_CAPS:
            s.selected.add(k)
    elif preset == "support_tickets":
        s.set_name(bot_name or "support_bot")
        s.set_description("بوت تذاكر دعم")
        for k in _SUPPORT_CAPS:
            s.selected.add(k)
    elif preset == "tasks":
        s.set_name(bot_name or "tasks_bot")
        s.set_description("بوت مهام شخصية")
        for k in _TASK_CAPS:
            s.selected.add(k)
    elif preset == "notes":
        s.set_name(bot_name or "notes_bot")
        s.set_description("بوت ملاحظات")
        for k in _NOTES_CAPS:
            s.selected.add(k)
    elif preset == "security_ops":
        s.set_name(bot_name or "security_ops_bot")
        s.set_description("بوت عمليات أمنية دفاعية: بلاغات وتوعية")
        for k in _SECURITY_CAPS:
            s.selected.add(k)
    else:
        s.set_name(bot_name or "custom_bot")
        s.selected.update({"start", "help"})
    return s


def spec_from_request(request: str, *, user_id: int = 0) -> BotSpec | None:
    preset = detect_preset(request)
    if not preset:
        return None
    return session_for_preset(preset, user_id=user_id).to_spec()


__all__ = ["detect_preset", "session_for_preset", "spec_from_request", "is_bot_request", "default_spec_from_request"]
