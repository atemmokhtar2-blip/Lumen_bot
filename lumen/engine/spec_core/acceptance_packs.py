"""Acceptance tests per market vertical — for generated bots' end-user flows.

Used by presets and samples so every commercial bot ships with a QA checklist.
"""
from __future__ import annotations

from typing import Any

from .schema import AcceptanceTest


def _t(name: str, steps: list[str], expected: str) -> AcceptanceTest:
    return AcceptanceTest(name=name, steps=steps, expected=expected)


# ── packs ─────────────────────────────────────────────────────────────

SHOP = [
    _t(
        "catalog_loads",
        ["User sends /shop or taps Shop", "Bot lists seed products with prices"],
        "At least one product visible with id and price",
    ),
    _t(
        "cart_checkout_invoice",
        ["User adds product to cart", "User runs checkout", "Bot sends Telegram invoice"],
        "Invoice message appears; no paid status yet",
    ),
    _t(
        "payment_success_fulfills",
        ["Simulate/complete successful_payment", "Order status becomes paid"],
        "Order marked paid; digital goods delivered if applicable",
    ),
    _t(
        "coupon_reduces_total",
        ["Apply seed coupon SAVE10", "Checkout total reflects discount"],
        "Discount applied once; invalid coupon rejected",
    ),
    _t(
        "i18n_lang",
        ["User sends /lang en", "UI strings switch to English"],
        "Subsequent replies in selected language",
    ),
]

SUBSCRIPTIONS = [
    _t(
        "plans_listed",
        ["User sends /plans"],
        "Free and paid seed plans listed with duration and price",
    ),
    _t(
        "subscribe_free",
        ["User subscribes to free plan"],
        "my_sub shows active free plan without payment",
    ),
    _t(
        "subscribe_paid_requires_payment",
        ["User selects paid VIP plan"],
        "Invoice sent; subscription inactive until successful_payment",
    ),
    _t(
        "gate_premium",
        ["User without sub hits a gated command", "User with active sub succeeds"],
        "Clear upgrade message when inactive",
    ),
]

POINTS = [
    _t(
        "balance_zero_or_seed",
        ["New user /balance"],
        "Non-negative balance; seed users may show demo points",
    ),
    _t(
        "daily_checkin_credits",
        ["User /daily or check-in once", "Repeat same day"],
        "First check-in credits points; second rejected or no double credit",
    ),
    _t(
        "leaderboard_order",
        ["Open /leaderboard"],
        "Users sorted by balance descending",
    ),
    _t(
        "debit_no_negative",
        ["Admin tries debit larger than balance"],
        "Rejected; balance unchanged",
    ),
]

CONTESTS = [
    _t(
        "list_open",
        ["User /contests"],
        "Seed open contest visible",
    ),
    _t(
        "join_once",
        ["User joins contest", "User joins again"],
        "Second join rejected unless multi-entry allowed",
    ),
    _t(
        "draw_after_close",
        ["Admin ends contest", "Admin draw_winner"],
        "Winner chosen from entries only after close",
    ),
]

GROWTH = [
    _t(
        "referral_code_unique",
        ["User requests referral code"],
        "Stable unique code per user",
    ),
    _t(
        "claim_referral",
        ["New user claims valid code", "Claims own code"],
        "Valid claim rewards both sides; self-referral blocked",
    ),
    _t(
        "streak_increments",
        ["Check-in two consecutive days"],
        "Streak becomes 2; skip day resets per rules",
    ),
]

SAAS = [
    _t(
        "privacy_public",
        ["User /privacy without subscription"],
        "Policy text returned",
    ),
    _t(
        "analytics_admin_only",
        ["Regular user /analytics", "Admin /analytics"],
        "User denied; admin sees overview numbers",
    ),
    _t(
        "export_delete_self",
        ["User /exportdata", "User confirms /deletedata"],
        "Export file/summary; delete removes or anonymizes user row",
    ),
]

CRM = [
    _t(
        "lead_capture",
        ["User submits lead form"],
        "Lead stored with status=new",
    ),
    _t(
        "pipeline_admin",
        ["Admin opens pipeline"],
        "Leads grouped by status",
    ),
]

SUPPORT = [
    _t(
        "ticket_lifecycle",
        ["User opens ticket", "Admin replies", "Admin closes"],
        "User sees status updates; closed ticket rejects further user replies",
    ),
    _t(
        "kb_search",
        ["User searches seed KB article"],
        "Matching article title/body returned",
    ),
]

EDUCATION = [
    _t(
        "enroll_and_progress",
        ["User enrolls seed course", "Opens first lesson"],
        "Progress > 0; certificate blocked until complete",
    ),
    _t(
        "quiz_score",
        ["User finishes seed quiz"],
        "Score stored and shown",
    ),
]

RESTAURANT = [
    _t(
        "menu_and_order",
        ["User views menu", "Places order"],
        "Order id returned; status pending then updatable by admin",
    ),
    _t(
        "table_book",
        ["User books table with time"],
        "Booking stored; conflict times rejected",
    ),
]

JOBS = [
    _t(
        "list_and_apply",
        ["User lists jobs", "Applies to seed job"],
        "Application stored; duplicate apply handled",
    ),
]

MARKETPLACE = [
    _t(
        "create_and_search",
        ["User creates listing", "Another user searches keyword"],
        "Listing appears in search results",
    ),
]

EVENTS = [
    _t(
        "rsvp",
        ["User RSVPs seed event", "Admin lists attendees"],
        "User on attendee list; capacity enforced if set",
    ),
]

WALLET = [
    _t(
        "topup_and_balance",
        ["User tops up via payment flow", "Checks balance"],
        "Balance increases only after successful_payment",
    ),
    _t(
        "transfer",
        ["User transfers to another user id"],
        "Both balances update; insufficient funds rejected",
    ),
]

COMMUNITY = [
    _t(
        "post_and_feed",
        ["User creates post", "Opens feed"],
        "Post visible; like increments count",
    ),
]

GROUP = [
    _t(
        "moderation_ban",
        ["Admin bans user in group context"],
        "Bot attempts restrict/ban via Telegram API with clear error if not admin",
    ),
]

BOOKING = [
    _t(
        "book_and_cancel",
        ["User books slot", "User cancels"],
        "Slot free after cancel; double-book blocked",
    ),
]


PACKS: dict[str, list[AcceptanceTest]] = {
    "shop": SHOP,
    "subscriptions": SUBSCRIPTIONS,
    "points": POINTS,
    "contests": CONTESTS,
    "growth": GROWTH,
    "saas": SAAS,
    "crm": CRM,
    "support_tickets": SUPPORT,
    "support_pro": SUPPORT,
    "education": EDUCATION,
    "restaurant": RESTAURANT,
    "jobs": JOBS,
    "marketplace": MARKETPLACE,
    "events": EVENTS,
    "wallet": WALLET,
    "community": COMMUNITY,
    "group_management": GROUP,
    "booking": BOOKING,
}


def tests_for_preset(preset: str) -> list[AcceptanceTest]:
    return list(PACKS.get(preset or "", []))


def tests_as_dicts(preset: str) -> list[dict[str, Any]]:
    return [
        {"name": t.name, "steps": list(t.steps), "expected": t.expected}
        for t in tests_for_preset(preset)
    ]


__all__ = ["PACKS", "tests_for_preset", "tests_as_dicts", "AcceptanceTest"]
