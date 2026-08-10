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
    "sec_tips": "sectips",
    "sec_password_tips": "passtips",
    "sec_dns_check": "dns",
    "sec_mx_check": "mx",
    "sec_tls_check": "tls",
    "sec_http_check": "httpstatus",
    "sec_headers_check": "headers",
    "sec_domain_overview": "domainscan",
    "faq_show": "faq",
    "broadcast_admin": "broadcast",
    "shop_catalog": "shop",
    "shop_add_item": "addproduct",
    "shop_order": "order",
    "shop_buy": "buy",
    "shop_orders": "orders",
    "shop_my_orders": "myorders",
    "plans": "plans",
    "subscribe": "subscribe",
    "my_sub": "mysub",
    "grant_sub": "grantsub",
    "revoke_sub": "revokesub",
    "sub_status": "substatus",
    "balance": "balance",
    "leaderboard": "leaderboard",
    "grant_points": "grantpoints",
    "debit_points": "debitpoints",
    "points_history": "pointshistory",
    "redeem_points": "redeem",
    "contests": "contests",
    "join_contest": "join",
    "my_entries": "myentries",
    "new_contest": "newcontest",
    "end_contest": "endcontest",
    "draw_winner": "draw",
    "contest_info": "contest",
    "lang": "lang",
    "language": "lang",
}

# Fill missing command aliases from capability keys
for _k in CAPABILITIES:
    DEFAULT_COMMANDS.setdefault(_k, _k.replace("_", "")[:32])

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
    "shop_buy": "تم إرسال فاتورة الدفع",
    "shop_add_item": "تم إضافة المنتج",
    "subscribe": "تم تفعيل الاشتراك",
    "grant_sub": "تم منح الاشتراك",
    "revoke_sub": "تم إلغاء الاشتراك",
    "grant_points": "تم منح النقاط",
    "join_contest": "تم تسجيل مشاركتك",
    "draw_winner": "تم سحب الفائز",
    "lang": "تم تغيير اللغة",
}

DEFAULT_SUCCESS_EN: dict[str, str] = {
    "shop_buy": "Payment invoice sent",
    "shop_add_item": "Product added",
    "subscribe": "Subscription activated",
    "grant_sub": "Subscription granted",
    "revoke_sub": "Subscription revoked",
    "grant_points": "Points granted",
    "join_contest": "Entry recorded",
    "draw_winner": "Winner drawn",
    "lang": "Language updated",
    "balance": "Your balance",
    "leaderboard": "Leaderboard",
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
        """Set bot name with smart extraction (avoids ____ path junk)."""
        import re as _re
        raw = (name or "").strip()
        try:
            from .arabic_intent_engine import extract_bot_name
            smart = extract_bot_name(raw)
            if smart:
                raw = smart
        except Exception:
            pass
        cleaned = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in raw)
        cleaned = _re.sub(r"_+", "_", cleaned).strip("_")
        if not cleaned or set(cleaned) <= {"_"} or len(cleaned) < 2:
            cleaned = "my_bot"
        self.bot_name = cleaned[:40]

    def set_description(self, text: str) -> None:
        self.description = (text or "").strip()[:200]

    def needs_sqlite(self) -> bool:
        for key in self.selected:
            cap = get_capability(key)
            if cap and cap.service in {
                "tasks", "notes", "welcome", "tickets", "security", "shop",
                "booking", "crm", "reminders", "community", "edu", "hr",
                "utils", "gate", "payments", "subscriptions", "points", "contests",
                "cart", "growth", "wallet", "forms", "events", "notify",
                "support", "jobs", "marketplace", "restaurant", "services",
                "analytics", "admin", "compliance", "integrations",
                "creator", "waitlist", "gamification", "pricing", "onboarding",
                "agency", "safety", "fitness", "realestate", "clinic",
                "auction", "delivery", "retention",
            }:
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

        # Commerce / engagement start buttons (end-user product packs)
        if "shop_catalog" in selected:
            start_buttons.append(StartButton(label="🛒 Shop", callback_id="shop.catalog"))
            features.append(
                Feature(
                    id="shop_catalog_cb",
                    feature="shop_catalog",
                    trigger=Trigger(type="callback", id="shop.catalog"),
                    action=Action(service="shop", method="catalog"),
                )
            )
        if "shop_buy" in selected:
            start_buttons.append(StartButton(label="💳 Buy", callback_id="shop.buy"))
        if "plans" in selected:
            start_buttons.append(StartButton(label="⭐ Plans", callback_id="sub.plans"))
            features.append(
                Feature(
                    id="plans_cb",
                    feature="plans",
                    trigger=Trigger(type="callback", id="sub.plans"),
                    action=Action(service="subscriptions", method="list_plans"),
                )
            )
        if "balance" in selected:
            start_buttons.append(StartButton(label="💎 Points", callback_id="points.balance"))
            features.append(
                Feature(
                    id="balance_cb",
                    feature="balance",
                    trigger=Trigger(type="callback", id="points.balance"),
                    action=Action(service="points", method="balance"),
                )
            )
        if "contests" in selected:
            start_buttons.append(StartButton(label="🏆 Contests", callback_id="contest.list"))
            features.append(
                Feature(
                    id="contests_cb",
                    feature="contests",
                    trigger=Trigger(type="callback", id="contest.list"),
                    action=Action(service="contests", method="list_open"),
                )
            )
        if "lang" in selected or "language" in selected:
            start_buttons.append(StartButton(label="🌐 Language", callback_id="i18n.lang"))

        entity_names: list[str] = []
        if any(k.startswith("shop_") or k.startswith("cart_") or k.startswith("product_") for k in selected):
            entity_names.extend(["Product", "Order", "Payment", "Coupon", "CartItem"])
        if any(k in selected for k in ("plans", "subscribe", "my_sub", "grant_sub", "revoke_sub", "sub_status")):
            entity_names.extend(["Plan", "Subscription"])
        if any(k in selected for k in ("balance", "leaderboard", "grant_points", "debit_points", "points_history", "redeem_points")):
            entity_names.extend(["PointLedger", "UserBalance"])
        if any(k in selected for k in ("contests", "join_contest", "my_entries", "new_contest", "end_contest", "draw_winner")):
            entity_names.extend(["Contest", "Entry"])
        if any(k.startswith("referral_") or k in selected and k in ("daily_checkin", "streak_status", "achievement_list") for k in selected):
            entity_names.extend(["Referral", "Checkin"])
        if any(k.startswith("wallet_") for k in selected):
            entity_names.extend(["Wallet", "WalletTxn"])
        if any(k.startswith("content_") or k in ("tip_creator", "membership_gate") for k in selected):
            entity_names.extend(["ContentItem", "Unlock", "Tip"])
        if any(k.startswith("lead_") or k.startswith("deal_") or k == "pipeline_board" for k in selected):
            entity_names.extend(["Lead", "Deal"])
        if any(k.startswith("ticket_") or k.startswith("kb_") for k in selected):
            entity_names.extend(["Ticket", "KbArticle"])
        if any(k.startswith("event_") for k in selected):
            entity_names.extend(["Event", "Rsvp"])
        if any(k.startswith("listing_") for k in selected):
            entity_names.extend(["Listing"])
        if any(k.startswith("job_") for k in selected):
            entity_names.extend(["Job", "Application"])
        if any(k.startswith("menu_") or k in ("order_status", "table_book") for k in selected):
            entity_names.extend(["MenuItem", "FoodOrder", "TableBooking"])
        if any(k.startswith("gym_") for k in selected):
            entity_names.extend(["GymSession", "GymMembership"])
        if any(k.startswith("property_") for k in selected):
            entity_names.extend(["Property", "PropertyInquiry"])
        if any(k.startswith("clinic_") for k in selected):
            entity_names.extend(["ClinicSlot", "Appointment"])
        if any(k.startswith("auction_") for k in selected):
            entity_names.extend(["Auction", "Bid"])
        if any(k.startswith("delivery_") for k in selected):
            entity_names.extend(["Shipment"])

        if any(k.startswith("waitlist_") for k in selected):
            entity_names.extend(["WaitlistEntry"])
        # dedupe preserve order
        seen: set[str] = set()
        entities_out: list[str] = []
        for n in entity_names:
            if n not in seen:
                seen.add(n)
                entities_out.append(n)

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
                entities=entities_out,
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
