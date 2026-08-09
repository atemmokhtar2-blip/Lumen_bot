"""Capability Registry V1 — fixed executable features (no AI).

Each capability maps to a deterministic code emitter used by the Coding Engine.
Only features listed here can appear in a valid BotSpec.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


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


# ── First 10 capabilities ───────────────────────────────────────────────

CAPABILITIES: dict[str, Capability] = {
    "start": Capability(
        key="start",
        service="core",
        method="start",
        description_ar="ترحيب وعرض الأزرار الرئيسية",
        description_en="Welcome and main buttons",
        category="core",
    ),
    "help": Capability(
        key="help",
        service="core",
        method="help",
        description_ar="عرض المساعدة",
        description_en="Show help",
        category="core",
    ),
    "user_ban": Capability(
        key="user_ban",
        service="moderation",
        method="ban_user",
        description_ar="حظر مستخدم من المجموعة",
        description_en="Ban a user from the chat",
        default_actor="admin",
        permissions=("ban_users",),
        needs_target_user=True,
        category="moderation",
    ),
    "user_unban": Capability(
        key="user_unban",
        service="moderation",
        method="unban_user",
        description_ar="إلغاء حظر مستخدم",
        description_en="Unban a user",
        default_actor="admin",
        permissions=("ban_users",),
        needs_target_user=True,
        category="moderation",
    ),
    "user_mute": Capability(
        key="user_mute",
        service="moderation",
        method="mute_user",
        description_ar="كتم مستخدم",
        description_en="Mute a user",
        default_actor="admin",
        permissions=("restrict_members",),
        needs_target_user=True,
        category="moderation",
    ),
    "user_warn": Capability(
        key="user_warn",
        service="moderation",
        method="warn_user",
        description_ar="تحذير مستخدم",
        description_en="Warn a user",
        default_actor="admin",
        permissions=("ban_users",),
        needs_target_user=True,
        category="moderation",
    ),
    "task_add": Capability(
        key="task_add",
        service="tasks",
        method="add_task",
        description_ar="إضافة مهمة",
        description_en="Add a task",
        category="tasks",
    ),
    "task_list": Capability(
        key="task_list",
        service="tasks",
        method="list_tasks",
        description_ar="عرض المهام",
        description_en="List tasks",
        category="tasks",
    ),
    "task_done": Capability(
        key="task_done",
        service="tasks",
        method="done_task",
        description_ar="تعليم تعليم مهمة كمكتملة",
        description_en="Mark task done",
        category="tasks",
    ),
    "task_delete": Capability(
        key="task_delete",
        service="tasks",
        method="delete_task",
        description_ar="حذف مهمة",
        description_en="Delete a task",
        category="tasks",
    ),
}


def get_capability(key: str) -> Capability | None:
    return CAPABILITIES.get((key or "").strip().lower())


def list_capabilities() -> list[Capability]:
    return list(CAPABILITIES.values())


def known_keys() -> set[str]:
    return set(CAPABILITIES.keys())


__all__ = [
    "Capability",
    "CAPABILITIES",
    "get_capability",
    "list_capabilities",
    "known_keys",
]
