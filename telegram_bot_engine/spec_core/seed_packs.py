"""Demo seed rows per vertical — so generated bots are usable on first /start.

Seed data is for the GENERATED bot's database (end-users), not the generator.
"""
from __future__ import annotations

from typing import Any


def _shop() -> dict[str, list[dict[str, Any]]]:
    return {
        "Product": [
            {
                "id": 1,
                "sku": "DEMO-PACK",
                "title": "Starter Pack",
                "title_ar": "باقة البداية",
                "price_cents": 499,
                "currency": "USD",
                "stock": 100,
                "digital": True,
                "payload": "digital:starter",
            },
            {
                "id": 2,
                "sku": "DEMO-PRO",
                "title": "Pro Bundle",
                "title_ar": "باقة احترافية",
                "price_cents": 1499,
                "currency": "USD",
                "stock": 50,
                "digital": True,
                "payload": "digital:pro",
            },
            {
                "id": 3,
                "sku": "DEMO-MERCH",
                "title": "Brand Tee",
                "title_ar": "تيشيرت",
                "price_cents": 2499,
                "currency": "USD",
                "stock": 20,
                "digital": False,
                "payload": "physical:tee",
            },
        ],
        "Coupon": [
            {
                "code": "SAVE10",
                "percent_off": 10,
                "active": True,
                "max_uses": 1000,
            },
            {
                "code": "WELCOME",
                "percent_off": 15,
                "active": True,
                "max_uses": 1,
                "per_user": True,
            },
        ],
    }


def _subscriptions() -> dict[str, list[dict[str, Any]]]:
    return {
        "Plan": [
            {
                "id": 1,
                "code": "free",
                "name": "Free",
                "name_ar": "مجاني",
                "price_cents": 0,
                "currency": "USD",
                "duration_days": 3650,
                "benefits": ["basic_access"],
            },
            {
                "id": 2,
                "code": "vip_monthly",
                "name": "VIP Monthly",
                "name_ar": "VIP شهري",
                "price_cents": 999,
                "currency": "USD",
                "duration_days": 30,
                "benefits": ["basic_access", "premium", "priority_support"],
            },
            {
                "id": 3,
                "code": "vip_yearly",
                "name": "VIP Yearly",
                "name_ar": "VIP سنوي",
                "price_cents": 9999,
                "currency": "USD",
                "duration_days": 365,
                "benefits": ["basic_access", "premium", "priority_support", "badge"],
            },
        ],
    }


def _points() -> dict[str, list[dict[str, Any]]]:
    return {
        "UserBalance": [
            {"user_id": 10001, "balance": 500, "display": "DemoAce"},
            {"user_id": 10002, "balance": 320, "display": "DemoBee"},
            {"user_id": 10003, "balance": 150, "display": "DemoCat"},
        ],
        "PointLedger": [
            {"user_id": 10001, "delta": 500, "reason": "seed", "created_at": "2026-01-01T00:00:00Z"},
            {"user_id": 10002, "delta": 320, "reason": "seed", "created_at": "2026-01-01T00:00:00Z"},
            {"user_id": 10003, "delta": 150, "reason": "seed", "created_at": "2026-01-01T00:00:00Z"},
        ],
    }


def _contests() -> dict[str, list[dict[str, Any]]]:
    return {
        "Contest": [
            {
                "id": 1,
                "title": "Launch Giveaway",
                "title_ar": "سحب الإطلاق",
                "status": "open",
                "rules": "One entry per user. Winner announced by admin.",
                "ends_at": "2026-12-31T23:59:59Z",
            }
        ],
        "Entry": [],
    }


def _growth() -> dict[str, list[dict[str, Any]]]:
    return {
        "ReferralReward": [
            {"event": "invite_accepted", "points": 50, "inviter_points": 100},
            {"event": "daily_checkin", "points": 10},
        ],
        "Achievement": [
            {"code": "first_checkin", "title": "First Check-in", "points": 5},
            {"code": "streak_7", "title": "7-Day Streak", "points": 70},
            {"code": "refer_3", "title": "3 Friends", "points": 150},
        ],
    }


def _saas() -> dict[str, list[dict[str, Any]]]:
    data = _subscriptions()
    data["WebhookConfig"] = []
    data["Content"] = [
        {
            "key": "privacy",
            "en": "We store Telegram user id, subscription status, and payment charge ids required for fulfillment. Contact the bot owner to request deletion.",
            "ar": "نحتفظ بمعرف تيليجرام وحالة الاشتراك ومعرفات الدفع اللازمة للتنفيذ. تواصل مع مالك البوت لطلب الحذف.",
        },
        {
            "key": "terms",
            "en": "Use of this bot is at your own risk. Paid plans renew only when you pay again unless stated otherwise.",
            "ar": "استخدام البوت على مسؤوليتك. الخطط المدفوعة لا تتجدد تلقائياً إلا إذا نُص على ذلك.",
        },
    ]
    return data


def _crm() -> dict[str, list[dict[str, Any]]]:
    return {
        "Lead": [
            {
                "id": 1,
                "name": "Demo Lead",
                "contact": "@demo_lead",
                "status": "new",
                "note": "Interested in VIP",
            }
        ],
        "Deal": [],
        "PipelineStage": [
            {"code": "new", "label": "New"},
            {"code": "contacted", "label": "Contacted"},
            {"code": "won", "label": "Won"},
            {"code": "lost", "label": "Lost"},
        ],
    }


def _support() -> dict[str, list[dict[str, Any]]]:
    return {
        "KbArticle": [
            {
                "id": 1,
                "slug": "getting-started",
                "title": "Getting started",
                "title_ar": "البداية",
                "body": "Use /ticket to open support. Check /faq style articles here.",
                "body_ar": "استخدم /ticket لفتح تذكرة. راجع المقالات هنا.",
            },
            {
                "id": 2,
                "slug": "billing",
                "title": "Billing",
                "title_ar": "الفوترة",
                "body": "Payments are processed via Telegram. Keep your charge receipt.",
                "body_ar": "الدفع عبر تيليجرام. احتفظ بإيصال العملية.",
            },
        ],
        "Ticket": [],
    }


def _education() -> dict[str, list[dict[str, Any]]]:
    return {
        "Course": [
            {
                "id": 1,
                "code": "intro",
                "title": "Intro Course",
                "title_ar": "دورة تمهيدية",
                "lessons": 3,
            }
        ],
        "Lesson": [
            {"id": 1, "course_id": 1, "order": 1, "title": "Welcome", "body": "Welcome to the course."},
            {"id": 2, "course_id": 1, "order": 2, "title": "Basics", "body": "Core concepts."},
            {"id": 3, "course_id": 1, "order": 3, "title": "Next steps", "body": "You are done."},
        ],
        "Quiz": [
            {
                "id": 1,
                "course_id": 1,
                "question": "2+2=?",
                "options": ["3", "4", "5"],
                "answer_index": 1,
            }
        ],
    }


def _restaurant() -> dict[str, list[dict[str, Any]]]:
    return {
        "MenuItem": [
            {"id": 1, "name": "Burger", "name_ar": "برجر", "price_cents": 800, "currency": "USD", "category": "mains"},
            {"id": 2, "name": "Fries", "name_ar": "بطاطس", "price_cents": 300, "currency": "USD", "category": "sides"},
            {"id": 3, "name": "Cola", "name_ar": "كولا", "price_cents": 200, "currency": "USD", "category": "drinks"},
        ],
        "TableSlot": [
            {"id": 1, "label": "Table A", "seats": 4},
            {"id": 2, "label": "Table B", "seats": 2},
        ],
    }


def _jobs() -> dict[str, list[dict[str, Any]]]:
    return {
        "Job": [
            {
                "id": 1,
                "title": "Support Agent",
                "title_ar": "موظف دعم",
                "location": "Remote",
                "description": "Handle Telegram support tickets.",
            },
            {
                "id": 2,
                "title": "Bot Developer",
                "title_ar": "مطور بوتات",
                "location": "Remote",
                "description": "python-telegram-bot experience preferred.",
            },
        ],
        "Application": [],
    }


def _marketplace() -> dict[str, list[dict[str, Any]]]:
    return {
        "Listing": [
            {
                "id": 1,
                "title": "Used Laptop",
                "title_ar": "لابتوب مستعمل",
                "price_cents": 35000,
                "currency": "USD",
                "seller_id": 10001,
                "status": "open",
            }
        ],
    }


def _events() -> dict[str, list[dict[str, Any]]]:
    return {
        "Event": [
            {
                "id": 1,
                "title": "Launch Meetup",
                "title_ar": "لقاء الإطلاق",
                "starts_at": "2026-09-01T18:00:00Z",
                "capacity": 50,
                "status": "open",
            }
        ],
        "Rsvp": [],
    }


def _wallet() -> dict[str, list[dict[str, Any]]]:
    return {
        "Wallet": [
            {"user_id": 10001, "balance_cents": 1000, "currency": "USD"},
        ],
        "WalletLedger": [
            {"user_id": 10001, "delta_cents": 1000, "reason": "seed", "created_at": "2026-01-01T00:00:00Z"},
        ],
    }


def _community() -> dict[str, list[dict[str, Any]]]:
    return {
        "Post": [
            {
                "id": 1,
                "user_id": 10001,
                "body": "Welcome to the community feed!",
                "likes": 0,
            }
        ],
    }


def _group() -> dict[str, list[dict[str, Any]]]:
    return {
        "Config": [
            {"key": "welcome_enabled", "value": "1"},
            {"key": "welcome_text", "value": "Welcome! Read the rules with /rules"},
            {"key": "rules_text", "value": "1) Be respectful\n2) No spam\n3) Follow admin instructions"},
        ],
    }


def _booking() -> dict[str, list[dict[str, Any]]]:
    return {
        "Slot": [
            {"id": 1, "label": "09:00", "capacity": 1},
            {"id": 2, "label": "10:00", "capacity": 1},
            {"id": 3, "label": "11:00", "capacity": 1},
        ],
        "Booking": [],
    }


PACKS: dict[str, dict[str, list[dict[str, Any]]]] = {
    "shop": _shop(),
    "subscriptions": _subscriptions(),
    "points": _points(),
    "contests": _contests(),
    "growth": _growth(),
    "saas": _saas(),
    "crm": _crm(),
    "support_tickets": _support(),
    "support_pro": _support(),
    "education": _education(),
    "restaurant": _restaurant(),
    "jobs": _jobs(),
    "marketplace": _marketplace(),
    "events": _events(),
    "wallet": _wallet(),
    "community": _community(),
    "group_management": _group(),
    "booking": _booking(),
}


def seed_for_preset(preset: str) -> dict[str, list[dict[str, Any]]]:
    """Return a deep-ish copy of seed rows for preset."""
    raw = PACKS.get(preset or "") or {}
    out: dict[str, list[dict[str, Any]]] = {}
    for k, rows in raw.items():
        out[k] = [dict(r) for r in rows]
    return out


def merge_seed(
    base: dict[str, list[dict[str, Any]]],
    extra: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    merged = {k: [dict(r) for r in v] for k, v in (base or {}).items()}
    for k, rows in (extra or {}).items():
        merged.setdefault(k, [])
        merged[k].extend(dict(r) for r in rows)
    return merged


__all__ = ["PACKS", "seed_for_preset", "merge_seed"]
