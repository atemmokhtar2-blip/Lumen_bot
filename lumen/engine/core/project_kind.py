"""ProjectKind — single source of truth for what Lumen builds.

Phase 1 contract kinds:
  telegram_bot | web_site | web_api | cli_app | library

Extra kinds (discord_bot, whatsapp_bot, general_app, refine) map onto the
same delivery surfaces so planner strings stay compatible.
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Any, Iterable


class ProjectKind(str, Enum):
    TELEGRAM_BOT = "telegram_bot"
    WEB_SITE = "web_site"
    WEB_API = "web_api"
    CLI_APP = "cli_app"
    LIBRARY = "library"
    # Planner-compatible extensions (same surfaces as general / bot)
    DISCORD_BOT = "discord_bot"
    WHATSAPP_BOT = "whatsapp_bot"
    GENERAL_APP = "general_app"
    REFINE = "refine"


class DeliverySurface(str, Enum):
    TELEGRAM_RUNTIME = "telegram_runtime"  # trial chat + bot host
    HTTP_RUNTIME = "http_runtime"  # reserved — public URL (Phase 3)
    ARTIFACT_ONLY = "artifact_only"  # ZIP / files only today


_INTENT_TO_KIND: dict[str, ProjectKind] = {
    "telegram_bot": ProjectKind.TELEGRAM_BOT,
    "discord_bot": ProjectKind.DISCORD_BOT,
    "whatsapp_bot": ProjectKind.WHATSAPP_BOT,
    "web_api": ProjectKind.WEB_API,
    "web_site": ProjectKind.WEB_SITE,
    "cli_app": ProjectKind.CLI_APP,
    "library": ProjectKind.LIBRARY,
    "general_app": ProjectKind.GENERAL_APP,
    "refine": ProjectKind.REFINE,
}

_SITE_HINT = re.compile(
    r"\b(موقع|website|web\s*site|landing|portfolio|مدونة|blog|صفحة|homepage|معرض)\b",
    re.I,
)
_CLI_HINT = re.compile(
    r"\b(cli|command\s*line|سكربت|script|terminal|سطر\s*الأوامر|برنامج\s*طرفي)\b",
    re.I,
)

_LABEL_AR: dict[ProjectKind, str] = {
    ProjectKind.TELEGRAM_BOT: "بوت تيليجرام",
    ProjectKind.WEB_SITE: "موقع ويب",
    ProjectKind.WEB_API: "واجهة API",
    ProjectKind.CLI_APP: "برنامج سطر أوامر",
    ProjectKind.LIBRARY: "مكتبة بايثون",
    ProjectKind.DISCORD_BOT: "بوت ديسكورد",
    ProjectKind.WHATSAPP_BOT: "بوت واتساب",
    ProjectKind.GENERAL_APP: "برنامج عام",
    ProjectKind.REFINE: "تحسين مشروع موجود",
}

# Hard rules injected into Cline (no telegram bias for non-bot kinds)
_CLINE_RULES: dict[ProjectKind, str] = {
    ProjectKind.TELEGRAM_BOT: (
        "PROJECT_KIND=telegram_bot. Build a python-telegram-bot (v20+) Application. "
        "Read BOT_TOKEN/TELEGRAM_BOT_TOKEN from env only. Include /start handler."
    ),
    ProjectKind.WEB_SITE: (
        "PROJECT_KIND=web_site. Build a FastAPI (or Flask) web site with HTML templates "
        "or static files. MUST expose GET / (home page). Do NOT build a Telegram bot. "
        "No telegram imports. Health at GET /health."
    ),
    ProjectKind.WEB_API: (
        "PROJECT_KIND=web_api. Build a FastAPI JSON API. MUST expose GET /health. "
        "Do NOT build a Telegram bot. No telegram imports."
    ),
    ProjectKind.CLI_APP: (
        "PROJECT_KIND=cli_app. Build a CLI entrypoint (argparse or click) in main.py. "
        "Do NOT build a Telegram bot. Runnable: python main.py --help"
    ),
    ProjectKind.LIBRARY: (
        "PROJECT_KIND=library. Build an importable Python package + tests. "
        "Do NOT build a Telegram bot."
    ),
    ProjectKind.DISCORD_BOT: (
        "PROJECT_KIND=discord_bot. Build a discord.py bot. Token from env. No Telegram."
    ),
    ProjectKind.WHATSAPP_BOT: (
        "PROJECT_KIND=whatsapp_bot. Scaffold WhatsApp-oriented Python service. No Telegram."
    ),
    ProjectKind.GENERAL_APP: (
        "PROJECT_KIND=general_app. Build a runnable Python project matching the GOAL. "
        "Do NOT default to Telegram unless the goal explicitly asks for it."
    ),
    ProjectKind.REFINE: (
        "PROJECT_KIND=refine. Incremental repair only — edit existing files, do not scaffold a new bot."
    ),
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
    g = goal or ""
    if base == ProjectKind.WEB_API and _SITE_HINT.search(g):
        return ProjectKind.WEB_SITE
    if base == ProjectKind.GENERAL_APP and _CLI_HINT.search(g):
        return ProjectKind.CLI_APP
    if base == ProjectKind.GENERAL_APP and _SITE_HINT.search(g):
        return ProjectKind.WEB_SITE
    return base


def resolve_project_kind(
    *,
    text: str = "",
    preferred_keys: Iterable[str] | None = None,
    explicit: str | ProjectKind | None = None,
) -> ProjectKind:
    forced = parse_kind(explicit)
    if forced is not None:
        return forced
    from lumen.engine.services.multi_agent.dynamic_planner import classify_intent

    intent = classify_intent(text or "", preferred_keys=preferred_keys)
    return kind_from_plan_intent(intent.kind, goal=text or "")


def delivery_surface(kind: ProjectKind) -> DeliverySurface:
    if kind == ProjectKind.TELEGRAM_BOT:
        return DeliverySurface.TELEGRAM_RUNTIME
    if kind in {ProjectKind.WEB_API, ProjectKind.WEB_SITE}:
        import os
        # HTTP path is selected when public base is configured (VPS/domain ready).
        # Without base → artifact only (no fake URL).
        if (os.getenv("LUMEN_PUBLIC_BASE") or "").strip():
            return DeliverySurface.HTTP_RUNTIME
        return DeliverySurface.ARTIFACT_ONLY
    return DeliverySurface.ARTIFACT_ONLY


def http_runtime_hints(*, project_ref: str = "", kind: ProjectKind | None = None) -> dict[str, Any]:
    """Public URL + health path for web kinds. Empty public_url if base unset."""
    import os
    from pathlib import Path as _P
    base = (os.getenv("LUMEN_PUBLIC_BASE") or "").strip().rstrip("/")
    health = (os.getenv("LUMEN_HEALTH_PATH") or "/health").strip() or "/health"
    if not health.startswith("/"):
        health = "/" + health
    slug = ""
    if project_ref:
        slug = _P(str(project_ref)).name[:40].replace(" ", "-")
    if not slug:
        slug = "app"
    public_url = f"{base}/p/{slug}/" if base else ""
    return {
        "public_url": public_url,
        "health_path": health,
        "health_url": (public_url.rstrip("/") + health) if public_url else "",
        "start_hint": "uvicorn main:app --host 0.0.0.0 --port $PORT",
        "base_configured": bool(base),
    }


def label_ar(kind: ProjectKind) -> str:
    return _LABEL_AR.get(kind, kind.value)


def needs_bot_token(kind: ProjectKind) -> bool:
    return kind == ProjectKind.TELEGRAM_BOT


def cline_kind_rules(kind: ProjectKind) -> str:
    base = _CLINE_RULES.get(kind, _CLINE_RULES[ProjectKind.GENERAL_APP])
    files = ", ".join(default_deliverables(kind)[:12])
    return f"{base} Required files when greenfield: {files}."


def kind_metadata(kind: ProjectKind) -> dict[str, Any]:
    surface = delivery_surface(kind)
    return {
        "project_kind": kind.value,
        "delivery_surface": surface.value,
        "project_kind_label_ar": label_ar(kind),
        "needs_bot_token": needs_bot_token(kind),
    }


def planner_intent_kind(kind: ProjectKind) -> str:
    """Map ProjectKind → dynamic_planner task-graph key."""
    if kind == ProjectKind.WEB_SITE:
        return "web_api"  # same scaffold family + site acceptance in rules
    if kind == ProjectKind.CLI_APP:
        return "general_app"
    if kind in _INTENT_TO_KIND.values():
        # reverse lookup
        for k, v in _INTENT_TO_KIND.items():
            if v == kind:
                return k
    return kind.value



def default_deliverables(kind: ProjectKind) -> list[str]:
    if kind == ProjectKind.TELEGRAM_BOT:
        return ["main.py", "requirements.txt", "README.md", ".env.example"]
    if kind == ProjectKind.WEB_SITE:
        return ["main.py", "requirements.txt", "README.md", ".env.example", "templates/index.html", "static/style.css"]
    if kind == ProjectKind.WEB_API:
        return ["main.py", "requirements.txt", "README.md", ".env.example", "routers/__init__.py"]
    if kind == ProjectKind.CLI_APP:
        return ["main.py", "requirements.txt", "README.md"]
    if kind == ProjectKind.LIBRARY:
        return ["pyproject.toml", "README.md", "src/__init__.py", "tests/test_basic.py"]
    if kind in {ProjectKind.DISCORD_BOT, ProjectKind.WHATSAPP_BOT}:
        return ["main.py", "requirements.txt", "README.md", ".env.example"]
    return ["main.py", "requirements.txt", "README.md"]


def acceptance_hints(kind: ProjectKind) -> list[str]:
    if kind == ProjectKind.TELEGRAM_BOT:
        return ["main.py valid Python", "python-telegram-bot or equivalent in requirements", "token from environment", "/start handler registered"]
    if kind == ProjectKind.WEB_SITE:
        return ["main.py valid Python", "fastapi or flask in requirements", "GET / home page", "GET /health", "no telegram imports", "HTML template or static index"]
    if kind == ProjectKind.WEB_API:
        return ["main.py valid Python", "fastapi or flask in requirements", "GET /health", "no telegram imports"]
    if kind == ProjectKind.CLI_APP:
        return ["main.py valid Python", "CLI --help works", "argparse or click entrypoint", "no telegram imports"]
    if kind == ProjectKind.LIBRARY:
        return ["importable package", "at least one test file", "no telegram imports"]
    return ["main.py valid Python", "compileall passes"]


__all__ = [
    "ProjectKind",
    "DeliverySurface",
    "parse_kind",
    "kind_from_plan_intent",
    "resolve_project_kind",
    "delivery_surface",
    "label_ar",
    "needs_bot_token",
    "cline_kind_rules",
    "kind_metadata",
    "planner_intent_kind",
    "http_runtime_hints",
    "default_deliverables",
    "acceptance_hints",
]
