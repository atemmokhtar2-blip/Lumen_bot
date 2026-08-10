"""Extract concrete capability keys from free-text (Arabic/English).

Maps user language → **real registry keys** only. Phantom labels that the
code generator cannot emit are never returned.
"""
from __future__ import annotations

from typing import Iterable

from .registry import CAPABILITIES

# keyword → registry key (or keys). Order within a group is priority.
_PATTERNS: dict[str, tuple[str, ...]] = {
    # ── defensive security (real handlers) ─────────────────────────────
    "sec_dns_check": (
        "dns", "dns records", "فحص dns", "سجلات dns", "a record", "cname", "dns lookup",
    ),
    "sec_mx_check": (
        "mx", "mx records", "سجلات mx", "mail exchange", "mx check",
    ),
    "sec_tls_check": (
        "tls", "ssl", "certificate", "شهادة ssl", "tls check", "ssl check", "شهادة",
    ),
    "sec_http_check": (
        "http status", "http code", "حالة http", "status code", "http check",
    ),
    "sec_headers_check": (
        "security headers", "http headers", "رؤوس http", "csp", "hsts", "headers check",
    ),
    "sec_domain_overview": (
        "domain scan", "website scan", "فحص الموقع", "site analysis", "domain scanner",
        "فحص نطاق", "domain overview", "domain check",
    ),
    "sec_report_phish": (
        "phishing", "تصيد", "تصيّد", "phish", "احتيال",
    ),
    "sec_report_incident": (
        "incident", "حادث أمني", "بلاغ أمني", "security incident", "soc",
    ),
    "sec_checklist": (
        "checklist", "توعية أمنية", "security checklist", "توعية",
    ),
    "sec_tips": (
        "security tips", "نصائح أمان", "نصائح أمنية",
    ),
    "sec_password_tips": (
        "password", "كلمة المرور", "كلمات المرور", "password strength", "قوة كلمة المرور",
    ),
    "sec_list_reports": (
        "security reports", "بلاغات أمنية", "list reports",
    ),
    # ── projects / ops ─────────────────────────────────────────────────
    "project_create": ("create project", "إنشاء مشروع", "new project", "مشروع جديد"),
    "project_list": ("list projects", "مشاريعي", "قائمة المشاريع", "projects list"),
    "project_view": ("view project", "عرض مشروع"),
    "project_search": ("search project", "بحث مشروع"),
    "project_stats": ("project stats", "إحصائيات المشروع"),
    "project_close": ("close project", "إغلاق مشروع"),
    # ── reports / export proxies (generic service) ─────────────────────
    "report_create": ("pdf", "تقرير pdf", "export pdf", "generate pdf", "تقرير", "report"),
    "report_list": ("list reports", "قائمة التقارير", "my reports"),
    "report_export": ("export report", "تصدير تقرير", "excel", "xlsx", "csv", "تصدير"),
    # ── tasks / notes as lightweight audit log stand-ins ───────────────
    "task_add": ("task", "مهمة", "todo", "مهام"),
    "task_list": ("list tasks", "قائمة المهام"),
    "note_add": ("note", "ملاحظة", "log entry", "سجل", "logs", "تسجيل", "سجلات", "audit log"),
    "note_list": ("list notes", "عرض الملاحظات", "show logs"),
    # ── tickets / support ──────────────────────────────────────────────
    "ticket_open": ("ticket", "تذكرة", "دعم", "support", "helpdesk"),
    "ticket_list": ("list tickets", "تذاكر مفتوحة"),
    "ticket_status": ("ticket status", "حالة تذكرة"),
    # ── rate / auth proxies (closest real caps) ────────────────────────
    "my_id": ("api key", "مفتاح api", "token", "my id"),
    "rules": ("rate limit", "rate limiting", "تحديد المعدل", "throttle", "rules"),
    # ── commerce (only when clearly asked) ─────────────────────────────
    "shop_catalog": ("shop", "store", "متجر", "كتالوج", "catalog", "منتجات"),
    "cart_view": ("cart", "سلة"),
    "plans": ("subscription", "اشتراك", "خطة"),
    "wallet_balance": ("wallet", "محفظة", "رصيد"),
    # ── iot / devops closest real packs ────────────────────────────────
    "saas_dashboard": ("docker", "kubernetes", "k8s", "ci/cd", "deployment", "نشر", "حاوية"),
    # ── core always-safe ───────────────────────────────────────────────
    "start": ("start", "بدء"),
    "help": ("help", "مساعدة"),
    "lang": ("i18n", "multi-language", "متعدد اللغات", "ترجمة", "lang"),
}

# Domain keyword groups → preferred registry keys (unioned when domain hits)
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
    "devops": (
        "start", "help", "lang", "task_add", "task_list", "note_add", "note_list",
        "project_create", "project_list", "ticket_open", "ticket_list",
    ),
    "iot": (
        "start", "help", "lang", "task_add", "task_list", "note_add", "note_list",
        "project_list",
    ),
    "blockchain": (
        "start", "help", "lang", "wallet_balance", "note_add", "ticket_open",
    ),
    "ai_ml": (
        "start", "help", "lang", "note_add", "note_list", "ticket_open",
    ),
    "ecommerce": (
        "start", "help", "lang", "shop_catalog", "cart_view", "shop_my_orders",
        "plans", "wallet_balance",
    ),
    "projects": (
        "start", "help", "project_create", "project_list", "project_view",
        "project_search", "project_stats", "task_add", "task_list", "note_add",
    ),
}


def _norm(text: str) -> str:
    return (text or "").lower()


def extract(text: str) -> list[str]:
    """Return registry keys mentioned in text (deduped, order preserved)."""
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

    # Always keep core when anything matched
    if out:
        for core in ("start", "help"):
            add(core)

    return out


def extract_for_domains(domains: Iterable[str]) -> list[str]:
    """Union of domain hint packs filtered to real registry keys."""
    out: list[str] = []
    seen: set[str] = set()
    for d in domains:
        for key in _DOMAIN_CAP_HINTS.get(d, ()):
            if key in CAPABILITIES and key not in seen:
                seen.add(key)
                out.append(key)
    return out


def extract_all(text: str, domains: Iterable[str] | None = None) -> list[str]:
    """Merge text extraction + domain hints."""
    keys = extract(text)
    if domains:
        for k in extract_for_domains(domains):
            if k not in keys:
                keys.append(k)
    return keys


__all__ = ["extract", "extract_for_domains", "extract_all"]
