"""Mass capability expansion toward launch scale (10k targets).

Generates structured, deterministic capability keys from vertical × action
templates. Shared service/method patterns keep zero-AI codegen stable.
"""
from __future__ import annotations

from .registry import CAPABILITIES, Capability, _add, _c

# ── shared action vocabularies ──────────────────────────────────────────
CRUD = (
    ("list", "قائمة", "List"),
    ("view", "عرض", "View"),
    ("create", "إنشاء", "Create"),
    ("update", "تحديث", "Update"),
    ("delete", "حذف", "Delete"),
    ("search", "بحث", "Search"),
    ("filter", "تصفية", "Filter"),
    ("export", "تصدير", "Export"),
    ("import_data", "استيراد", "Import"),
    ("archive", "أرشفة", "Archive"),
    ("restore", "استعادة", "Restore"),
    ("duplicate", "نسخ", "Duplicate"),
    ("share", "مشاركة", "Share"),
    ("pin", "تثبيت", "Pin"),
    ("unpin", "إلغاء تثبيت", "Unpin"),
    ("favorite", "مفضلة", "Favorite"),
    ("unfavorite", "إزالة من المفضلة", "Unfavorite"),
    ("stats", "إحصاء", "Stats"),
    ("history", "سجل", "History"),
    ("audit", "تدقيق", "Audit"),
)

WORKFLOW = (
    ("submit", "إرسال", "Submit"),
    ("approve", "قبول", "Approve"),
    ("reject", "رفض", "Reject"),
    ("assign", "تعيين", "Assign"),
    ("claim", "استلام", "Claim"),
    ("release", "تحرير", "Release"),
    ("escalate", "تصعيد", "Escalate"),
    ("close", "إغلاق", "Close"),
    ("reopen", "إعادة فتح", "Reopen"),
    ("schedule", "جدولة", "Schedule"),
    ("reschedule", "إعادة جدولة", "Reschedule"),
    ("cancel", "إلغاء", "Cancel"),
    ("postpone", "تأجيل", "Postpone"),
    ("remind", "تذكير", "Remind"),
    ("notify", "إشعار", "Notify"),
)

COMMERCE = (
    ("buy", "شراء", "Buy"),
    ("sell", "بيع", "Sell"),
    ("quote", "عرض سعر", "Quote"),
    ("invoice", "فاتورة", "Invoice"),
    ("refund", "استرجاع", "Refund"),
    ("discount", "خصم", "Discount"),
    ("coupon", "كوبون", "Coupon"),
    ("checkout", "إتمام شراء", "Checkout"),
    ("cart_add", "إضافة سلة", "Cart add"),
    ("cart_remove", "حذف من السلة", "Cart remove"),
    ("wishlist", "مفضلة شراء", "Wishlist"),
    ("review", "تقييم", "Review"),
    ("rate", "نجوم", "Rate"),
    ("ship", "شحن", "Ship"),
    ("track", "تتبع", "Track"),
    ("fulfill", "تنفيذ طلب", "Fulfill"),
    ("stock", "مخزون", "Stock"),
    ("price", "تسعير", "Price"),
    ("tax", "ضريبة", "Tax"),
    ("currency", "عملة", "Currency"),
)

SOCIAL = (
    ("follow", "متابعة", "Follow"),
    ("unfollow", "إلغاء متابعة", "Unfollow"),
    ("like", "إعجاب", "Like"),
    ("unlike", "إلغاء إعجاب", "Unlike"),
    ("comment", "تعليق", "Comment"),
    ("reply", "رد", "Reply"),
    ("repost", "إعادة نشر", "Repost"),
    ("report", "بلاغ", "Report"),
    ("block", "حظر", "Block"),
    ("unblock", "فك حظر", "Unblock"),
    ("mute", "كتم", "Mute"),
    ("unmute", "إلغاء كتم", "Unmute"),
    ("invite", "دعوة", "Invite"),
    ("join", "انضمام", "Join"),
    ("leave", "مغادرة", "Leave"),
)

GAMING = (
    ("play", "لعب", "Play"),
    ("pause", "إيقاف", "Pause"),
    ("resume", "استئناف", "Resume"),
    ("score", "نتيجة", "Score"),
    ("rank", "ترتيب", "Rank"),
    ("reward", "مكافأة", "Reward"),
    ("quest", "مهمة", "Quest"),
    ("badge", "شارة", "Badge"),
    ("level_up", "ترقية مستوى", "Level up"),
    ("streak", "سلسلة", "Streak"),
    ("checkin", "تسجيل يومي", "Check-in"),
    ("leaderboard", "متصدرين", "Leaderboard"),
)

ADMIN = (
    ("config", "إعداد", "Config"),
    ("toggle", "تفعيل/إيقاف", "Toggle"),
    ("broadcast", "إذاعة", "Broadcast"),
    ("ban", "حظر", "Ban"),
    ("unban", "فك حظر", "Unban"),
    ("role_set", "تعيين دور", "Set role"),
    ("audit_log", "سجل تدقيق", "Audit log"),
    ("metrics", "مقاييس", "Metrics"),
    ("health", "صحة النظام", "Health"),
    ("backup", "نسخ احتياطي", "Backup"),
    ("restore_backup", "استعادة نسخة", "Restore backup"),
    ("feature_flag", "علم ميزة", "Feature flag"),
)

# Vertical domains: (prefix, service, category, ar_name, en_name)
VERTICALS: list[tuple[str, str, str, str, str]] = [
    ("inv", "inventory", "inventory", "مخزون", "Inventory"),
    ("sku", "catalog", "catalog", "صنف", "SKU"),
    ("ord", "orders", "orders", "طلب", "Order"),
    ("pay", "billing", "billing", "دفعة", "Payment"),
    ("sub", "subs", "subs", "اشتراك", "Subscription"),
    ("mem", "members", "members", "عضو", "Member"),
    ("tkt", "tickets2", "tickets2", "تذكرة", "Ticket"),
    ("lead", "leads", "leads", "عميل", "Lead"),
    ("deal", "deals", "deals", "صفقة", "Deal"),
    ("camp", "campaigns", "campaigns", "حملة", "Campaign"),
    ("coup", "coupons", "coupons", "كوبون", "Coupon"),
    ("aff", "affiliate", "affiliate", "شريك", "Affiliate"),
    ("ref", "refs", "refs", "إحالة", "Referral"),
    ("pts", "loyalty", "loyalty", "نقاط", "Points"),
    ("wal", "wallets", "wallets", "محفظة", "Wallet"),
    ("gift", "gifts", "gifts", "هدية", "Gift"),
    ("evt", "events2", "events2", "فعالية", "Event"),
    ("rsvp", "rsvps", "rsvps", "حضور", "RSVP"),
    ("crs", "courses", "courses", "دورة", "Course"),
    ("lsn", "lessons", "lessons", "درس", "Lesson"),
    ("quiz", "quizzes", "quizzes", "اختبار", "Quiz"),
    ("job", "jobs2", "jobs2", "وظيفة", "Job"),
    ("app", "apps", "apps", "طلب توظيف", "Application"),
    ("prop", "props", "props", "عقار", "Property"),
    ("apt", "apts", "apts", "موعد", "Appointment"),
    ("gym", "gyms", "gyms", "حصة", "Session"),
    ("menu", "menus", "menus", "قائمة", "Menu"),
    ("dish", "dishes", "dishes", "طبق", "Dish"),
    ("tbl", "tables", "tables", "طاولة", "Table"),
    ("ship", "ships", "ships", "شحنة", "Shipment"),
    ("auc", "auctions2", "auctions2", "مزاد", "Auction"),
    ("bid", "bids", "bids", "مزايدة", "Bid"),
    ("post", "posts", "posts", "منشور", "Post"),
    ("cmt", "comments", "comments", "تعليق", "Comment"),
    ("feed", "feeds", "feeds", "خلاصة", "Feed"),
    ("grp", "groups2", "groups2", "مجموعة", "Group"),
    ("chn", "channels", "channels", "قناة", "Channel"),
    ("msg", "messages", "messages", "رسالة", "Message"),
    ("file", "files", "files", "ملف", "File"),
    ("doc", "docs", "docs", "مستند", "Document"),
    ("form", "forms2", "forms2", "نموذج", "Form"),
    ("surv", "surveys", "surveys", "استبيان", "Survey"),
    ("poll", "polls", "polls", "تصويت", "Poll"),
    ("kb", "kb2", "kb2", "معرفة", "KB"),
    ("faq", "faqs", "faqs", "أسئلة", "FAQ"),
    ("tag", "tags", "tags", "وسم", "Tag"),
    ("cat", "cats", "cats", "تصنيف", "Category"),
    ("brand", "brands", "brands", "علامة", "Brand"),
    ("store", "stores", "stores", "متجر", "Store"),
    ("wh", "warehouses", "warehouses", "مستودع", "Warehouse"),
    ("vendor", "vendors", "vendors", "مورد", "Vendor"),
    ("cust", "customers", "customers", "زبون", "Customer"),
    ("staff", "staff", "staff", "موظف", "Staff"),
    ("role", "roles", "roles", "دور", "Role"),
    ("perm", "perms", "perms", "صلاحية", "Permission"),
    ("notif", "notifs", "notifs", "تنبيه", "Notification"),
    ("tmpl", "templates", "templates", "قالب", "Template"),
    ("hook", "hooks", "hooks", "ويب هوك", "Webhook"),
    ("api", "apis", "apis", "واجهة", "API key"),
    ("log", "logs", "logs", "سجل", "Log"),
    ("metric", "metrics2", "metrics2", "مقياس", "Metric"),
    ("report", "reports", "reports", "تقرير", "Report"),
    ("invoice2", "invoices", "invoices", "فاتورة", "Invoice"),
    ("tax2", "taxes", "taxes", "ضريبة", "Tax"),
    ("curr", "currencies", "currencies", "عملة", "Currency"),
    ("lang2", "langs", "langs", "لغة", "Language"),
    ("theme", "themes", "themes", "سمة", "Theme"),
    ("badge2", "badges", "badges", "شارة", "Badge"),
    ("quest2", "quests", "quests", "مهمة", "Quest"),
    ("ach", "achievements", "achievements", "إنجاز", "Achievement"),
    ("tier", "tiers", "tiers", "مستوى", "Tier"),
    ("plan2", "plans2", "plans2", "خطة", "Plan"),
    ("addon", "addons", "addons", "إضافة", "Add-on"),
    ("bundle", "bundles", "bundles", "باقة", "Bundle"),
    ("promo", "promos", "promos", "عرض", "Promo"),
    ("flash", "flashsales", "flashsales", "عرض خاطف", "Flash sale"),
    ("wait", "waitlists2", "waitlists2", "انتظار", "Waitlist"),
    ("room", "rooms", "rooms", "غرفة", "Room"),
    ("seat", "seats", "seats", "مقعد", "Seat"),
    ("vehicle", "vehicles", "vehicles", "مركبة", "Vehicle"),
    ("route", "routes", "routes", "مسار", "Route"),
    ("stop", "stops", "stops", "محطة", "Stop"),
    ("driver", "drivers", "drivers", "سائق", "Driver"),
    ("rider", "riders", "riders", "راكب", "Rider"),
    ("pet", "pets", "pets", "حيوان", "Pet"),
    ("book2", "books", "books", "كتاب", "Book"),
    ("chapter", "chapters", "chapters", "فصل", "Chapter"),
    ("podcast", "podcasts", "podcasts", "بودكاست", "Podcast"),
    ("episode", "episodes", "episodes", "حلقة", "Episode"),
    ("stream", "streams", "streams", "بث", "Stream"),
    ("clip", "clips", "clips", "مقطع", "Clip"),
    ("asset", "assets", "assets", "أصل", "Asset"),
    ("license", "licenses", "licenses", "ترخيص", "License"),
    ("key2", "keys", "keys", "مفتاح", "Key"),
    ("token2", "tokens", "tokens", "رمز", "Token"),
    ("device", "devices", "devices", "جهاز", "Device"),
    ("sensor", "sensors", "sensors", "مستشعر", "Sensor"),
    ("alert2", "alerts", "alerts", "إنذار", "Alert"),
    ("incident2", "incidents", "incidents", "حادثة", "Incident"),
    ("sla2", "slas", "slas", "اتفاقية", "SLA"),
    ("contract", "contracts", "contracts", "عقد", "Contract"),
    ("invoice_item", "invoice_items", "invoice_items", "بند فاتورة", "Invoice item"),
    ("project", "projects", "projects", "مشروع", "Project"),
    ("task2", "tasks2", "tasks2", "مهمة عمل", "Work task"),
    ("sprint", "sprints", "sprints", "سبيرنت", "Sprint"),
    ("milestone", "milestones", "milestones", "معلم", "Milestone"),
    ("time_entry", "time_entries", "time_entries", "وقت", "Time entry"),
    ("expense", "expenses", "expenses", "مصروف", "Expense"),
    ("budget", "budgets", "budgets", "ميزانية", "Budget"),
    ("invoice_rec", "recurring", "recurring", "فاتورة دورية", "Recurring"),
    ("sub_item", "sub_items", "sub_items", "بند اشتراك", "Sub item"),
    ("credit_note", "credit_notes", "credit_notes", "إشعار دائن", "Credit note"),
    ("debit_note", "debit_notes", "debit_notes", "إشعار مدين", "Debit note"),
    ("refund2", "refunds2", "refunds2", "مرتجع", "Refund"),
    ("return2", "returns", "returns", "إرجاع", "Return"),
    ("exchange", "exchanges", "exchanges", "استبدال", "Exchange"),
    ("warranty", "warranties", "warranties", "ضمان", "Warranty"),
    ("service2", "services2", "services2", "خدمة", "Service"),
    ("package", "packages", "packages", "طرد", "Package"),
    ("label", "labels", "labels", "ملصق", "Label"),
    ("zone", "zones", "zones", "منطقة", "Zone"),
    ("rate2", "rates", "rates", "تعريفة", "Rate"),
    ("carrier", "carriers", "carriers", "ناقل", "Carrier"),
    ("pickup", "pickups", "pickups", "استلام", "Pickup"),
    ("dropoff", "dropoffs", "dropoffs", "تسليم", "Dropoff"),
    ("slot2", "slots", "slots", "فترة", "Slot"),
    ("calendar", "calendars", "calendars", "تقويم", "Calendar"),
    ("reminder2", "reminders2", "reminders2", "تذكير", "Reminder"),
    ("habit", "habits", "habits", "عادة", "Habit"),
    ("goal", "goals", "goals", "هدف", "Goal"),
    ("note2", "notes2", "notes2", "ملاحظة", "Note"),
    ("folder", "folders", "folders", "مجلد", "Folder"),
    ("link", "links", "links", "رابط", "Link"),
    ("qr", "qrs", "qrs", "رمز QR", "QR"),
    ("barcode", "barcodes", "barcodes", "باركود", "Barcode"),
    ("print2", "prints", "prints", "طباعة", "Print job"),
    ("scan", "scans", "scans", "مسح", "Scan"),
    ("ocr", "ocrs", "ocrs", "تعرف نص", "OCR job"),
    ("translate", "translates", "translates", "ترجمة", "Translate job"),
    ("voice", "voices", "voices", "صوت", "Voice note"),
    ("sticker", "stickers", "stickers", "ملصق", "Sticker"),
    ("emoji", "emojis", "emojis", "إيموجي", "Emoji pack"),
    ("theme2", "ui_themes", "ui_themes", "واجهة", "UI theme"),
    ("locale", "locales", "locales", "محلية", "Locale"),
    ("timezone", "timezones", "timezones", "منطقة زمنية", "Timezone"),
    ("holiday", "holidays", "holidays", "عطلة", "Holiday"),
    ("shift", "shifts", "shifts", "وردية", "Shift"),
    ("attendance", "attendance", "attendance", "حضور", "Attendance"),
    ("leave2", "leaves", "leaves", "إجازة", "Leave"),
    ("payroll", "payrolls", "payrolls", "رواتب", "Payroll"),
    ("invoice_pay", "invoice_pays", "invoice_pays", "سداد", "Invoice payment"),
    ("payout", "payouts", "payouts", "صرف", "Payout"),
    ("settlement", "settlements", "settlements", "تسوية", "Settlement"),
    ("chargeback", "chargebacks", "chargebacks", "استرداد قسري", "Chargeback"),
    ("dispute", "disputes", "disputes", "نزاع", "Dispute"),
    ("case", "cases", "cases", "قضية", "Case"),
    ("evidence", "evidence", "evidence", "دليل", "Evidence"),
    ("policy", "policies", "policies", "سياسة", "Policy"),
    ("consent", "consents", "consents", "موافقة", "Consent"),
    ("gdpr", "gdpr", "gdpr", "خصوصية", "GDPR request"),
    ("export2", "exports", "exports", "تصدير بيانات", "Data export"),
    ("import2", "imports", "imports", "استيراد بيانات", "Data import"),
    ("migration", "migrations", "migrations", "ترحيل", "Migration"),
    ("sync", "syncs", "syncs", "مزامنة", "Sync job"),
    ("queue", "queues", "queues", "طابور", "Queue"),
    ("job_run", "job_runs", "job_runs", "تشغيل", "Job run"),
    ("cron", "crons", "crons", "جدولة زمنية", "Cron"),
    ("worker", "workers", "workers", "عامل", "Worker"),
    ("cache", "caches", "caches", "ذاكرة مؤقتة", "Cache"),
    ("session2", "sessions", "sessions", "جلسة", "Session"),
    ("device2", "user_devices", "user_devices", "جهاز مستخدم", "User device"),
    ("push", "pushes", "pushes", "دفع إشعار", "Push"),
    ("email2", "emails", "emails", "بريد", "Email"),
    ("sms", "sms", "sms", "رسالة نصية", "SMS"),
    ("call", "calls", "calls", "مكالمة", "Call"),
    ("meeting", "meetings", "meetings", "اجتماع", "Meeting"),
    ("webinar", "webinars", "webinars", "ندوة", "Webinar"),
    ("certificate", "certs", "certs", "شهادة", "Certificate"),
    ("diploma", "diplomas", "diplomas", "دبلوم", "Diploma"),
    ("transcript", "transcripts", "transcripts", "كشف درجات", "Transcript"),
    ("enrollment", "enrollments", "enrollments", "تسجيل", "Enrollment"),
    ("classroom", "classrooms", "classrooms", "فصل", "Classroom"),
    ("homework", "homeworks", "homeworks", "واجب", "Homework"),
    ("grade", "grades", "grades", "درجة", "Grade"),
    ("rubric", "rubrics", "rubrics", "معيار", "Rubric"),
    ("announcement", "announcements", "announcements", "إعلان", "Announcement"),
    ("newsletter", "newsletters", "newsletters", "نشرة", "Newsletter"),
    ("blog", "blogs", "blogs", "مقال", "Blog"),
    ("page", "pages", "pages", "صفحة", "Page"),
    ("media", "media", "media", "وسائط", "Media"),
    ("gallery", "galleries", "galleries", "معرض", "Gallery"),
    ("album", "albums", "albums", "ألبوم", "Album"),
    ("playlist", "playlists", "playlists", "قائمة تشغيل", "Playlist"),
    ("track2", "tracks", "tracks", "مقطع صوتي", "Track"),
    ("artist", "artists", "artists", "فنان", "Artist"),
    ("venue", "venues", "venues", "مكان", "Venue"),
    ("ticket2", "event_tickets", "event_tickets", "تذكرة فعالية", "Event ticket"),
    ("checkin2", "checkins", "checkins", "تسجيل حضور", "Check-in"),
    ("sponsor", "sponsors", "sponsors", "راعي", "Sponsor"),
    ("partner", "partners", "partners", "شريك", "Partner"),
    ("investor", "investors", "investors", "مستثمر", "Investor"),
    ("startup", "startups", "startups", "شركة ناشئة", "Startup"),
    ("pitch", "pitches", "pitches", "عرض", "Pitch"),
    ("grant2", "grants", "grants", "منحة", "Grant"),
    ("scholarship", "scholarships", "scholarships", "منحة دراسية", "Scholarship"),
    ("donation", "donations", "donations", "تبرع", "Donation"),
    ("ngo", "ngos", "ngos", "منظمة", "NGO"),
    ("volunteer", "volunteers", "volunteers", "متطوع", "Volunteer"),
    ("mission", "missions", "missions", "مهمة إنسانية", "Mission"),
    ("supply", "supplies", "supplies", "إمداد", "Supply"),
    ("warehouse2", "wh2", "wh2", "مخزن", "Warehouse unit"),
    ("bin", "bins", "bins", "صندوق", "Bin"),
    ("lot", "lots", "lots", "دفعة", "Lot"),
    ("serial", "serials", "serials", "رقم تسلسلي", "Serial"),
    ("batch", "batches", "batches", "دفعة إنتاج", "Batch"),
    ("recipe", "recipes", "recipes", "وصفة", "Recipe"),
    ("ingredient", "ingredients", "ingredients", "مكون", "Ingredient"),
    ("allergen", "allergens", "allergens", "مسبب حساسية", "Allergen"),
    ("nutrition", "nutrition", "nutrition", "تغذية", "Nutrition"),
    ("diet", "diets", "diets", "حمية", "Diet"),
    ("workout", "workouts", "workouts", "تمرين", "Workout"),
    ("exercise", "exercises", "exercises", "حركة", "Exercise"),
    ("set2", "sets", "sets", "مجموعة تمارين", "Set"),
    ("pr", "prs", "prs", "رقم شخصي", "Personal record"),
    ("coach", "coaches", "coaches", "مدرب", "Coach"),
    ("trainee", "trainees", "trainees", "متدرب", "Trainee"),
    ("program", "programs", "programs", "برنامج", "Program"),
    ("module", "modules", "modules", "وحدة", "Module"),
    ("unit", "units", "units", "وحدة قياس", "Unit"),
    ("measure", "measures", "measures", "قياس", "Measure"),
    ("sample", "samples", "samples", "عينة", "Sample"),
    ("lab", "labs", "labs", "مختبر", "Lab"),
    ("test2", "lab_tests", "lab_tests", "تحليل", "Lab test"),
    ("result", "results", "results", "نتيجة تحليل", "Result"),
    ("prescription", "prescriptions", "prescriptions", "وصفة طبية", "Prescription"),
    ("medicine", "medicines", "medicines", "دواء", "Medicine"),
    ("pharmacy", "pharmacies", "pharmacies", "صيدلية", "Pharmacy"),
    ("patient", "patients", "patients", "مريض", "Patient"),
    ("doctor2", "doctors", "doctors", "طبيب", "Doctor"),
    ("nurse", "nurses", "nurses", "ممرض", "Nurse"),
    ("ward", "wards", "wards", "جناح", "Ward"),
    ("bed", "beds", "beds", "سرير", "Bed"),
    ("triage", "triages", "triages", "فرز", "Triage"),
    ("vitals", "vitals", "vitals", "علامات حيوية", "Vitals"),
    ("insurance", "insurances", "insurances", "تأمين", "Insurance"),
    ("claim2", "claims", "claims", "مطالبة", "Claim"),
    ("policy2", "ins_policies", "ins_policies", "وثيقة تأمين", "Insurance policy"),
    ("premium", "premiums", "premiums", "قسط", "Premium"),
    ("coverage", "coverages", "coverages", "تغطية", "Coverage"),
    ("risk", "risks", "risks", "خطر", "Risk"),
    ("compliance2", "compliances", "compliances", "امتثال", "Compliance"),
    ("audit2", "audits", "audits", "مراجعة", "Audit"),
    ("finding", "findings", "findings", "ملاحظة مراجعة", "Finding"),
    ("control", "controls", "controls", "ضبط", "Control"),
    ("asset2", "it_assets", "it_assets", "أصل تقني", "IT asset"),
    ("ticket_it", "it_tickets", "it_tickets", "تذكرة تقنية", "IT ticket"),
    ("change", "changes", "changes", "تغيير", "Change"),
    ("release2", "releases", "releases", "إصدار", "Release"),
    ("deploy", "deploys", "deploys", "نشر", "Deploy"),
    ("env", "envs", "envs", "بيئة", "Environment"),
    ("secret", "secrets", "secrets", "سر", "Secret"),
    ("config2", "configs", "configs", "تهيئة", "Config entry"),
    ("flag", "flags", "flags", "علم", "Flag"),
    ("experiment", "experiments", "experiments", "تجربة", "Experiment"),
    ("variant", "variants", "variants", "متغير", "Variant"),
    ("funnel", "funnels", "funnels", "قمع", "Funnel"),
    ("cohort", "cohorts", "cohorts", "مجموعة", "Cohort"),
    ("segment", "segments", "segments", "شريحة", "Segment"),
    ("persona", "personas", "personas", "شخصية", "Persona"),
    ("journey", "journeys", "journeys", "رحلة", "Journey"),
    ("touch", "touches", "touches", "لمسة", "Touchpoint"),
    ("nps", "nps", "nps", "رضا", "NPS"),
    ("csat2", "csat2", "csat2", "تقييم خدمة", "CSAT"),
    ("ces", "ces", "ces", "جهد عميل", "CES"),
    ("feedback2", "feedbacks", "feedbacks", "ملاحظة", "Feedback"),
    ("idea", "ideas", "ideas", "فكرة", "Idea"),
    ("roadmap", "roadmaps", "roadmaps", "خارطة", "Roadmap"),
    ("feature2", "features2", "features2", "ميزة منتج", "Product feature"),
    ("bug", "bugs", "bugs", "خلل", "Bug"),
    ("issue", "issues", "issues", "مشكلة", "Issue"),
    ("pr2", "pulls", "pulls", "طلب دمج", "Pull request"),
    ("commit", "commits", "commits", "التزام", "Commit"),
    ("branch", "branches", "branches", "فرع", "Branch"),
    ("repo", "repos", "repos", "مستودع", "Repository"),
    ("wiki", "wikis", "wikis", "ويكي", "Wiki"),
    ("snippet", "snippets", "snippets", "مقتطف", "Snippet"),
    ("macro", "macros", "macros", "ماكرو", "Macro"),
    ("bot_cmd", "bot_cmds", "bot_cmds", "أمر بوت", "Bot command"),
    ("bot_flow", "bot_flows", "bot_flows", "تدفق بوت", "Bot flow"),
    ("bot_state", "bot_states", "bot_states", "حالة بوت", "Bot state"),
    ("bot_kb", "bot_kbs", "bot_kbs", "لوحة بوت", "Bot keyboard"),
    ("bot_msg", "bot_msgs", "bot_msgs", "رسالة بوت", "Bot message"),
]

# Domain-specific action sets: which vocab to apply
_SETS = {
    "default": CRUD + WORKFLOW,
    "commerce": CRUD + COMMERCE + WORKFLOW,
    "social": CRUD + SOCIAL,
    "game": CRUD + GAMING,
    "admin": CRUD + ADMIN + WORKFLOW,
}

_COMMERCE_PREFIXES = {
    "inv", "sku", "ord", "pay", "sub", "coup", "aff", "pts", "wal", "gift",
    "ship", "auc", "bid", "store", "vendor", "cust", "invoice2", "promo",
    "flash", "bundle", "addon", "plan2", "refund2", "return2", "exchange",
    "payout", "settlement", "chargeback", "premium", "donation",
}
_SOCIAL_PREFIXES = {
    "post", "cmt", "feed", "grp", "chn", "msg", "follow", "blog", "gallery",
    "album", "playlist", "artist", "sponsor", "partner",
}
_GAME_PREFIXES = {
    "badge2", "quest2", "ach", "tier", "pts", "gym", "workout", "exercise",
    "set2", "pr", "habit", "goal",
}
_ADMIN_PREFIXES = {
    "staff", "role", "perm", "log", "metric", "report", "hook", "api",
    "config2", "flag", "secret", "env", "deploy", "audit2", "compliance2",
}


def _action_set(prefix: str) -> tuple:
    if prefix in _COMMERCE_PREFIXES:
        return _SETS["commerce"]
    if prefix in _SOCIAL_PREFIXES:
        return _SETS["social"]
    if prefix in _GAME_PREFIXES:
        return _SETS["game"]
    if prefix in _ADMIN_PREFIXES:
        return _SETS["admin"]
    return _SETS["default"]


def _actor_for(action: str) -> str:
    if action in {
        "approve", "reject", "assign", "escalate", "ban", "unban", "role_set",
        "broadcast", "config", "metrics", "backup", "feature_flag", "import_data",
        "export", "audit", "audit_log", "health", "restore_backup", "toggle",
    }:
        return "admin"
    return "user"


def expand_scale_capabilities(*, target: int = 10000) -> int:
    """Generate capabilities until CAPABILITIES reaches target size."""
    before = len(CAPABILITIES)
    batch: list[Capability] = []

    for prefix, service, cat, ar_name, en_name in VERTICALS:
        for action, ar_act, en_act in _action_set(prefix):
            key = f"{prefix}_{action}"
            if key in CAPABILITIES:
                continue
            actor = _actor_for(action)
            batch.append(
                _c(
                    key,
                    service,
                    action,
                    f"{ar_act} {ar_name}",
                    f"{en_act} {en_name}",
                    actor,
                    cat=cat,
                )
            )
            if before + len(batch) >= target:
                break
        if before + len(batch) >= target:
            break

    # Extra numeric variants for remaining headroom (page slots, tiers, channels)
    if before + len(batch) < target:
        for i in range(1, 501):
            for kind, svc, cat in (
                ("page", "cms", "cms"),
                ("slot", "scheduling", "scheduling"),
                ("tier", "loyalty", "loyalty"),
                ("channel", "notify", "notify"),
                ("segment", "crm", "crm"),
                ("pipeline", "crm", "crm"),
                ("warehouse", "inventory", "inventory"),
                ("campaign", "marketing", "marketing"),
                ("experiment", "growth", "growth"),
                ("template", "content", "content"),
            ):
                key = f"{kind}_{i:03d}_open"
                if key in CAPABILITIES:
                    continue
                batch.append(
                    _c(
                        key,
                        svc,
                        f"open_{kind}_{i:03d}",
                        f"فتح {kind} {i}",
                        f"Open {kind} {i}",
                        cat=cat,
                    )
                )
                if before + len(batch) >= target:
                    break
            if before + len(batch) >= target:
                break

    if batch:
        _add(*batch)
    return len(CAPABILITIES) - before


# Auto-expand on import toward launch target
_ADDED = expand_scale_capabilities(target=11000)

__all__ = ["expand_scale_capabilities", "VERTICALS", "_ADDED"]
