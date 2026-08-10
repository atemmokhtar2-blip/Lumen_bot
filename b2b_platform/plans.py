"""Subscription plans — B2B commercial surface."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    id: str
    name: str
    price_usd_month: float
    # Quotas (0 = unlimited)
    generations_per_month: int
    hosted_bots: int
    api_rpm: int  # requests per minute
    white_label: bool
    custom_domain: bool
    priority_support: bool
    features: tuple[str, ...]


PLANS: dict[str, Plan] = {
    "free": Plan(
        id="free",
        name="Free",
        price_usd_month=0,
        generations_per_month=20,
        hosted_bots=1,
        api_rpm=30,
        white_label=False,
        custom_domain=False,
        priority_support=False,
        features=("generate", "download_zip"),
    ),
    "pro": Plan(
        id="pro",
        name="Pro",
        price_usd_month=49,
        generations_per_month=500,
        hosted_bots=10,
        api_rpm=120,
        white_label=False,
        custom_domain=False,
        priority_support=False,
        features=("generate", "download_zip", "managed_hosting", "api_access"),
    ),
    "business": Plan(
        id="business",
        name="Business",
        price_usd_month=199,
        generations_per_month=5000,
        hosted_bots=100,
        api_rpm=600,
        white_label=True,
        custom_domain=True,
        priority_support=True,
        features=(
            "generate",
            "download_zip",
            "managed_hosting",
            "api_access",
            "white_label",
            "dashboard",
            "team_keys",
        ),
    ),
    "enterprise": Plan(
        id="enterprise",
        name="Enterprise",
        price_usd_month=0,  # custom
        generations_per_month=0,  # unlimited
        hosted_bots=0,
        api_rpm=3000,
        white_label=True,
        custom_domain=True,
        priority_support=True,
        features=(
            "generate",
            "download_zip",
            "managed_hosting",
            "api_access",
            "white_label",
            "dashboard",
            "team_keys",
            "sla",
            "sso",
            "dedicated_isolation",
        ),
    ),
}


def get_plan(plan_id: str) -> Plan:
    return PLANS.get((plan_id or "free").lower(), PLANS["free"])
