"""Extract concrete capability keys from free-text (Arabic/English).

Maps user language → **real registry keys** only. Phantom labels that the
code generator cannot emit are never returned.
"""
from __future__ import annotations

from typing import Iterable

from .registry import CAPABILITIES

_PATTERNS: dict[str, tuple[str, ...]] = {
    # security
    "sec_dns_check": ("dns", "dns records", "فحص dns", "سجلات dns", "a record", "cname", "dns lookup"),
    "sec_mx_check": ("mx", "mx records", "سجلات mx", "mail exchange", "mx check"),
    "sec_tls_check": ("tls", "ssl", "certificate", "شهادة ssl", "tls check", "ssl check"),
    "sec_http_check": ("http status", "http code", "حالة http", "status code", "http check"),
    "sec_headers_check": ("security headers", "http headers", "رؤوس http", "csp", "hsts", "headers check"),
    "sec_domain_overview": (
        "domain scan", "website scan", "فحص الموقع", "site analysis", "domain scanner",
        "فحص نطاق", "domain overview", "domain check",
    ),
    "sec_report_phish": ("phishing", "تصيد", "تصيّد", "phish", "احتيال"),
    "sec_report_incident": ("incident", "حادث أمني", "بلاغ أمني", "security incident", "soc"),
    "sec_checklist": ("checklist", "توعية أمنية", "security checklist", "توعية"),
    "sec_tips": ("security tips", "نصائح أمان", "نصائح أمنية"),
    "sec_password_tips": ("password", "كلمة المرور", "كلمات المرور", "password strength"),
    "sec_list_reports": ("security reports", "بلاغات أمنية"),
    # IoT
    "device_list": ("device list", "أجهزة", "اجهزة", "devices", "قائمة الأجهزة", "smart devices"),
    "device_create": ("add device", "تسجيل جهاز", "register device", "device create"),
    "device_view": ("device status", "حالة جهاز", "device view"),
    "sensor_list": ("sensors", "حساسات", "مستشعرات", "sensor list", "sensor data"),
    "sensor_create": ("add sensor", "إضافة حساس", "sensor create"),
    "sensor_view": ("sensor reading", "قراءة حساس", "telemetry"),
    # DevOps
    "deploy_list": ("deployments", "نشر", "deployment", "deploy list", "deploy status"),
    "deploy_create": ("new deploy", "إنشاء نشر", "deploy create"),
    "deploy_view": ("deploy view", "عرض نشر"),
    "env_list": ("environments", "بيئات", "env list", "staging", "production env"),
    "secret_list": ("secrets", "أسرار", "secret list"),
    "log_list": ("logs", "سجلات", "logging", "audit log", "تسجيل"),
    # Blockchain / wallet
    "wallet_balance": ("wallet", "محفظة", "balance", "رصيد", "crypto wallet"),
    "wallet_history": ("transaction history", "سجل معاملات", "tx history"),
    "wallet_transfer": ("send transaction", "تحويل", "transfer crypto"),
    "wallet_topup": ("topup", "شحن محفظة", "top-up"),
    # AI assist (notes/tasks as lightweight workspace)
    "note_add": ("note", "ملاحظة", "prompt log", "سجل برومبت", "ai log"),
    "note_list": ("list notes", "عرض الملاحظات", "show logs"),
    "task_add": ("task", "مهمة", "todo", "مهام", "job queue"),
    "task_list": ("list tasks", "قائمة المهام"),
    # Healthcare
    "clinic_book": ("book appointment", "حجز موعد", "موعد طبي"),
    "clinic_my": ("my appointments", "مواعيدي"),
    "patient_list": ("patients", "مرضى", "patient list"),
    "patient_create": ("new patient", "تسجيل مريض"),
    "doctor2_list": ("doctors", "أطباء", "doctor list"),
    "prescription_list": ("prescriptions", "وصفات", "وصفة طبية"),
    "prescription_create": ("new prescription", "إنشاء وصفة"),
    # Education
    "course_list": ("courses", "دورات", "كورسات", "course list"),
    "course_enroll": ("enroll", "تسجيل في دورة"),
    "lesson_list": ("lessons", "دروس", "lesson list"),
    "lesson_open": ("open lesson", "فتح درس"),
    "quiz_start": ("quiz", "اختبار", "امتحان", "start quiz"),
    "quiz_score": ("quiz score", "درجة الاختبار"),
    "homework_submit": ("homework", "واجب", "submit homework"),
    # Commerce
    "shop_catalog": ("shop", "store", "متجر", "كتالوج", "catalog", "منتجات"),
    "cart_view": ("cart", "سلة"),
    "plans": ("subscription", "اشتراك", "خطة"),
    # Social / community
    "post_create": ("create post", "منشور", "نشر بوست"),
    "post_list": ("feed", "المنشورات", "timeline"),
    "post_like": ("like", "إعجاب", "اعجاب"),
    "post_comment": ("comment", "تعليق"),
    # Projects / reports
    "project_create": ("create project", "إنشاء مشروع", "new project", "مشروع جديد"),
    "project_list": ("list projects", "مشاريعي", "قائمة المشاريع", "projects list"),
    "project_view": ("view project", "عرض مشروع"),
    "project_search": ("search project", "بحث مشروع"),
    "project_stats": ("project stats", "إحصائيات المشروع"),
    "report_create": ("pdf", "تقرير pdf", "export pdf", "generate pdf", "تقرير", "report"),
    "report_list": ("list reports", "قائمة التقارير", "my reports"),
    "report_export": ("export report", "تصدير تقرير", "excel", "xlsx", "csv", "تصدير"),
    # Support
    "ticket_open": ("ticket", "تذكرة", "دعم", "support", "helpdesk"),
    "ticket_list": ("list tickets", "تذاكر مفتوحة"),
    "ticket_status": ("ticket status", "حالة تذكرة"),
    # Gaming proxies
    "leaderboard": ("leaderboard", "لوحة المتصدرين", "متصدرين"),
    "contests": ("tournament", "بطولة", "مسابقة", "contest"),
    "join_contest": ("join tournament", "انضم للبطولة"),
    "balance": ("xp", "points balance", "نقاطي"),
    "achievement_list": ("achievement", "إنجاز", "انجاز", "achievements"),
    # Core
    "start": ("start", "بدء"),
    "help": ("help", "مساعدة"),
    "lang": ("i18n", "multi-language", "متعدد اللغات", "ترجمة", "lang"),
    "my_id": ("api key", "مفتاح api", "token", "my id"),
    "rules": ("rate limit", "rate limiting", "تحديد المعدل", "throttle", "rules"),
}

_DOMAIN_CAP_HINTS: dict[str, tuple[str, ...]] = {
    "cybersecurity": (
        "start", "help", "lang",
        "sec_dns_check", "sec_mx_check", "sec_tls_check", "sec_http_check",
        "sec_headers_check", "sec_domain_overview", "sec_password_tips",
        "sec_report_phish", "sec_report_incident", "sec_checklist", "sec_tips",
        "sec_list_reports", "sec_close_report",
        "project_create", "project_list", "project_view", "project_search",
        "report_create", "report_list", "report_export",
        "note_add", "note_list", "task_add", "task_list",
        "ticket_open", "ticket_list", "my_id", "rules",
    ),
    "iot": (
        "start", "help", "lang",
        "device_list", "device_create", "device_view", "device_search",
        "sensor_list", "sensor_create", "sensor_view", "sensor_search",
        "note_add", "note_list", "task_add", "task_list", "ticket_open",
        "project_list", "project_create",
    ),
    "blockchain": (
        "start", "help", "lang",
        "wallet_balance", "wallet_history", "wallet_transfer", "wallet_topup",
        "note_add", "ticket_open", "ticket_list", "rules", "my_id",
    ),
    "ai_ml": (
        "start", "help", "lang",
        "note_add", "note_list", "task_add", "task_list",
        "ticket_open", "project_create", "project_list",
    ),
    "devops": (
        "start", "help", "lang",
        "deploy_list", "deploy_create", "deploy_view", "deploy_search",
        "env_list", "secret_list", "log_list",
        "task_add", "task_list", "note_add", "note_list", "ticket_open",
        "project_create", "project_list",
    ),
    "healthcare": (
        "start", "help", "lang",
        "clinic_book", "clinic_my", "clinic_cancel", "clinic_slots",
        "patient_list", "patient_create", "patient_view",
        "doctor2_list", "doctor2_view",
        "prescription_list", "prescription_create",
        "ticket_open", "note_add",
    ),
    "education": (
        "start", "help", "lang",
        "course_list", "course_enroll", "lesson_list", "lesson_open",
        "quiz_start", "quiz_score", "homework_submit", "homework_list",
    ),
    "ecommerce": (
        "start", "help", "lang", "shop_catalog", "cart_view", "shop_my_orders",
        "plans", "wallet_balance",
    ),
    "marketplace": (
        "start", "help", "lang", "shop_catalog", "cart_view", "wallet_balance",
        "ticket_open",
    ),
    "finance": (
        "start", "help", "lang", "wallet_balance", "wallet_history",
        "report_create", "report_list", "ticket_open",
    ),
    "logistics": (
        "start", "help", "lang", "ticket_open", "task_list", "note_add",
    ),
    "gaming": (
        "start", "help", "lang", "leaderboard", "contests", "join_contest",
        "balance", "achievement_list", "points_history",
    ),
    "social": (
        "start", "help", "lang", "post_create", "post_list", "post_like",
        "post_comment", "profile_view",
    ),
    "projects": (
        "start", "help", "project_create", "project_list", "project_view",
        "project_search", "project_stats", "task_add", "task_list", "note_add",
    ),
    "saas": (
        "start", "help", "lang", "ticket_open", "project_list",
    ),
    "hr": (
        "start", "help", "hr_leave_request", "hr_leave_list", "hr_checkin",
    ),
    "fitness": (
        "start", "help", "lang", "gym_checkin", "gym_membership",
    ),
}


def _norm(text: str) -> str:
    return (text or "").lower()


def extract(text: str) -> list[str]:
    t = _norm(text)
    out: list[str] = []
    seen: set[str] = set()

    def add(key: str) -> None:
        if key in CAPABILITIES and key not in seen:
            seen.add(key)
            out.append(key)

    for key, keywords in _PATTERNS.items():
        if any(kw in t for kw in keywords):
            add(key)

    if out:
        for core in ("start", "help"):
            add(core)
    return out


def extract_for_domains(domains: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for d in domains:
        for key in _DOMAIN_CAP_HINTS.get(d, ()):
            if key in CAPABILITIES and key not in seen:
                seen.add(key)
                out.append(key)
    return out


def extract_all(text: str, domains: Iterable[str] | None = None) -> list[str]:
    keys = extract(text)
    if domains:
        for k in extract_for_domains(domains):
            if k not in keys:
                keys.append(k)
    return keys


__all__ = ["extract", "extract_for_domains", "extract_all"]
