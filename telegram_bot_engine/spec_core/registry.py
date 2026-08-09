"""Capability Registry — executable features for zero-AI generation.

Scale model: many product capabilities, each mapped to a deterministic service/method.
Offensive cyber / exploit tooling is intentionally excluded.
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


def _c(key, service, method, ar, en, actor="user", perms=(), target=False, cat="general"):
    return Capability(
        key=key, service=service, method=method,
        description_ar=ar, description_en=en,
        default_actor=actor, permissions=tuple(perms),
        needs_target_user=target, category=cat,
    )


CAPABILITIES: dict[str, Capability] = {}


def _add(*caps: Capability) -> None:
    for c in caps:
        CAPABILITIES[c.key] = c


# ── core ──────────────────────────────────────────────────────────────
_add(
    _c("start", "core", "start", "ترحيب وأزرار رئيسية", "Welcome + main buttons", cat="core"),
    _c("help", "core", "help", "مساعدة الأوامر", "Help", cat="core"),
    _c("about", "core", "about", "عن البوت", "About", cat="core"),
    _c("ping", "core", "ping", "فحص التشغيل", "Ping", cat="core"),
    _c("my_id", "core", "my_id", "معرف المستخدم والمحادثة", "User/chat ids", cat="core"),
    _c("settings", "core", "settings", "إعدادات المستخدم", "User settings", cat="core"),
    _c("language", "core", "language", "تغيير اللغة", "Change language", cat="core"),
    _c("cancel", "core", "cancel", "إلغاء العملية الحالية", "Cancel flow", cat="core"),
)

# ── content / community ───────────────────────────────────────────────
_add(
    _c("rules", "content", "rules", "قوانين المجموعة", "Rules", cat="content"),
    _c("faq_show", "content", "faq", "أسئلة شائعة", "FAQ", cat="content"),
    _c("announce", "content", "announce", "إعلان مشرف", "Announce", actor="admin", cat="content"),
    _c("broadcast_admin", "content", "announce", "إذاعة مشرف", "Broadcast", actor="admin", cat="content"),
    _c("news", "content", "news", "آخر الأخبار", "News feed", cat="content"),
    _c("links", "content", "links", "روابط مهمة", "Important links", cat="content"),
    _c("contact_admin", "content", "contact", "تواصل مع الإدارة", "Contact admins", cat="content"),
    _c("feedback", "community", "feedback", "إرسال ملاحظة/تقييم", "Send feedback", cat="community"),
    _c("suggest", "community", "suggest", "اقتراح ميزة", "Suggest feature", cat="community"),
    _c("poll_create", "community", "poll_create", "إنشاء تصويت بسيط", "Create simple poll", actor="admin", cat="community"),
    _c("report_user", "community", "report_user", "الإبلاغ عن مستخدم", "Report a user", cat="community"),
)

# ── moderation ────────────────────────────────────────────────────────
_add(
    _c("user_ban", "moderation", "ban_user", "حظر مستخدم", "Ban user", "admin", ("ban_users",), True, "moderation"),
    _c("user_unban", "moderation", "unban_user", "فك حظر", "Unban", "admin", ("ban_users",), True, "moderation"),
    _c("user_mute", "moderation", "mute_user", "كتم", "Mute", "admin", ("restrict_members",), True, "moderation"),
    _c("user_unmute", "moderation", "unmute_user", "فك كتم", "Unmute", "admin", ("restrict_members",), True, "moderation"),
    _c("user_kick", "moderation", "kick_user", "طرد", "Kick", "admin", ("ban_users",), True, "moderation"),
    _c("user_warn", "moderation", "warn_user", "تحذير", "Warn", "admin", ("ban_users",), True, "moderation"),
    _c("user_promote", "moderation", "promote_user", "ترقية مشرف", "Promote", "owner", ("promote_members",), True, "moderation"),
    _c("user_demote", "moderation", "demote_user", "إلغاء إشراف", "Demote", "owner", ("promote_members",), True, "moderation"),
    _c("pin_message", "moderation", "pin_message", "تثبيت رسالة", "Pin message", "admin", ("pin_messages",), False, "moderation"),
    _c("delete_message", "moderation", "delete_message", "حذف رسالة", "Delete message", "admin", ("delete_messages",), False, "moderation"),
    _c("purge", "moderation", "purge", "تنظيف رسائل (بالرد)", "Purge from reply", "admin", ("delete_messages",), False, "moderation"),
    _c("lock_chat", "moderation", "lock_chat", "قفل الدردشة للرسائل", "Lock chat", "admin", ("restrict_members",), False, "moderation"),
    _c("unlock_chat", "moderation", "unlock_chat", "فتح الدردشة", "Unlock chat", "admin", ("restrict_members",), False, "moderation"),
    _c("slowmode_info", "moderation", "slowmode_info", "عرض وضع التباطؤ", "Slow mode info", "admin", (), False, "moderation"),
    _c("user_info", "moderation", "user_info", "معلومات عضو", "Member info", "admin", (), True, "moderation"),
)

# ── welcome / gate ────────────────────────────────────────────────────
_add(
    _c("welcome_set", "welcome", "set_message", "تعيين رسالة ترحيب", "Set welcome", "admin", cat="welcome"),
    _c("welcome_toggle", "welcome", "toggle", "تفعيل/إيقاف الترحيب", "Toggle welcome", "admin", cat="welcome"),
    _c("welcome_show", "welcome", "show", "عرض إعداد الترحيب", "Show welcome", "admin", cat="welcome"),
    _c("welcome_test", "welcome", "test", "تجربة الترحيب", "Test welcome", "admin", cat="welcome"),
    _c("goodbye_set", "welcome", "set_goodbye", "تعيين رسالة وداع", "Set goodbye", "admin", cat="welcome"),
    _c("verify_start", "gate", "verify_start", "بدء تحقق بسيط للعضو", "Simple member verify", cat="gate"),
    _c("verify_ok", "gate", "verify_ok", "تأكيد التحقق", "Confirm verify", cat="gate"),
    _c("force_subscribe_info", "gate", "force_sub_info", "شرح الاشتراك الإجباري", "Force-subscribe info", "admin", cat="gate"),
)

# ── tasks / notes / reminders ─────────────────────────────────────────
_add(
    _c("task_add", "tasks", "add_task", "إضافة مهمة", "Add task", cat="tasks"),
    _c("task_list", "tasks", "list_tasks", "عرض المهام", "List tasks", cat="tasks"),
    _c("task_done", "tasks", "done_task", "إكمال مهمة", "Complete task", cat="tasks"),
    _c("task_delete", "tasks", "delete_task", "حذف مهمة", "Delete task", cat="tasks"),
    _c("task_clear", "tasks", "clear_tasks", "مسح المكتمل", "Clear done tasks", cat="tasks"),
    _c("note_add", "notes", "add_note", "إضافة ملاحظة", "Add note", cat="notes"),
    _c("note_list", "notes", "list_notes", "عرض الملاحظات", "List notes", cat="notes"),
    _c("note_delete", "notes", "delete_note", "حذف ملاحظة", "Delete note", cat="notes"),
    _c("remind_set", "reminders", "set_reminder", "تذكير لاحق (نص)", "Set text reminder", cat="reminders"),
    _c("remind_list", "reminders", "list_reminders", "قائمة التذكيرات", "List reminders", cat="reminders"),
    _c("remind_clear", "reminders", "clear_reminders", "مسح التذكيرات", "Clear reminders", cat="reminders"),
)

# ── tickets / CRM lite ────────────────────────────────────────────────
_add(
    _c("ticket_open", "tickets", "open_ticket", "فتح تذكرة", "Open ticket", cat="tickets"),
    _c("ticket_close", "tickets", "close_ticket", "إغلاق تذكرة", "Close ticket", cat="tickets"),
    _c("ticket_list", "tickets", "list_tickets", "كل التذاكر المفتوحة", "List tickets", cat="tickets"),
    _c("ticket_my", "tickets", "my_tickets", "تذاكري", "My tickets", cat="tickets"),
    _c("ticket_reply", "tickets", "reply_ticket", "رد على تذكرة", "Reply ticket", "admin", cat="tickets"),
    _c("ticket_status", "tickets", "ticket_status", "حالة تذكرة", "Ticket status", cat="tickets"),
    _c("lead_capture", "crm", "lead_capture", "تسجيل اهتمام/عميل محتمل", "Capture lead", cat="crm"),
    _c("lead_list", "crm", "lead_list", "عرض العملاء المحتملين", "List leads", "admin", cat="crm"),
)

# ── security defensive ────────────────────────────────────────────────
_add(
    _c("sec_report_phish", "security", "report_phish", "إبلاغ تصيّد", "Report phishing", cat="security"),
    _c("sec_report_incident", "security", "report_incident", "بلاغ حادث أمني", "Security incident", cat="security"),
    _c("sec_checklist", "security", "checklist", "توعية أمنية", "Security checklist", cat="security"),
    _c("sec_list_reports", "security", "list_reports", "بلاغات أمنية", "List sec reports", "admin", cat="security"),
    _c("sec_close_report", "security", "close_report", "إغلاق بلاغ أمني", "Close sec report", "admin", cat="security"),
    _c("sec_tips", "security", "tips", "نصائح أمان سريعة", "Quick security tips", cat="security"),
)

# ── shop / booking lite ───────────────────────────────────────────────
_add(
    _c("shop_catalog", "shop", "catalog", "عرض قائمة منتجات", "Product catalog", cat="shop"),
    _c("shop_add_item", "shop", "add_item", "إضافة منتج (مشرف)", "Add product", "admin", cat="shop"),
    _c("shop_order", "shop", "place_order", "طلب منتج", "Place order", cat="shop"),
    _c("shop_orders", "shop", "list_orders", "طلبات المتجر", "List orders", "admin", cat="shop"),
    _c("book_slot", "booking", "book_slot", "حجز موعد", "Book slot", cat="booking"),
    _c("book_list", "booking", "list_bookings", "حجوزاتي", "My bookings", cat="booking"),
    _c("book_cancel", "booking", "cancel_booking", "إلغاء حجز", "Cancel booking", cat="booking"),
    _c("book_admin_list", "booking", "admin_list", "كل الحجوزات", "All bookings", "admin", cat="booking"),
)

# ── education / hr lite ───────────────────────────────────────────────
_add(
    _c("course_list", "edu", "course_list", "قائمة الدورات", "Course list", cat="edu"),
    _c("course_enroll", "edu", "enroll", "تسجيل في دورة", "Enroll course", cat="edu"),
    _c("quiz_start", "edu", "quiz_start", "بدء اختبار قصير", "Start quiz", cat="edu"),
    _c("hr_leave_request", "hr", "leave_request", "طلب إجازة", "Leave request", cat="hr"),
    _c("hr_leave_list", "hr", "leave_list", "طلبات الإجازة", "Leave list", "admin", cat="hr"),
    _c("hr_checkin", "hr", "checkin", "تسجيل حضور", "Check-in", cat="hr"),
)

# ── utilities ─────────────────────────────────────────────────────────
_add(
    _c("calc", "utils", "calc", "حاسبة بسيطة", "Simple calculator", cat="utils"),
    _c("time_now", "utils", "time_now", "الوقت الحالي", "Current time", cat="utils"),
    _c("echo", "utils", "echo", "إعادة النص", "Echo text", cat="utils"),
    _c("random_pick", "utils", "random_pick", "اختيار عشوائي من قائمة", "Random pick", cat="utils"),
    _c("short_note", "utils", "short_note", "ملاحظة سريعة عامة", "Quick public note", cat="utils"),
    _c("stats_basic", "utils", "stats_basic", "إحصاء أساسي للبوت", "Basic bot stats", "admin", cat="utils"),
)


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
