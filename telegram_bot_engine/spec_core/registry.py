"""Capability Registry — fixed executable features (no AI).

Only features listed here can appear in a valid BotSpec.
Coding Engine maps each key → deterministic PTB v21 implementation.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Capability:
    key: str
    service: str
    method: str
    description_ar: str
    description_en: str
    default_actor: str = "user"
    permissions: tuple[str, ...] = ()
    needs_target_user: bool = False
    category: str = "general"


CAPABILITIES: dict[str, Capability] = {
    # ── core ──────────────────────────────────────────────────────────
    "start": Capability(
        key="start", service="core", method="start",
        description_ar="ترحيب وعرض الأزرار الرئيسية",
        description_en="Welcome and main buttons",
        category="core",
    ),
    "help": Capability(
        key="help", service="core", method="help",
        description_ar="عرض المساعدة",
        description_en="Show help",
        category="core",
    ),
    "about": Capability(
        key="about", service="core", method="about",
        description_ar="عن البوت",
        description_en="About the bot",
        category="core",
    ),
    "ping": Capability(
        key="ping", service="core", method="ping",
        description_ar="فحص أن البوت يعمل",
        description_en="Health ping",
        category="core",
    ),
    "my_id": Capability(
        key="my_id", service="core", method="my_id",
        description_ar="عرض معرف المستخدم والمحادثة",
        description_en="Show user and chat ids",
        category="core",
    ),
    "rules": Capability(
        key="rules", service="content", method="rules",
        description_ar="عرض قوانين المجموعة",
        description_en="Show group rules",
        category="content",
    ),
    "announce": Capability(
        key="announce", service="content", method="announce",
        description_ar="إعلان للمشرفين في المحادثة",
        description_en="Admin announcement",
        default_actor="admin",
        category="content",
    ),
    # ── moderation ────────────────────────────────────────────────────
    "user_ban": Capability(
        key="user_ban", service="moderation", method="ban_user",
        description_ar="حظر مستخدم من المجموعة",
        description_en="Ban a user from the chat",
        default_actor="admin", permissions=("ban_users",),
        needs_target_user=True, category="moderation",
    ),
    "user_unban": Capability(
        key="user_unban", service="moderation", method="unban_user",
        description_ar="إلغاء حظر مستخدم",
        description_en="Unban a user",
        default_actor="admin", permissions=("ban_users",),
        needs_target_user=True, category="moderation",
    ),
    "user_mute": Capability(
        key="user_mute", service="moderation", method="mute_user",
        description_ar="كتم مستخدم",
        description_en="Mute a user",
        default_actor="admin", permissions=("restrict_members",),
        needs_target_user=True, category="moderation",
    ),
    "user_unmute": Capability(
        key="user_unmute", service="moderation", method="unmute_user",
        description_ar="إلغاء كتم مستخدم",
        description_en="Unmute a user",
        default_actor="admin", permissions=("restrict_members",),
        needs_target_user=True, category="moderation",
    ),
    "user_kick": Capability(
        key="user_kick", service="moderation", method="kick_user",
        description_ar="طرد مستخدم",
        description_en="Kick a user",
        default_actor="admin", permissions=("ban_users",),
        needs_target_user=True, category="moderation",
    ),
    "user_warn": Capability(
        key="user_warn", service="moderation", method="warn_user",
        description_ar="تحذير مستخدم",
        description_en="Warn a user",
        default_actor="admin", permissions=("ban_users",),
        needs_target_user=True, category="moderation",
    ),
    "user_promote": Capability(
        key="user_promote", service="moderation", method="promote_user",
        description_ar="ترقية مشرف",
        description_en="Promote member to admin",
        default_actor="owner", permissions=("promote_members",),
        needs_target_user=True, category="moderation",
    ),
    "user_demote": Capability(
        key="user_demote", service="moderation", method="demote_user",
        description_ar="إلغاء إشراف",
        description_en="Demote admin",
        default_actor="owner", permissions=("promote_members",),
        needs_target_user=True, category="moderation",
    ),
    "pin_message": Capability(
        key="pin_message", service="moderation", method="pin_message",
        description_ar="تثبيت رسالة (بالرد)",
        description_en="Pin replied message",
        default_actor="admin", permissions=("pin_messages",),
        category="moderation",
    ),
    "delete_message": Capability(
        key="delete_message", service="moderation", method="delete_message",
        description_ar="حذف رسالة (بالرد)",
        description_en="Delete replied message",
        default_actor="admin", permissions=("delete_messages",),
        category="moderation",
    ),
    # ── tasks ─────────────────────────────────────────────────────────
    "task_add": Capability(
        key="task_add", service="tasks", method="add_task",
        description_ar="إضافة مهمة",
        description_en="Add a task",
        category="tasks",
    ),
    "task_list": Capability(
        key="task_list", service="tasks", method="list_tasks",
        description_ar="عرض المهام",
        description_en="List tasks",
        category="tasks",
    ),
    "task_done": Capability(
        key="task_done", service="tasks", method="done_task",
        description_ar="تعليم تعليم مهمة كمكتملة",
        description_en="Mark task done",
        category="tasks",
    ),
    "task_delete": Capability(
        key="task_delete", service="tasks", method="delete_task",
        description_ar="حذف مهمة",
        description_en="Delete a task",
        category="tasks",
    ),
    "task_clear": Capability(
        key="task_clear", service="tasks", method="clear_tasks",
        description_ar="مسح كل المهام المكتملة",
        description_en="Clear completed tasks",
        category="tasks",
    ),
    # ── notes ─────────────────────────────────────────────────────────
    "note_add": Capability(
        key="note_add", service="notes", method="add_note",
        description_ar="إضافة ملاحظة شخصية",
        description_en="Add a personal note",
        category="notes",
    ),
    "note_list": Capability(
        key="note_list", service="notes", method="list_notes",
        description_ar="عرض الملاحظات",
        description_en="List notes",
        category="notes",
    ),
    "note_delete": Capability(
        key="note_delete", service="notes", method="delete_note",
        description_ar="حذف ملاحظة",
        description_en="Delete a note",
        category="notes",
    ),
    # ── welcome ─────────────────────────────────────────────────────
    "welcome_set": Capability(
        key="welcome_set", service="welcome", method="set_message",
        description_ar="تعيين رسالة الترحيب (ترحب بالأعضاء الجدد تلقائياً)",
        description_en="Set auto-welcome message for new members",
        default_actor="admin",
        category="welcome",
    ),
    "welcome_toggle": Capability(
        key="welcome_toggle", service="welcome", method="toggle",
        description_ar="تفعيل/إيقاف الترحيب التلقائي",
        description_en="Enable or disable auto-welcome",
        default_actor="admin",
        category="welcome",
    ),
    "welcome_show": Capability(
        key="welcome_show", service="welcome", method="show",
        description_ar="عرض إعدادات الترحيب الحالية",
        description_en="Show current welcome settings",
        default_actor="admin",
        category="welcome",
    ),
    "welcome_test": Capability(
        key="welcome_test", service="welcome", method="test",
        description_ar="تجربة رسالة الترحيب",
        description_en="Preview welcome message",
        default_actor="admin",
        category="welcome",
    ),
    # ── support tickets ─────────────────────────────────────────────
    "ticket_open": Capability(
        key="ticket_open", service="tickets", method="open_ticket",
        description_ar="فتح تذكرة دعم جديدة",
        description_en="Open a support ticket",
        category="tickets",
    ),
    "ticket_close": Capability(
        key="ticket_close", service="tickets", method="close_ticket",
        description_ar="إغلاق تذكرة دعم",
        description_en="Close a support ticket",
        category="tickets",
    ),
    "ticket_list": Capability(
        key="ticket_list", service="tickets", method="list_tickets",
        description_ar="عرض تذاكر الدعم (للمشرف: الكل / للمستخدم: تذاكره)",
        description_en="List support tickets",
        category="tickets",
    ),
    "ticket_my": Capability(
        key="ticket_my", service="tickets", method="my_tickets",
        description_ar="عرض تذاكري المفتوحة",
        description_en="List my open tickets",
        category="tickets",
    ),
    "ticket_reply": Capability(
        key="ticket_reply", service="tickets", method="reply_ticket",
        description_ar="الرد على تذكرة دعم",
        description_en="Reply to a support ticket",
        default_actor="admin",
        category="tickets",
    ),
    "ticket_status": Capability(
        key="ticket_status", service="tickets", method="ticket_status",
        description_ar="حالة تذكرة برقمها",
        description_en="Show ticket status by id",
        category="tickets",
    ),
}


def get_capability(key: str) -> Capability | None:
    return CAPABILITIES.get((key or "").strip().lower())


def list_capabilities() -> list[Capability]:
    return list(CAPABILITIES.values())


def known_keys() -> set[str]:
    return set(CAPABILITIES.keys())


def by_category() -> dict[str, list[Capability]]:
    out: dict[str, list[Capability]] = {}
    for cap in CAPABILITIES.values():
        out.setdefault(cap.category, []).append(cap)
    return out


__all__ = [
    "Capability",
    "CAPABILITIES",
    "get_capability",
    "list_capabilities",
    "known_keys",
    "by_category",
]
