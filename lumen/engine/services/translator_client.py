"""Capability helpers for bot-intent → feature keys.

Translate/chat LLM paths are permanently removed. Agent LLM uses model_catalog + agent_brain.
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_FEATURE_ALIASES = {
    "admin_ban_bot": "user_ban",
    "admin_unban_bot": "user_unban",
    "ban": "user_ban",
    "kick": "user_kick",
    "mute": "user_mute",
    "warn": "user_warn",
    "welcome": "welcome_set",
    "setwelcome": "welcome_set",
    "content_list": "shop_catalog",
    "product_list": "shop_catalog",
    "products": "shop_catalog",
    "catalog": "shop_catalog",
    "shop": "shop_catalog",
    "store": "shop_catalog",
    "add_to_cart": "cart_add",
    "view_cart": "cart_view",
    "checkout": "cart_checkout",
    "orders": "shop_my_orders",
    "my_orders": "shop_my_orders",
    "order_list": "shop_my_orders",
    "todo_add": "task_add",
    "todo_list": "task_list",
    "tasks": "task_list",
    "notes": "note_list",
    "add_note": "note_add",
    "list_notes": "note_list",
    "open_ticket": "ticket_open",
    "my_tickets": "ticket_my",
    "book": "book_slot",
    "booking": "book_slot",
    "appointments": "clinic_my",
    "lead": "lead_capture",
    "leads": "lead_list",
    "echo_message": "echo",
    "reply": "echo",
    "pdf": "images_to_pdf",
    "image_to_pdf": "images_to_pdf",
    "images_to_pdf": "images_to_pdf",
    "photo_to_pdf": "images_to_pdf",
    "img2pdf": "images_to_pdf",
}

_AR_RULES: list[tuple[str, list[str]]] = [
    (r"يرحب|ترحيب|ترحيب.?بال|welcome", ["welcome_set", "welcome_show"]),
    (r"يحظر|حظر|بان|ban(?!k)", ["user_ban"]),
    (r"يطرد|طرد|kick", ["user_kick"]),
    (r"يكتم|كتم|ميوت|mute", ["user_mute"]),
    (r"ينذر|انذار|تحذير|warn", ["user_warn"]),
    (r"قواعد|laws|rules", ["rules"]),
    (r"يشتم|سب|إساء|مسيئ|insult|toxic|bad.?word|كلمات.?مسي", ["user_ban", "delete_message", "user_warn"]),
    (r"يمسح|حذف.?رس|delete.?msg", ["delete_message"]),
    (
        r"متجر|تسوق|منتج|منتجات|أسعار|اسعار|سلة|طلب\b|طلبات|شراء|"
        r"ecommerce|shop|store|cart|product|catalog|checkout|price",
        ["shop_catalog", "cart_view", "cart_add", "cart_checkout", "shop_my_orders"],
    ),
    (r"مهام|مهمة|\btodo\b|\btasks?\b", ["task_add", "task_list", "task_done"]),
    (r"ملاحظات|ملاحظة|\bnotes?\b", ["note_add", "note_list"]),
    (r"تذاكر|تذكرة|دعم\s*فني|ticket|support", ["ticket_open", "ticket_my"]),
    (r"حجز|موعد|book\s*slot|appointment", ["book_slot", "book_list", "book_cancel"]),
    (r"عيادة|clinic|doctor", ["clinic_my", "book_slot"]),
    (r"عملاء|lead|leads", ["lead_capture", "lead_list"]),
    (r"تذكير|remind", ["remind_set"]),
    (r"إعلان|announce", ["announce"]),
    (r"faq|أسئلة\s*شائعة", ["faq_show"]),
    (
        r"صور|صورة|pdf|صور\s*لـ?\s*pdf|images?\s*to\s*pdf|ملفات\s*pdf|ملف\s*pdf",
        ["pdf_start", "pdf_done", "pdf_clear", "pdf_status", "images_to_pdf"],
    ),
    (
        r"مطعم|منيو|توصيل\s*طلب|restaurant|food\s*order|delivery\s*bot",
        ["shop_catalog", "cart_add", "cart_view", "cart_checkout", "shop_my_orders"],
    ),
    (
        r"فواتير|مدفوعات|invoice|billing",
        ["shop_catalog", "cart_checkout", "shop_my_orders", "payment_receipt"],
    ),
]


def _spec_core_capabilities() -> list[str]:
    try:
        from lumen.engine.services.capability_detection.catalog import CAPABILITIES
        return sorted(str(key) for key in CAPABILITIES.keys())
    except Exception as exc:
        logger.warning("spec_core capability list unavailable: %s", exc)
        return []


def _rule_features_from_text(text: str, allowed: set[str]) -> list[str]:
    raw = (text or "").strip().lower()
    if not raw:
        return []
    found: list[str] = []
    for pattern, keys in _AR_RULES:
        if re.search(pattern, raw, re.I):
            for k in keys:
                canon = _FEATURE_ALIASES.get(k, k)
                if canon in allowed and canon not in found:
                    found.append(canon)
    if found:
        for core in ("start", "help"):
            if core in allowed and core not in found:
                found.append(core)
        domain = [k for k in found if k not in {"echo", "start", "help", "lang", "language", "cancel"}]
        if domain and "echo" in found:
            found = [k for k in found if k != "echo"]
    return found[:12]


def translate_request(text: str, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Removed — agent owns LLM."""
    return None


def chat_request(message: str, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Removed — agent owns LLM."""
    return None


def translate_via_groq(text: str, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    return None


def chat_via_gemini(message: str, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    return None


def translate_infinite_via_gemini(text: str, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    return None


def translate_infinite_via_groq(text: str, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    return None


__all__ = [
    "_spec_core_capabilities",
    "_rule_features_from_text",
    "translate_request",
    "chat_request",
]
