"""Capability Registry — executable features for zero-AI generation.

Scale model: 20k+ product capabilities, each mapped to a deterministic service/method.
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
    # Domain / surface checks — stdlib only (no offensive tooling)
    _c("sec_dns_check", "security", "dns_check", "فحص سجلات DNS", "DNS A/AAAA lookup", cat="security"),
    _c("sec_mx_check", "security", "mx_check", "فحص سجلات MX", "MX-oriented host lookup", cat="security"),
    _c("sec_tls_check", "security", "tls_check", "فحص شهادة TLS/SSL", "TLS certificate overview", cat="security"),
    _c("sec_http_check", "security", "http_check", "فحص حالة HTTP", "HTTP status probe", cat="security"),
    _c("sec_headers_check", "security", "headers_check", "رؤوس أمان HTTP", "Security headers probe", cat="security"),
    _c("sec_domain_overview", "security", "domain_overview", "نظرة عامة على النطاق", "Domain security overview", cat="security"),
    _c("sec_password_tips", "security", "password_tips", "نصائح كلمات المرور", "Password hygiene tips", cat="security"),
)

# ── shop / payments (end-user commerce) ───────────────────────────────
_add(
    _c("shop_catalog", "shop", "catalog", "عرض قائمة منتجات", "Product catalog", cat="shop"),
    _c("shop_add_item", "shop", "add_item", "إضافة منتج (مشرف)", "Add product", "admin", cat="shop"),
    _c("shop_order", "shop", "place_order", "طلب منتج (بدون فاتورة)", "Place order", cat="shop"),
    _c("shop_buy", "shop", "send_invoice", "شراء بفاتورة تيليجرام", "Buy via Telegram invoice", cat="shop"),
    _c("shop_orders", "shop", "list_orders", "كل الطلبات", "List orders", "admin", cat="shop"),
    _c("shop_my_orders", "shop", "my_orders", "طلباتي", "My orders", cat="shop"),
    _c("payment_precheckout", "payments", "pre_checkout", "التحقق قبل الدفع", "Pre-checkout validation", cat="payments"),
    _c("payment_success", "payments", "successful_payment", "إتمام الدفع", "Successful payment handler", cat="payments"),
)

# ── subscriptions (end-user plans) ────────────────────────────────────
_add(
    _c("plans", "subscriptions", "list_plans", "عرض خطط الاشتراك", "List subscription plans", cat="subscriptions"),
    _c("subscribe", "subscriptions", "subscribe", "الاشتراك في خطة", "Subscribe to a plan", cat="subscriptions"),
    _c("my_sub", "subscriptions", "my_subscription", "اشتراكي الحالي", "My subscription", cat="subscriptions"),
    _c("grant_sub", "subscriptions", "grant", "منح اشتراك (مشرف)", "Grant subscription", "admin", cat="subscriptions"),
    _c("revoke_sub", "subscriptions", "revoke", "إلغاء اشتراك (مشرف)", "Revoke subscription", "admin", cat="subscriptions"),
    _c("sub_status", "subscriptions", "status", "حالة الاشتراك", "Subscription status", cat="subscriptions"),
)

# ── points / loyalty ──────────────────────────────────────────────────
_add(
    _c("balance", "points", "balance", "رصيدي من النقاط", "My points balance", cat="points"),
    _c("leaderboard", "points", "leaderboard", "لوحة المتصدرين", "Leaderboard", cat="points"),
    _c("grant_points", "points", "grant", "منح نقاط (مشرف)", "Grant points", "admin", cat="points"),
    _c("debit_points", "points", "debit", "خصم نقاط (مشرف)", "Debit points", "admin", cat="points"),
    _c("points_history", "points", "history", "سجل نقاطي", "My points history", cat="points"),
    _c("redeem_points", "points", "redeem", "استبدال نقاط", "Redeem points", cat="points"),
)

# ── contests / giveaways ──────────────────────────────────────────────
_add(
    _c("contests", "contests", "list_open", "المسابقات المفتوحة", "Open contests", cat="contests"),
    _c("join_contest", "contests", "join", "الانضمام لمسابقة", "Join contest", cat="contests"),
    _c("my_entries", "contests", "my_entries", "مشاركاتي", "My entries", cat="contests"),
    _c("new_contest", "contests", "create", "إنشاء مسابقة (مشرف)", "Create contest", "admin", cat="contests"),
    _c("end_contest", "contests", "close", "إنهاء مسابقة (مشرف)", "End contest", "admin", cat="contests"),
    _c("draw_winner", "contests", "draw_winner", "سحب فائز (مشرف)", "Draw winner", "admin", cat="contests"),
    _c("contest_info", "contests", "info", "تفاصيل مسابقة", "Contest info", cat="contests"),
)

# ── i18n ──────────────────────────────────────────────────────────────
_add(
    _c("lang", "i18n", "set_language", "تغيير لغة الواجهة", "Change UI language", cat="i18n"),
)

# ── booking lite ──────────────────────────────────────────────────────
_add(
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
    _c("uuid_gen", "utils", "uuid_gen", "توليد معرف فريد", "Generate UUID", cat="utils"),
    _c("password_gen", "utils", "password_gen", "توليد كلمة مرور", "Generate password", cat="utils"),
    _c("qr_text", "utils", "qr_text", "نص لـ QR (رابط/وصف)", "QR payload text", cat="utils"),
)

# ── cart / catalog advanced (end-user commerce) ────────────────────────
_add(
    _c("cart_add", "cart", "add", "إضافة للسلة", "Add to cart", cat="cart"),
    _c("cart_view", "cart", "view", "عرض السلة", "View cart", cat="cart"),
    _c("cart_clear", "cart", "clear", "تفريغ السلة", "Clear cart", cat="cart"),
    _c("cart_checkout", "cart", "checkout", "إتمام الشراء من السلة", "Checkout cart", cat="cart"),
    _c("wishlist_add", "shop", "wishlist_add", "إضافة للمفضلة", "Add to wishlist", cat="shop"),
    _c("wishlist_view", "shop", "wishlist_view", "المفضلة", "View wishlist", cat="shop"),
    _c("product_search", "shop", "search", "بحث منتجات", "Search products", cat="shop"),
    _c("product_info", "shop", "product_info", "تفاصيل منتج", "Product details", cat="shop"),
    _c("stock_set", "shop", "stock_set", "تعديل المخزون (مشرف)", "Set stock", "admin", cat="shop"),
    _c("coupon_apply", "shop", "coupon_apply", "تطبيق كوبون", "Apply coupon", cat="shop"),
    _c("coupon_create", "shop", "coupon_create", "إنشاء كوبون (مشرف)", "Create coupon", "admin", cat="shop"),
    _c("review_add", "shop", "review_add", "تقييم منتج", "Add product review", cat="shop"),
    _c("review_list", "shop", "review_list", "عرض التقييمات", "List reviews", cat="shop"),
    _c("refund_request", "shop", "refund_request", "طلب استرجاع", "Request refund", cat="shop"),
    _c("refund_approve", "shop", "refund_approve", "قبول استرجاع (مشرف)", "Approve refund", "admin", cat="shop"),
    _c("digital_deliver", "shop", "digital_deliver", "تسليم منتج رقمي", "Deliver digital good", cat="shop"),
    _c("license_issue", "shop", "license_issue", "إصدار مفتاح ترخيص", "Issue license key", "admin", cat="shop"),
    _c("shipping_set", "shop", "shipping_set", "حفظ عنوان الشحن", "Set shipping address", cat="shop"),
)

# ── referrals / growth ────────────────────────────────────────────────
_add(
    _c("referral_code", "growth", "my_code", "كود الإحالة الخاص بي", "My referral code", cat="growth"),
    _c("referral_invite", "growth", "invite_link", "رابط دعوة", "Invite link", cat="growth"),
    _c("referral_stats", "growth", "stats", "إحصاء الإحالات", "Referral stats", cat="growth"),
    _c("referral_claim", "growth", "claim", "تفعيل كود إحالة", "Claim referral code", cat="growth"),
    _c("referral_rewards", "growth", "rewards_info", "مكافآت الإحالة", "Referral rewards info", cat="growth"),
    _c("daily_checkin", "growth", "daily_checkin", "تسجيل يومي + مكافأة", "Daily check-in reward", cat="growth"),
    _c("streak_status", "growth", "streak", "سلسلة الأيام", "Streak status", cat="growth"),
    _c("achievement_list", "growth", "achievements", "الإنجازات", "Achievements", cat="growth"),
)

# ── wallet / credits ──────────────────────────────────────────────────
_add(
    _c("wallet_balance", "wallet", "balance", "رصيد المحفظة", "Wallet balance", cat="wallet"),
    _c("wallet_topup", "wallet", "topup", "شحن المحفظة", "Top up wallet", cat="wallet"),
    _c("wallet_transfer", "wallet", "transfer", "تحويل رصيد", "Transfer credits", cat="wallet"),
    _c("wallet_history", "wallet", "history", "سجل المحفظة", "Wallet history", cat="wallet"),
)

# ── forms / surveys / events ──────────────────────────────────────────
_add(
    _c("form_start", "forms", "start", "بدء نموذج", "Start form", cat="forms"),
    _c("form_submit", "forms", "submit", "إرسال النموذج", "Submit form", cat="forms"),
    _c("form_list", "forms", "list_admin", "ردود النماذج (مشرف)", "Form responses", "admin", cat="forms"),
    _c("survey_vote", "forms", "survey_vote", "تصويت استبيان", "Survey vote", cat="forms"),
    _c("survey_results", "forms", "survey_results", "نتائج الاستبيان", "Survey results", cat="forms"),
    _c("event_list", "events", "list_events", "الفعاليات", "List events", cat="events"),
    _c("event_rsvp", "events", "rsvp", "تأكيد حضور", "RSVP event", cat="events"),
    _c("event_create", "events", "create", "إنشاء فعالية (مشرف)", "Create event", "admin", cat="events"),
    _c("event_attendees", "events", "attendees", "قائمة الحضور (مشرف)", "Event attendees", "admin", cat="events"),
)

# ── notifications / channels ──────────────────────────────────────────
_add(
    _c("notify_subscribe", "notify", "subscribe_topic", "الاشتراك في تنبيهات", "Subscribe to alerts", cat="notify"),
    _c("notify_unsubscribe", "notify", "unsubscribe_topic", "إلغاء تنبيهات", "Unsubscribe alerts", cat="notify"),
    _c("notify_topics", "notify", "list_topics", "مواضيع التنبيه", "Alert topics", cat="notify"),
    _c("broadcast_segment", "notify", "broadcast_segment", "إذاعة لشريحة (مشرف)", "Segment broadcast", "admin", cat="notify"),
    _c("schedule_post", "notify", "schedule_post", "جدولة منشور (مشرف)", "Schedule post", "admin", cat="notify"),
    _c("channel_link", "notify", "channel_link", "رابط القناة الرسمية", "Official channel link", cat="notify"),
)

# ── CRM / sales pipeline (extends existing lead_*) ────────────────────
_add(
    _c("lead_status", "crm", "set_status", "تحديث حالة عميل (مشرف)", "Set lead status", "admin", cat="crm"),
    _c("pipeline_board", "crm", "pipeline", "لوحة المبيعات (مشرف)", "Sales pipeline", "admin", cat="crm"),
    _c("deal_create", "crm", "deal_create", "إنشاء صفقة (مشرف)", "Create deal", "admin", cat="crm"),
    _c("customer_profile", "crm", "profile", "ملف العميل", "Customer profile", cat="crm"),
    _c("followup_set", "crm", "followup_set", "تذكير متابعة (مشرف)", "Set follow-up", "admin", cat="crm"),
)

# ── support advanced ──────────────────────────────────────────────────
_add(
    _c("ticket_priority", "tickets", "set_priority", "أولوية تذكرة", "Set ticket priority", "admin", cat="tickets"),
    _c("ticket_assign", "tickets", "assign", "تعيين تذكرة لمشرف", "Assign ticket", "admin", cat="tickets"),
    _c("ticket_sla", "tickets", "sla_info", "معلومات SLA", "SLA info", "admin", cat="tickets"),
    _c("kb_search", "support", "kb_search", "بحث قاعدة معرفة", "Knowledge base search", cat="support"),
    _c("kb_article", "support", "kb_article", "عرض مقالة", "View KB article", cat="support"),
    _c("kb_add", "support", "kb_add", "إضافة مقالة (مشرف)", "Add KB article", "admin", cat="support"),
    _c("csat_rate", "support", "csat", "تقييم جودة الدعم", "Rate support (CSAT)", cat="support"),
)

# ── community / social ────────────────────────────────────────────────
_add(
    _c("profile_set", "community", "profile_set", "تعديل الملف الشخصي", "Edit profile", cat="community"),
    _c("profile_view", "community", "profile_view", "عرض ملف", "View profile", cat="community"),
    _c("follow_user", "community", "follow", "متابعة مستخدم", "Follow user", cat="community"),
    _c("feed_view", "community", "feed", "الخلاصة", "Community feed", cat="community"),
    _c("post_create", "community", "post_create", "نشر في المجتمع", "Create post", cat="community"),
    _c("post_like", "community", "post_like", "إعجاب بمنشور", "Like post", cat="community"),
    _c("report_content", "community", "report_content", "الإبلاغ عن محتوى", "Report content", cat="community"),
    _c("mod_queue", "community", "mod_queue", "طابور الإشراف", "Moderation queue", "admin", cat="community"),
)

# ── education advanced ────────────────────────────────────────────────
_add(
    _c("lesson_list", "edu", "lesson_list", "قائمة الدروس", "Lesson list", cat="edu"),
    _c("lesson_open", "edu", "lesson_open", "فتح درس", "Open lesson", cat="edu"),
    _c("progress_view", "edu", "progress", "تقدمي في الدورة", "Course progress", cat="edu"),
    _c("certificate_issue", "edu", "certificate", "شهادة إتمام", "Completion certificate", cat="edu"),
    _c("homework_submit", "edu", "homework_submit", "تسليم واجب", "Submit homework", cat="edu"),
    _c("homework_review", "edu", "homework_review", "مراجعة واجب (مشرف)", "Review homework", "admin", cat="edu"),
    _c("quiz_score", "edu", "quiz_score", "نتيجة الاختبار", "Quiz score", cat="edu"),
)

# ── jobs / marketplace listings ───────────────────────────────────────
_add(
    _c("job_list", "jobs", "list", "قائمة الوظائف", "Job listings", cat="jobs"),
    _c("job_post", "jobs", "post", "نشر وظيفة (مشرف)", "Post job", "admin", cat="jobs"),
    _c("job_apply", "jobs", "apply", "التقديم على وظيفة", "Apply to job", cat="jobs"),
    _c("job_my_apps", "jobs", "my_applications", "طلباتي", "My applications", cat="jobs"),
    _c("listing_create", "marketplace", "create_listing", "إنشاء إعلان", "Create listing", cat="marketplace"),
    _c("listing_search", "marketplace", "search", "بحث إعلانات", "Search listings", cat="marketplace"),
    _c("listing_contact", "marketplace", "contact_seller", "تواصل مع البائع", "Contact seller", cat="marketplace"),
    _c("listing_mine", "marketplace", "my_listings", "إعلاناتي", "My listings", cat="marketplace"),
)

# ── restaurant / services ─────────────────────────────────────────────
_add(
    _c("menu_view", "restaurant", "menu", "قائمة الطعام", "View menu", cat="restaurant"),
    _c("menu_order", "restaurant", "place_order", "طلب من القائمة", "Order from menu", cat="restaurant"),
    _c("order_status", "restaurant", "order_status", "حالة الطلب", "Order status", cat="restaurant"),
    _c("table_book", "restaurant", "book_table", "حجز طاولة", "Book a table", cat="restaurant"),
    _c("service_quote", "services", "quote", "طلب عرض سعر", "Request quote", cat="services"),
    _c("service_catalog", "services", "catalog", "كتالوج الخدمات", "Service catalog", cat="services"),
)

# ── admin / analytics / compliance ────────────────────────────────────
_add(
    _c("analytics_overview", "analytics", "overview", "نظرة تحليلية (مشرف)", "Analytics overview", "admin", cat="analytics"),
    _c("analytics_users", "analytics", "users", "إحصاء المستخدمين (مشرف)", "User analytics", "admin", cat="analytics"),
    _c("analytics_revenue", "analytics", "revenue", "إيرادات (مشرف)", "Revenue analytics", "admin", cat="analytics"),
    _c("export_users", "analytics", "export_users", "تصدير مستخدمين (مشرف)", "Export users CSV", "admin", cat="analytics"),
    _c("admin_users", "admin", "list_users", "قائمة المستخدمين", "List users", "admin", cat="admin"),
    _c("admin_ban_bot", "admin", "ban_from_bot", "حظر من البوت", "Ban from bot", "admin", cat="admin"),
    _c("admin_unban_bot", "admin", "unban_from_bot", "فك حظر من البوت", "Unban from bot", "admin", cat="admin"),
    _c("admin_set_role", "admin", "set_role", "تعيين دور", "Set user role", "owner", cat="admin"),
    _c("maintenance_mode", "admin", "maintenance", "وضع الصيانة", "Maintenance mode", "owner", cat="admin"),
    _c("privacy_policy", "compliance", "privacy", "سياسة الخصوصية", "Privacy policy", cat="compliance"),
    _c("terms_of_service", "compliance", "terms", "شروط الاستخدام", "Terms of service", cat="compliance"),
    _c("data_export_me", "compliance", "export_me", "تصدير بياناتي", "Export my data", cat="compliance"),
    _c("data_delete_me", "compliance", "delete_me", "حذف حسابي/بياناتي", "Delete my data", cat="compliance"),
)

# ── automation / integrations ─────────────────────────────────────────
_add(
    _c("webhook_set", "integrations", "webhook_set", "تعيين Webhook (مشرف)", "Set outbound webhook", "admin", cat="integrations"),
    _c("webhook_test", "integrations", "webhook_test", "اختبار Webhook (مشرف)", "Test webhook", "admin", cat="integrations"),
    _c("api_token_issue", "integrations", "api_token_issue", "إصدار رمز API (مشرف)", "Issue API token", "admin", cat="integrations"),
    _c("rss_add", "integrations", "rss_add", "إضافة مصدر RSS (مشرف)", "Add RSS feed", "admin", cat="integrations"),
    _c("rss_list", "integrations", "rss_list", "مصادر RSS", "List RSS feeds", cat="integrations"),
)

# ── creator monetization ──────────────────────────────────────────────
_add(
    _c("content_list", "creator", "list_content", "المحتوى المتاح", "Available content", cat="creator"),
    _c("content_unlock", "creator", "unlock", "فتح محتوى مدفوع", "Unlock paid content", cat="creator"),
    _c("content_upload", "creator", "upload", "رفع محتوى (مشرف)", "Upload content", "admin", cat="creator"),
    _c("tip_creator", "creator", "tip", "إكرامية للمنشئ", "Tip the creator", cat="creator"),
    _c("membership_gate", "creator", "gate_check", "تحقق عضوية المحتوى", "Membership gate check", cat="creator"),
    _c("content_library", "creator", "library", "مكتبتي", "My unlocked library", cat="creator"),
)

# ── waitlist / launches ───────────────────────────────────────────────
_add(
    _c("waitlist_join", "waitlist", "join", "الانضمام لقائمة الانتظار", "Join waitlist", cat="waitlist"),
    _c("waitlist_status", "waitlist", "status", "حالة الانتظار", "Waitlist status", cat="waitlist"),
    _c("waitlist_invite", "waitlist", "invite_next", "دعوة التالي (مشرف)", "Invite next", "admin", cat="waitlist"),
    _c("waitlist_stats", "waitlist", "stats", "إحصاء الانتظار (مشرف)", "Waitlist stats", "admin", cat="waitlist"),
)

# ── gamification extras ───────────────────────────────────────────────
_add(
    _c("badge_list", "gamification", "badges", "شاراتي", "My badges", cat="gamification"),
    _c("badge_grant", "gamification", "grant_badge", "منح شارة (مشرف)", "Grant badge", "admin", cat="gamification"),
    _c("quest_list", "gamification", "quests", "المهام", "Quests", cat="gamification"),
    _c("quest_claim", "gamification", "claim_quest", "استلام مكافأة مهمة", "Claim quest reward", cat="gamification"),
)


# ── launch extras ─────────────────────────────────────────────────────
_add(
    _c("flash_sale_list", "shop", "flash_list", "عروض خاطفة", "Flash sales", cat="shop"),
    _c("gift_code_redeem", "shop", "redeem_gift", "استرداد كود هدية", "Redeem gift code", cat="shop"),
    _c("gift_code_create", "shop", "create_gift", "إنشاء كود هدية", "Create gift code", "admin", cat="shop"),
    _c("affiliate_payout", "growth", "payout_request", "طلب صرف إحالات", "Request affiliate payout", cat="growth"),
    _c("upsell_offer", "shop", "upsell", "عرض ترقية", "Upsell offer", cat="shop"),
    _c("downgrade_plan", "subscriptions", "downgrade", "تخفيض الخطة", "Downgrade plan", cat="subscriptions"),
    _c("pause_sub", "subscriptions", "pause", "إيقاف اشتراك مؤقت", "Pause subscription", cat="subscriptions"),
    _c("resume_sub", "subscriptions", "resume", "استئناف اشتراك", "Resume subscription", cat="subscriptions"),
    _c("contest_share", "contests", "share", "مشاركة المسابقة", "Share contest", cat="contests"),
    _c("points_transfer", "points", "transfer", "تحويل نقاط", "Transfer points", cat="points"),
)


# ── commerce polish ───────────────────────────────────────────────────
_add(
    _c("invoice_resend", "payments", "resend_invoice", "إعادة إرسال فاتورة", "Resend invoice", cat="payments"),
    _c("order_cancel", "shop", "cancel_order", "إلغاء طلب", "Cancel order", cat="shop"),
    _c("order_track", "shop", "track_order", "تتبع طلب", "Track order", cat="shop"),
    _c("stock_alert", "shop", "stock_alert", "تنبيه نفاد مخزون", "Low stock alert", "admin", cat="shop"),
    _c("plan_compare", "subscriptions", "compare_plans", "مقارنة الخطط", "Compare plans", cat="subscriptions"),
    _c("points_shop", "points", "points_shop", "متجر النقاط", "Points shop", cat="points"),
    _c("contest_rules", "contests", "rules", "قوانين المسابقة", "Contest rules", cat="contests"),
    _c("referral_leaderboard", "growth", "referral_board", "متصدري الإحالات", "Referral leaderboard", cat="growth"),
    _c("lang_auto", "i18n", "auto_detect", "لغة تلقائية", "Auto language", cat="i18n"),
    _c("onboarding_complete", "onboarding", "complete", "إنهاء التهيئة", "Complete onboarding", cat="onboarding"),
    _c("feature_flags", "admin", "feature_flags", "أعلام الميزات", "Feature flags", "owner", cat="admin"),
    _c("health_ping", "utils", "health_ping", "فحص صحة البوت", "Bot health ping", "admin", cat="utils"),
)


# ── smart UX ──────────────────────────────────────────────────────────
_add(
    _c("smart_help", "core", "smart_help", "مساعدة سياقية", "Contextual smart help", cat="core"),
    _c("quick_reply", "core", "quick_reply", "ردود سريعة", "Quick replies menu", cat="core"),
    _c("deep_link_start", "core", "deep_link", "بدء بروابط عميقة", "Deep-link start payload", cat="core"),
    _c("onboarding_smart", "onboarding", "smart_flow", "تهيئة ذكية", "Smart onboarding flow", cat="onboarding"),
    _c("recommend_products", "shop", "recommend", "توصية منتجات", "Recommend products", cat="shop"),
    _c("recommend_plan", "subscriptions", "recommend_plan", "توصية خطة", "Recommend plan", cat="subscriptions"),
    _c("auto_leaderboard", "points", "auto_board", "متصدرين تلقائي", "Auto-post leaderboard", "admin", cat="points"),
    _c("smart_broadcast", "notify", "smart_broadcast", "إذاعة ذكية", "Smart segmented broadcast", "admin", cat="notify"),
    _c("churn_risk", "analytics", "churn_risk", "خطر إلغاء الاشتراك", "Churn risk list", "admin", cat="analytics"),
    _c("cohort_stats", "analytics", "cohorts", "إحصاء مجموعات", "Cohort stats", "admin", cat="analytics"),
)


# ── vertical: fitness / gym ───────────────────────────────────────────
_add(
    _c("gym_book", "fitness", "book_session", "حجز حصة", "Book gym session", cat="fitness"),
    _c("gym_schedule", "fitness", "schedule", "جدول الحصص", "Class schedule", cat="fitness"),
    _c("gym_checkin", "fitness", "gym_checkin", "حضور الصالة", "Gym check-in", cat="fitness"),
    _c("gym_membership", "fitness", "membership", "عضوية النادي", "Gym membership", cat="fitness"),
)

# ── vertical: real estate ─────────────────────────────────────────────
_add(
    _c("property_list", "realestate", "list", "قائمة العقارات", "Property listings", cat="realestate"),
    _c("property_search", "realestate", "search", "بحث عقارات", "Search properties", cat="realestate"),
    _c("property_inquiry", "realestate", "inquiry", "استفسار عن عقار", "Property inquiry", cat="realestate"),
    _c("property_add", "realestate", "add", "إضافة عقار", "Add property", "admin", cat="realestate"),
)

# ── vertical: clinic / appointments ───────────────────────────────────
_add(
    _c("clinic_book", "clinic", "book", "حجز موعد طبي", "Book clinic appointment", cat="clinic"),
    _c("clinic_slots", "clinic", "slots", "المواعيد المتاحة", "Available slots", cat="clinic"),
    _c("clinic_cancel", "clinic", "cancel", "إلغاء موعد", "Cancel appointment", cat="clinic"),
    _c("clinic_my", "clinic", "my_appointments", "مواعيدي", "My appointments", cat="clinic"),
)

# ── vertical: delivery / logistics ────────────────────────────────────
_add(
    _c("delivery_track", "delivery", "track", "تتبع شحنة", "Track delivery", cat="delivery"),
    _c("delivery_create", "delivery", "create", "إنشاء شحنة", "Create shipment", "admin", cat="delivery"),
    _c("delivery_status", "delivery", "status", "حالة الشحن", "Shipment status", cat="delivery"),
)

# ── vertical: auction ─────────────────────────────────────────────────
_add(
    _c("auction_list", "auction", "list", "المزادات", "List auctions", cat="auction"),
    _c("auction_bid", "auction", "bid", "مزايدة", "Place bid", cat="auction"),
    _c("auction_create", "auction", "create", "إنشاء مزاد", "Create auction", "admin", cat="auction"),
    _c("auction_my_bids", "auction", "my_bids", "مزايداتي", "My bids", cat="auction"),
)

# ── retention / lifecycle ─────────────────────────────────────────────
_add(
    _c("winback_offer", "retention", "winback", "عرض استرجاع", "Win-back offer", cat="retention"),
    _c("inactive_nudge", "retention", "nudge", "تذكير خمول", "Inactive user nudge", "admin", cat="retention"),
    _c("loyalty_tier", "retention", "tier", "مستوى الولاء", "Loyalty tier", cat="retention"),
    _c("anniversary_bonus", "retention", "anniversary", "مكافأة ذكرى", "Anniversary bonus", cat="retention"),
)

# ── admin ops polish ──────────────────────────────────────────────────
_add(
    _c("admin_dashboard", "admin", "dashboard", "لوحة المشرف", "Admin dashboard", "admin", cat="admin"),
    _c("admin_search_user", "admin", "search_user", "بحث مستخدم", "Search user", "admin", cat="admin"),
    _c("admin_notes", "admin", "user_notes", "ملاحظات على مستخدم", "Admin user notes", "admin", cat="admin"),
    _c("force_logout", "admin", "force_logout", "إنهاء جلسات", "Force logout sessions", "owner", cat="admin"),
)


# ── growth commerce intelligence ──────────────────────────────────────
_add(
    _c("abandoned_cart", "cart", "abandoned", "سلات متروكة", "Abandoned carts", "admin", cat="cart"),
    _c("cart_recover", "cart", "recover", "استعادة سلة", "Recover cart", cat="cart"),
    _c("price_drop_alert", "shop", "price_drop", "تنبيه انخفاض سعر", "Price drop alert", cat="shop"),
    _c("back_in_stock", "shop", "back_in_stock", "تنبيه توفر", "Back in stock alert", cat="shop"),
    _c("bundle_list", "shop", "bundles", "باقات مجمعة", "Product bundles", cat="shop"),
    _c("bundle_buy", "shop", "buy_bundle", "شراء باقة", "Buy bundle", cat="shop"),
    _c("trial_start", "subscriptions", "start_trial", "بدء تجربة", "Start trial", cat="subscriptions"),
    _c("trial_status", "subscriptions", "trial_status", "حالة التجربة", "Trial status", cat="subscriptions"),
    _c("renew_sub", "subscriptions", "renew", "تجديد اشتراك", "Renew subscription", cat="subscriptions"),
    _c("gift_sub", "subscriptions", "gift", "إهداء اشتراك", "Gift subscription", cat="subscriptions"),
    _c("points_boost", "points", "boost", "مضاعفة نقاط", "Points boost event", "admin", cat="points"),
    _c("streak_freeze", "growth", "freeze_streak", "تجميد السلسلة", "Freeze streak", cat="growth"),
    _c("level_status", "gamification", "level", "مستواي", "My level", cat="gamification"),
    _c("level_leaderboard", "gamification", "level_board", "متصدري المستويات", "Level leaderboard", cat="gamification"),
    _c("ab_test_info", "growth", "ab_info", "معلومة تجربة A/B", "A/B test info", "admin", cat="growth"),
    _c("smart_segment", "crm", "smart_segment", "شريحة ذكية", "Smart segment", "admin", cat="crm"),
    _c("ltv_top", "analytics", "ltv_top", "أعلى قيمة عملاء", "Top LTV customers", "admin", cat="analytics"),
    _c("revenue_today", "analytics", "revenue_today", "إيراد اليوم", "Revenue today", "admin", cat="analytics"),
    _c("locale_pack", "i18n", "locale_pack", "حزمة ترجمة", "Locale pack info", cat="i18n"),
    _c("currency_convert", "pricing", "convert", "تحويل عملة", "Currency convert", cat="pricing"),
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

# Mass scale expansion toward launch (10k capabilities)

_add(
    _c("payment_receipt", "payments", "receipt", "إيصال دفع", "Payment receipt", cat="payments"),
    _c("payment_history", "payments", "history", "سجل المدفوعات", "Payment history", cat="payments"),
    _c("invoice_preview", "payments", "preview", "معاينة فاتورة", "Invoice preview", cat="payments"),
)

from . import registry_scale as _registry_scale  # noqa: E402,F401

