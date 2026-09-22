"""ProjectKind — single source of truth for what Lumen is building.

Phase 1: classify + carry through IR → generation metadata → delivery UI.
Hosting HTTP public URLs are Phase 3; this module only declares surfaces,
it does not invent running website hosts.
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Any, Iterable


class ProjectKind(str, Enum):
    TELEGRAM_BOT = "telegram_bot"
    DISCORD_BOT = "discord_bot"
    WHATSAPP_BOT = "whatsapp_bot"
    WEB_API = "web_api"
    WEB_SITE = "web_site"
    LIBRARY = "library"
    GENERAL_APP = "general_app"
    REFINE = "refine"


class DeliverySurface(str, Enum):
    """How the product is handed to the user after generation."""

    TELEGRAM_RUNTIME = "telegram_runtime"  # trial chat + permanent bot host
    HTTP_RUNTIME = "http_runtime"  # reserved for public URL host (Phase 3)
    ARTIFACT_ONLY = "artifact_only"  # ZIP / files; no live runtime yet


# PlanIntent.kind (dynamic_planner) → ProjectKind
_INTENT_TO_KIND: dict[str, ProjectKind] = {
    "telegram_bot": ProjectKind.TELEGRAM_BOT,
    "discord_bot": ProjectKind.DISCORD_BOT,
    "whatsapp_bot": ProjectKind.WHATSAPP_BOT,
    "web_api": ProjectKind.WEB_API,
    "library": ProjectKind.LIBRARY,
    "general_app": ProjectKind.GENERAL_APP,
    "refine": ProjectKind.REFINE,
}

_SITE_HINT = re.compile(
    r"\b(موقع|website|web\s*site|landing|portfolio|مدونة|blog|صفحة|homepage)\b",
    re.I,
)

_LABEL_AR: dict[ProjectKind, str] = {
    ProjectKind.TELEGRAM_BOT: "بوت تيليجرام",
    ProjectKind.DISCORD_BOT: "بوت ديسكورد",
    ProjectKind.WHATSAPP_BOT: "بوت واتساب",
    ProjectKind.WEB_API: "واجهة API / خادم ويب",
    ProjectKind.WEB_SITE: "موقع ويب",
    ProjectKind.LIBRARY: "مكتبة برمجية",
    ProjectKind.GENERAL_APP: "برنامج عام",
    ProjectKind.REFINE: "تحسين مشروع موجود",
}


def parse_kind(raw: str | ProjectKind | None) -> ProjectKind | None:
    if raw is None:
        return None
    if isinstance(raw, ProjectKind):
        return raw
    s = str(raw).strip().lower()
    if not s:
        return None
    try:
        return ProjectKind(s)
    except ValueError:
        return None


def kind_from_plan_intent(intent_kind: str, *, goal: str = "") -> ProjectKind:
    base = _INTENT_TO_KIND.get(str(intent_kind or "").strip().lower(), ProjectKind.GENERAL_APP)
    if base == ProjectKind.WEB_API and goal and _SITE_HINT.search(goal):
        return ProjectKind.WEB_SITE
    return base


def resolve_project_kind(
    *,
    text: str = "",
    preferred_keys: Iterable[str] | None = None,
    explicit: str | ProjectKind | None = None,
) -> ProjectKind:
    """Resolve kind: explicit package field wins, else planner intent."""
    forced = parse_kind(explicit)
    if forced is not None:
        return forced
    from lumen.engine.services.multi_agent.dynamic_planner import classify_intent

    intent = classify_intent(text or "", preferred_keys=preferred_keys)
    return kind_from_plan_intent(intent.kind, goal=text or "")


def delivery_surface(kind: ProjectKind) -> DeliverySurface:
    """What delivery is allowed today (honest — no fake hosts)."""
    if kind == ProjectKind.TELEGRAM_BOT:
        return DeliverySurface.TELEGRAM_RUNTIME
    if kind in {
        ProjectKind.WEB_API,
        ProjectKind.WEB_SITE,
        ProjectKind.DISCORD_BOT,
        ProjectKind.WHATSAPP_BOT,
        ProjectKind.GENERAL_APP,
        ProjectKind.LIBRARY,
        ProjectKind.REFINE,
    }:
        # Live HTTP / non-Telegram runtimes are not wired yet → files only
        return DeliverySurface.ARTIFACT_ONLY
    return DeliverySurface.ARTIFACT_ONLY


def label_ar(kind: ProjectKind) -> str:
    return _LABEL_AR.get(kind, kind.value)


def needs_bot_token(kind: ProjectKind) -> bool:
    return kind == ProjectKind.TELEGRAM_BOT


def kind_metadata(kind: ProjectKind) -> dict[str, Any]:
    """Flat dict for IR / GenerationResult.metadata."""
    surface = delivery_surface(kind)
    return {
        "project_kind": kind.value,
        "delivery_surface": surface.value,
        "project_kind_label_ar": label_ar(kind),
        "needs_bot_token": needs_bot_token(kind),
    }


__all__ = [
    "ProjectKind",
    "DeliverySurface",
    "parse_kind",
    "kind_from_plan_intent",
    "resolve_project_kind",
    "delivery_surface",
    "label_ar",
    "needs_bot_token",
    "kind_metadata",
]
