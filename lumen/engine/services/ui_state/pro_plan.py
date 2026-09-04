"""Lumen Pro subscription plan definition (Telegram Stars / XTR).

Single source of truth for the Pro plan shown in the Billing surface.
Payment is in-Telegram only (Telegram Stars) — no external website/Stripe.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProPlanResource:
    icon: str
    label: str
    value: str


@dataclass(frozen=True)
class ProPlanInclude:
    icon: str
    label: str


# ── Plan identity ──────────────────────────────────────────────
PRO_PLAN_ID = "lumen_pro"
PRO_PLAN_TITLE = "🚀 Lumen Pro"
PRO_PLAN_PRICE_USD = 10  # $10/month
PRO_PLAN_PRICE_STARS = 800  # Telegram Stars (XTR) — $10 × 80 stars/$ (same ratio as prior 25→2000)
PRO_PLAN_DURATION_MONTHS = 1  # 1 month subscription
PRO_PLAN_DURATION_LABEL = "شهر"  # Arabic: "1 month"
PRO_PLAN_BOT_LIMIT = 10  # up to 10 bots while Pro is active

# Telegram invoice payload (must be unique-ish; we embed plan id)
PRO_PLAN_INVOICE_PAYLOAD = "lumen_pro_monthly_v2"

# ── Resources (shown in Rich Messages native table) ───────────
PRO_PLAN_RESOURCES: tuple[ProPlanResource, ...] = (
    ProPlanResource("💾", "المساحة التخزينية", "3 GB"),
    ProPlanResource("🧠", "الذاكرة (RAM)", "2 GB مشتركة"),
    ProPlanResource("⚡", "المعالج (CPU)", "0.5 نواة"),
    ProPlanResource("🤖", "عدد البوتات", f"حتى {PRO_PLAN_BOT_LIMIT} بوتات"),
    ProPlanResource("⏱️", "مدة الاستضافة", PRO_PLAN_DURATION_LABEL),
    ProPlanResource("💳", "نظام الرصيد", "Credits لكل استخدام"),
)

# ── What the subscription includes ─────────────────────────────
PRO_PLAN_INCLUDES: tuple[ProPlanInclude, ...] = (
    ProPlanInclude("🏠", "استضافة دائمة مجانية للبوتات طوال الاشتراك"),
    ProPlanInclude("🔒", "بيئة معزولة لكل بوت"),
    ProPlanInclude("📊", "مراقبة وحالة لحظية"),
    ProPlanInclude("💰", "رصيد كريديتات شهري"),
    ProPlanInclude("💾", "اشتراك محفوظ في قاعدة البيانات — يبقى حتى لو مسحت البوت"),
)

# ── Rich Messages table spec ───────────────────────────────────
PRO_PLAN_TABLE_HEADERS = ("المورد", "القيمة")
PRO_PLAN_TABLE_CAPTION = "موارد خطة Lumen Pro"


def pro_plan_table_rows() -> list[list[str]]:
    """Rows for the Rich Messages native <table>."""
    return [[f"{r.icon} {r.label}", r.value] for r in PRO_PLAN_RESOURCES]


def pro_plan_includes_text() -> str:
    """Arabic bullet list of what the subscription includes."""
    return "\n".join(f"{inc.icon} {inc.label}" for inc in PRO_PLAN_INCLUDES)


def pro_plan_invoice_description() -> str:
    """Short description for the Telegram invoice (≤255 chars).

    Explicitly states that the subscription is saved in the database and
    survives bot deletion / re-entry — building user trust.
    """
    return (
        f"اشتراك Lumen Pro شهري — "
        f"3GB تخزين، 2GB RAM مشتركة، 0.5 CPU، "
        f"حتى {PRO_PLAN_BOT_LIMIT} بوتات، استضافة مجانية، مدة {PRO_PLAN_DURATION_LABEL}. "
        f"💾 اشتراكك محفوظ في قاعدة البيانات — يبقى حتى لو مسحت البوت ورجعت."
    )


__all__ = [
    "PRO_PLAN_ID",
    "PRO_PLAN_TITLE",
    "PRO_PLAN_PRICE_USD",
    "PRO_PLAN_PRICE_STARS",
    "PRO_PLAN_DURATION_MONTHS",
    "PRO_PLAN_DURATION_LABEL",
    "PRO_PLAN_BOT_LIMIT",
    "PRO_PLAN_INVOICE_PAYLOAD",
    "PRO_PLAN_RESOURCES",
    "PRO_PLAN_INCLUDES",
    "PRO_PLAN_TABLE_HEADERS",
    "PRO_PLAN_TABLE_CAPTION",
    "pro_plan_table_rows",
    "pro_plan_includes_text",
    "pro_plan_invoice_description",
]
