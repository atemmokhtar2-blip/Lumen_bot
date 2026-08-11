"""Subscription plans — Explorer (free) | Starter | Growth.

Enforcement is server-side only (billing + metering + generation/hosting gates).
Never trust client-supplied plan_id for privileges.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    id: str
    name: str
    name_ar: str
    price_usd_month: float
    price_usd_year: float  # 0 = no annual
    # Quotas (0 = unlimited)
    generations_per_month: int
    hosted_bots: int  # 0 = no 24/7 hosting
    messages_per_month: int  # 0 = unlimited
    live_preview_seconds: int  # max live run for non-hosted preview
    api_rpm: int
    white_label: bool
    custom_domain: bool
    priority_support: bool
    watermark: bool  # force "Powered by Maestro" in generated bots
    engine_tier: str  # basic | standard | advanced
    support_email: str
    features: tuple[str, ...]
    # Capability keys allowed at this tier (empty = no extra filter beyond features)
    allowed_engines: tuple[str, ...]


# Engine tiers — higher includes lower
ENGINE_TIERS = {
    "basic": (
        "core_commands",
        "buttons",
        "auto_reply",
        "faq_basic",
        "echo",
        "help",
        "start",
    ),
    "standard": (
        "core_commands",
        "buttons",
        "auto_reply",
        "faq_basic",
        "echo",
        "help",
        "start",
        "payments",
        "stripe",
        "webhooks",
        "external_api",
        "schedule",
        "voice_basic",
        "admin_ops",
    ),
    "advanced": (
        "core_commands",
        "buttons",
        "auto_reply",
        "faq_basic",
        "echo",
        "help",
        "start",
        "payments",
        "stripe",
        "webhooks",
        "external_api",
        "schedule",
        "voice_basic",
        "admin_ops",
        "database",
        "sqlite",
        "postgres",
        "analytics",
        "metrics",
        "team",
        "white_label",
    ),
}


PLANS: dict[str, Plan] = {
    # 1) Explorer / Hobby — free
    "explorer": Plan(
        id="explorer",
        name="Explorer",
        name_ar="المجرب",
        price_usd_month=0,
        price_usd_year=0,
        generations_per_month=25,
        hosted_bots=0,  # no 24/7
        messages_per_month=2000,
        live_preview_seconds=30 * 60,  # 30 minutes
        api_rpm=20,
        white_label=False,
        custom_domain=False,
        priority_support=False,
        watermark=True,
        engine_tier="basic",
        support_email="",
        features=(
            "generate",
            "download_zip",
            "live_preview",
        ),
        allowed_engines=ENGINE_TIERS["basic"],
    ),
    # 2) Starter / Indie — $8/mo or $144/yr
    "starter": Plan(
        id="starter",
        name="Starter",
        name_ar="المبادر",
        price_usd_month=8,
        price_usd_year=144,  # ~40% off vs 8*12
        generations_per_month=50,
        hosted_bots=1,
        messages_per_month=10_000,
        live_preview_seconds=60 * 60,
        api_rpm=60,
        white_label=False,
        custom_domain=False,
        priority_support=False,
        watermark=False,
        engine_tier="standard",
        support_email="capability7maestro7bot@gmail.com",
        features=(
            "generate",
            "download_zip",
            "live_preview",
            "managed_hosting",
            "api_access",
            "payments",
            "webhooks",
        ),
        allowed_engines=ENGINE_TIERS["standard"],
    ),
    # 3) Growth / Pro — $30/mo or $390/yr
    "growth": Plan(
        id="growth",
        name="Growth",
        name_ar="النمو",
        price_usd_month=30,
        price_usd_year=390,  # ~20% off vs 30*12
        generations_per_month=300,
        hosted_bots=5,
        messages_per_month=100_000,
        live_preview_seconds=2 * 60 * 60,
        api_rpm=180,
        white_label=True,
        custom_domain=False,
        priority_support=True,
        watermark=False,
        engine_tier="advanced",
        support_email="capability7maestro7bot@gmail.com",
        features=(
            "generate",
            "download_zip",
            "live_preview",
            "managed_hosting",
            "api_access",
            "payments",
            "webhooks",
            "database",
            "analytics",
            "white_label",
            "dashboard",
            "priority_support",
        ),
        allowed_engines=ENGINE_TIERS["advanced"],
    ),
}

# Aliases — old ids + marketing names map to canonical
_ALIASES = {
    "free": "explorer",
    "hobby": "explorer",
    "explorer": "explorer",
    "indie": "starter",
    "starter": "starter",
    "pro": "growth",
    "growth": "growth",
    "business": "growth",
    "unlimited": "growth",
    "enterprise": "growth",
}

WATERMARK_TEXT = "⚡ Powered by Maestro"
SUPPORT_EMAIL = "capability7maestro7bot@gmail.com"


def normalize_plan_id(plan_id: str | None) -> str:
    key = (plan_id or "explorer").strip().lower()
    return _ALIASES.get(key, key if key in PLANS else "explorer")


def get_plan(plan_id: str | None) -> Plan:
    return PLANS[normalize_plan_id(plan_id)]


def plan_allows_feature(plan_id: str | None, feature: str) -> bool:
    plan = get_plan(plan_id)
    return feature in plan.features


def filter_engines_for_plan(plan_id: str | None, keys: list[str] | None) -> list[str]:
    """Drop capability keys not allowed on this plan (server-side)."""
    plan = get_plan(plan_id)
    allowed = set(plan.allowed_engines)
    if not keys:
        return list(plan.allowed_engines)
    out = []
    for k in keys:
        kk = str(k).strip().lower()
        if kk in allowed or kk.startswith("core"):
            out.append(k)
    return out or list(plan.allowed_engines)


def public_plan_dict(plan: Plan) -> dict:
    return {
        "id": plan.id,
        "name": plan.name,
        "name_ar": plan.name_ar,
        "price_usd_month": plan.price_usd_month,
        "price_usd_year": plan.price_usd_year,
        "generations_per_month": plan.generations_per_month,
        "hosted_bots": plan.hosted_bots,
        "messages_per_month": plan.messages_per_month,
        "live_preview_minutes": plan.live_preview_seconds // 60,
        "api_rpm": plan.api_rpm,
        "watermark": plan.watermark,
        "engine_tier": plan.engine_tier,
        "support_email": plan.support_email,
        "features": list(plan.features),
        "priority_support": plan.priority_support,
    }
