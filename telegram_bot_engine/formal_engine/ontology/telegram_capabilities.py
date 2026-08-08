"""
Telegram Bot API capabilities — structural ontology only.

Maps surface language (AR/EN) → concrete Bot API methods.
This is NOT a domain template pack (no shop/tickets/admin-bot skeletons).
It only names what the Telegram API can do so the transpiler can emit real calls
when the user's command text evidences that capability.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TelegramCapability:
    """One Telegram Bot API capability the formal engine can emit."""

    id: str
    """Canonical id used in contracts / inference."""
    api_method: str
    """python-telegram-bot Bot method name, e.g. ban_chat_member."""
    surface_forms: tuple[str, ...]
    """Literal / stem forms that evidence this capability (matching aids only)."""
    needs_user_target: bool = True
    """Requires a target user (reply / id / @username / mention)."""
    needs_chat: bool = True
    """Requires a chat_id (group/supergroup/channel)."""
    admin_typical: bool = True
    """Usually restricted to admins; extractor may set admin_only."""
    description: str = ""


# Structural catalog derived from Telegram Bot API — not product templates.
TELEGRAM_CAPABILITIES: tuple[TelegramCapability, ...] = (
    TelegramCapability(
        id="ban_chat_member",
        api_method="ban_chat_member",
        surface_forms=(
            "ban", "حظر", "احظر", "بند", "بان", "block user", "blocked",
            "اطرد نهائي", "حظر عضو", "حظر المستخدم",
        ),
        description="Ban a user from a chat",
    ),
    TelegramCapability(
        id="unban_chat_member",
        api_method="unban_chat_member",
        surface_forms=(
            "unban", "فك الحظر", "الغاء الحظر", "إلغاء الحظر", "رفع الحظر",
            "unban user", "unblock",
        ),
        description="Unban a user in a chat",
    ),
    TelegramCapability(
        id="kick_chat_member",
        api_method="ban_chat_member",  # kick = ban then unban
        surface_forms=(
            "kick", "طرد", "اطرد", " extrinsic", "remove member", "kick user",
        ),
        description="Remove a user from a chat (ban + unban)",
    ),
    TelegramCapability(
        id="restrict_chat_member",
        api_method="restrict_chat_member",
        surface_forms=(
            "mute", "كتم", "اكتم", "تقييد", "restrict", "silence",
            "منع الكتابة", "كتم عضو", "mute user",
        ),
        description="Restrict a member (mute)",
    ),
    TelegramCapability(
        id="unrestrict_chat_member",
        api_method="restrict_chat_member",  # with all permissions True
        surface_forms=(
            "unmute", "فك الكتم", "الغاء الكتم", "إلغاء الكتم", "رفع التقييد",
            "unrestrict", "unmute user",
        ),
        description="Remove restrictions from a member",
    ),
    TelegramCapability(
        id="promote_chat_member",
        api_method="promote_chat_member",
        surface_forms=(
            "promote", "ترقية", "رقّي", "رقي", "اجعله مشرف", "تعيين مشرف",
            "make admin", "promote admin",
        ),
        description="Promote a member to admin",
    ),
    TelegramCapability(
        id="delete_message",
        api_method="delete_message",
        surface_forms=(
            "delete message", "حذف رسالة", "امسح الرسالة", "احذف الرسالة",
            "delmsg", "purge message",
        ),
        needs_user_target=False,
        description="Delete a message (reply target)",
    ),
    TelegramCapability(
        id="pin_chat_message",
        api_method="pin_chat_message",
        surface_forms=(
            "pin", "تثبيت", "ثبت", "ثبت الرسالة", "pin message",
        ),
        needs_user_target=False,
        description="Pin a message",
    ),
    TelegramCapability(
        id="unpin_chat_message",
        api_method="unpin_chat_message",
        surface_forms=(
            "unpin", "الغاء التثبيت", "إلغاء التثبيت", "فك التثبيت",
        ),
        needs_user_target=False,
        description="Unpin a message",
    ),
)


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    s = s.replace("ة", "ه").replace("ى", "ي")
    return s


def resolve_capabilities(*texts: str) -> list[str]:
    """
    Return capability ids evidenced by any of the given text fragments.
    Matching is lexical only — never invents capabilities not evidenced.
    """
    blob = _norm(" ".join(t for t in texts if t))
    if not blob:
        return []
    # also split on non-alnum for token presence
    tokens = set(blob.replace("/", " ").replace("_", " ").split())
    found: list[str] = []
    seen: set[str] = set()
    for cap in TELEGRAM_CAPABILITIES:
        for form in cap.surface_forms:
            nf = _norm(form)
            if not nf:
                continue
            if nf in blob or nf in tokens or any(nf == t or nf in t for t in tokens):
                if cap.id not in seen:
                    seen.add(cap.id)
                    found.append(cap.id)
                break
    return found


def capability_by_id(cap_id: str) -> TelegramCapability | None:
    for c in TELEGRAM_CAPABILITIES:
        if c.id == cap_id:
            return c
    return None


def any_needs_user_target(cap_ids: list[str]) -> bool:
    for cid in cap_ids:
        c = capability_by_id(cid)
        if c and c.needs_user_target:
            return True
    return False


def any_admin_typical(cap_ids: list[str]) -> bool:
    for cid in cap_ids:
        c = capability_by_id(cid)
        if c and c.admin_typical:
            return True
    return False
