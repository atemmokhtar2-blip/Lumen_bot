"""Interactive Spec Builder — zero-AI, button-driven BotSpec assembly."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from .registry import CAPABILITIES, by_category, get_capability
from .schema import (
    Action,
    BotMeta,
    BotSpec,
    Feature,
    Messages,
    StartButton,
    StorageSpec,
    Trigger,
)


# Default command ids when user enables a capability from the menu
DEFAULT_COMMANDS: dict[str, str] = {
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
    "sec_report_phish": "phish",
    "sec_report_incident": "incident",
    "sec_checklist": "seccheck",
    "sec_list_reports": "secreports",
    "sec_close_report": "closereport",
    "faq_show": "faq",
    "broadcast_admin": "broadcast",
}

DEFAULT_SUCCESS_AR: dict[str, str] = {
    "user_ban": "تم حظر المستخدم",
    "user_unban": "تم إلغاء الحظر",
    "user_mute": "تم كتم المستخدم",
    "user_unmute": "تم إلغاء الكتم",
    "user_kick": "تم طرد المستخدم",
    "user_warn": "تم تحذير المستخدم",
    "task_add": "تمت إضافة المهمة",
    "task_done": "تم تعليم المهمة كمكتملة",
    "task_delete": "تم حذف المهمة",
    "ticket_open": "تم فتح التذكرة",
    "ticket_close": "تم إغلاق التذكرة",
    "ticket_reply": "تم إرسال الرد",
    "welcome_set": "تم حفظ رسالة الترحيب",
    "note_add": "تمت إضافة الملاحظة",
}


@dataclass
class BuilderSession:
    """Mutable session while a user builds a bot via menus."""

    user_id: int
    bot_name: str = "my_bot"
    language: str = "ar"
    description: str = ""
    selected: set[str] = field(default_factory=lambda: {"start", "help"})
    awaiting_name: bool = False
    awaiting_description: bool = False
    awaiting_try_token: bool = False
    last_project_path: str = ""
    last_project_id: str = ""

    def toggle(self, key: str) -> bool:
        key = (key or "").strip().lower()
        if key not in CAPABILITIES:
            return False
        if key in {"start", "help"}:
            self.selected.add(key)
            return True
        if key in self.selected:
            self.selected.discard(key)
        else:
            self.selected.add(key)
        return True

    def is_on(self, key: str) -> bool:
        return key in self.selected

    def set_name(self, name: str) -> None:
        name = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in (name or "").strip())
        self.bot_name = (name or "my_bot")[:40]

    def set_description(self, text: str) -> None:
        self.description = (text or "").strip()[:200]

    def needs_sqlite(self) -> bool:
        for key in self.selected:
            cap = get_capability(key)
            if cap and cap.service in {"tasks", "notes", "welcome", "tickets", "security"}:
                return True
        return False

    def summary_text(self) -> str:
        lines = [
            f"اسم البوت: {self.bot_name}",
            f"اللغة: {self.language}",
            f"الوصف: {self.description or '—'}",
            f"القدرات ({len(self.selected)}):",
        ]
        by_cat = by_category()
        for cat, caps in by_cat.items():
            on = [c.key for c in caps if c.key in self.selected]
            if on:
                lines.append(f"• {cat}: {', '.join(on)}")
        return "\n".join(lines)

    def to_spec(self) -> BotSpec:
        features: list[Feature] = []
        start_buttons: list[StartButton] = []

        # Ensure essentials
        selected = set(self.selected)
        selected.add("start")
        selected.add("help")

        for key in sorted(selected):
            cap = get_capability(key)
            if not cap:
                continue
            cmd = DEFAULT_COMMANDS.get(key, key.replace("_", ""))
            success = DEFAULT_SUCCESS_AR.get(key, "تم بنجاح")
            failure = "فشل التنفيذ"
            actor = cap.default_actor if cap.default_actor != "user" else "user"
            features.append(
                Feature(
                    id=key,
                    feature=key,
                    actor=actor,  # type: ignore[arg-type]
                    target="telegram_user" if cap.needs_target_user else "",
                    trigger=Trigger(type="command", id=cmd),
                    permissions=list(cap.permissions),
                    action=Action(service=cap.service, method=cap.method),
                    messages=Messages(success=success, failure=failure),
                    success={"message": success},
                    failure={"message": failure},
                )
            )

        # Useful start buttons for common packs
        if "task_add" in selected:
            features.append(
                Feature(
                    id="task_add_cb",
                    feature="task_add",
                    trigger=Trigger(type="callback", id="task.add"),
                    action=Action(service="tasks", method="add_task"),
                    messages=Messages(prompt="أرسل عنوان المهمة", success="تمت إضافة المهمة", failure="فشل"),
                )
            )
            start_buttons.append(StartButton(label="إضافة مهمة", callback_id="task.add"))
        if "task_list" in selected:
            features.append(
                Feature(
                    id="task_list_cb",
                    feature="task_list",
                    trigger=Trigger(type="callback", id="task.list"),
                    action=Action(service="tasks", method="list_tasks"),
                )
            )
            start_buttons.append(StartButton(label="مهامي", callback_id="task.list"))
        if "ticket_open" in selected:
            features.append(
                Feature(
                    id="ticket_open_cb",
                    feature="ticket_open",
                    trigger=Trigger(type="callback", id="ticket.open"),
                    action=Action(service="tickets", method="open_ticket"),
                    messages=Messages(prompt="اكتب موضوع التذكرة", success="تم فتح التذكرة", failure="فشل"),
                )
            )
            start_buttons.append(StartButton(label="فتح تذكرة", callback_id="ticket.open"))
        if "ticket_my" in selected:
            features.append(
                Feature(
                    id="ticket_my_cb",
                    feature="ticket_my",
                    trigger=Trigger(type="callback", id="ticket.my"),
                    action=Action(service="tickets", method="my_tickets"),
                )
            )
            start_buttons.append(StartButton(label="تذاكري", callback_id="ticket.my"))
        if "note_add" in selected:
            features.append(
                Feature(
                    id="note_add_cb",
                    feature="note_add",
                    trigger=Trigger(type="callback", id="note.add"),
                    action=Action(service="notes", method="add_note"),
                    messages=Messages(prompt="أرسل الملاحظة", success="تمت الإضافة", failure="فشل"),
                )
            )
            start_buttons.append(StartButton(label="ملاحظة", callback_id="note.add"))

        return BotSpec(
            version="1.0",
            bot=BotMeta(
                name=self.bot_name,
                language=self.language,
                description=self.description or self.bot_name,
            ),
            actors=["user", "admin"],
            features=features,
            storage=StorageSpec(
                type="sqlite" if self.needs_sqlite() else "none",
                entities=[],
            ),
            start_buttons=start_buttons,
            hard_constraints=["zero-ai", "spec-builder"],
        )

    def to_dict(self) -> dict[str, Any]:
        return self.to_spec().to_dict()


# In-memory sessions (single-process builder bot)
_SESSIONS: dict[int, BuilderSession] = {}


def get_session(user_id: int) -> BuilderSession:
    if user_id not in _SESSIONS:
        _SESSIONS[user_id] = BuilderSession(user_id=user_id)
    return _SESSIONS[user_id]


def reset_session(user_id: int) -> BuilderSession:
    _SESSIONS[user_id] = BuilderSession(user_id=user_id)
    return _SESSIONS[user_id]


__all__ = [
    "BuilderSession",
    "DEFAULT_COMMANDS",
    "get_session",
    "reset_session",
]
