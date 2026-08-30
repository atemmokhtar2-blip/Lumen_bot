"""Plans system REMOVED.

Billing is credits-only. This module remains as a thin compatibility shim so
legacy imports (get_plan / normalize_plan_id) do not crash. Everything maps to
a single unlimited default — no tier gates, no generation quotas by plan.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    id: str
    name: str
    name_ar: str
    price_usd_month: float
    price_usd_year: float
    generations_per_month: int  # 0 = unlimited
    hosted_bots: int
    messages_per_month: int
    live_preview_seconds: int
    api_rpm: int
    white_label: bool
    custom_domain: bool
    priority_support: bool
    watermark: bool
    engine_tier: str
    support_email: str
    features: tuple[str, ...]
    allowed_engines: tuple[str, ...]


# Single unlimited profile — not a sellable "plan"
_DEFAULT = Plan(
    id="default",
    name="Credits",
    name_ar="رصيد",
    price_usd_month=0.0,
    price_usd_year=0.0,
    generations_per_month=0,  # unlimited (credits gate usage instead)
    hosted_bots=10**9,
    messages_per_month=0,
    live_preview_seconds=24 * 60 * 60,
    api_rpm=120,
    white_label=True,
    custom_domain=True,
    priority_support=True,
    watermark=False,
    engine_tier="advanced",
    support_email="",
    features=(
        "managed_hosting",
        "white_label",
        "custom_domain",
        "api",
        "credits",
    ),
    allowed_engines=(),
)

PLANS: dict[str, Plan] = {"default": _DEFAULT}


def normalize_plan_id(raw: str | None) -> str:
    return "default"


def get_plan(plan_id: str | None = None) -> Plan:
    return _DEFAULT


def public_plan_dict(plan: Plan | None = None) -> dict:
    p = plan or _DEFAULT
    return {
        "id": p.id,
        "name": p.name,
        "billing": "credits_only",
        "plans_removed": True,
        "generations_per_month": None,  # unlimited via plan; use credits
        "white_label": True,
    }
