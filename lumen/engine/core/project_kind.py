"""ProjectKind — single source of truth for what Lumen builds.

Kinds: telegram_bot | web_site | web_api | cli_app | library
(+ discord_bot, whatsapp_bot, general_app, refine)

Phase 2: runtime contract, scaffolds, acceptance hints, workspace seed.
"""
from __future__ import annotations

import re
from enum import Enum
from pathlib import Path
from typing import Any, Iterable


class ProjectKind(str, Enum):
    TELEGRAM_BOT = "telegram_bot"
    WEB_SITE = "web_site"
    WEB_API = "web_api"
    CLI_APP = "cli_app"
    LIBRARY = "library"
    DISCORD_BOT = "discord_bot"
    WHATSAPP_BOT = "whatsapp_bot"
    GENERAL_APP = "general_app"
    REFINE = "refine"


class DeliverySurface(str, Enum):
    TELEGRAM_RUNTIME = "telegram_runtime"
    HTTP_RUNTIME = "http_runtime"
    ARTIFACT_ONLY = "artifact_only"


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

_CLINE_RULES: dict[ProjectKind, str] = {
    ProjectKind.TELEGRAM_BOT: (
        "PROJECT_KIND=telegram_bot. Build a python-telegram-bot (v20+) Application. "
        "Read BOT_TOKEN/TELEGRAM_BOT_TOKEN from env only. Include /start handler."
    ),
    ProjectKind.WEB_SITE: (
        "PROJECT_KIND=web_site. Build a FastAPI web site with Jinja2 templates and/or static/. "
        "MUST expose GET / (HTML home) and GET /health. Do NOT build a Telegram bot. "
        "No telegram imports. Entrypoint: uvicorn main:app"
    ),
    ProjectKind.WEB_API: (
        "PROJECT_KIND=web_api. Build a FastAPI JSON API. MUST expose GET /health returning JSON. "
        "Do NOT build a Telegram bot. No telegram imports. Entrypoint: uvicorn main:app"
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
        "Do NOT default to Telegram unless the goal explicitly asks for it. "
        "Document the entrypoint clearly in README.md"
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
        if (os.getenv("LUMEN_PUBLIC_BASE") or "").strip():
            return DeliverySurface.HTTP_RUNTIME
        return DeliverySurface.ARTIFACT_ONLY
    return DeliverySurface.ARTIFACT_ONLY


def http_runtime_hints(*, project_ref: str = "", kind: ProjectKind | None = None) -> dict[str, Any]:
    import os
    base = (os.getenv("LUMEN_PUBLIC_BASE") or "").strip().rstrip("/")
    health = (os.getenv("LUMEN_HEALTH_PATH") or "/health").strip() or "/health"
    if not health.startswith("/"):
        health = "/" + health
    slug = Path(str(project_ref)).name[:40].replace(" ", "-") if project_ref else "app"
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
    return _CLINE_RULES.get(kind, _CLINE_RULES[ProjectKind.GENERAL_APP])


def runtime_contract(kind: ProjectKind) -> dict[str, Any]:
    """start_command, health_path, port, env_keys for delivery/hosting metadata."""
    if kind == ProjectKind.TELEGRAM_BOT:
        return {
            "start_command": "python main.py",
            "health_path": "",
            "port": 0,
            "env_keys": ["BOT_TOKEN", "TELEGRAM_BOT_TOKEN"],
        }
    if kind in {ProjectKind.WEB_API, ProjectKind.WEB_SITE}:
        return {
            "start_command": "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}",
            "health_path": "/health",
            "port": 8000,
            "env_keys": ["PORT"],
        }
    if kind == ProjectKind.CLI_APP:
        return {
            "start_command": "python main.py --help",
            "health_path": "",
            "port": 0,
            "env_keys": [],
        }
    if kind == ProjectKind.LIBRARY:
        return {
            "start_command": "python -m pytest -q",
            "health_path": "",
            "port": 0,
            "env_keys": [],
        }
    if kind == ProjectKind.DISCORD_BOT:
        return {
            "start_command": "python main.py",
            "health_path": "",
            "port": 0,
            "env_keys": ["DISCORD_TOKEN"],
        }
    return {
        "start_command": "python main.py",
        "health_path": "",
        "port": 0,
        "env_keys": [],
    }


def default_deliverables(kind: ProjectKind) -> list[str]:
    if kind == ProjectKind.TELEGRAM_BOT:
        return ["main.py", "requirements.txt", "README.md", ".env.example"]
    if kind == ProjectKind.WEB_SITE:
        return [
            "main.py",
            "requirements.txt",
            "README.md",
            ".env.example",
            "templates/index.html",
            "static/style.css",
        ]
    if kind == ProjectKind.WEB_API:
        return ["main.py", "requirements.txt", "README.md", ".env.example", "routers/health.py"]
    if kind == ProjectKind.CLI_APP:
        return ["main.py", "requirements.txt", "README.md"]
    if kind == ProjectKind.LIBRARY:
        return ["pyproject.toml", "README.md", "src/__init__.py", "tests/test_basic.py"]
    if kind in {ProjectKind.DISCORD_BOT, ProjectKind.WHATSAPP_BOT}:
        return ["main.py", "requirements.txt", "README.md", ".env.example"]
    return ["main.py", "requirements.txt", "README.md"]


def acceptance_hints(kind: ProjectKind) -> list[str]:
    if kind == ProjectKind.TELEGRAM_BOT:
        return [
            "main.py valid Python",
            "python-telegram-bot or equivalent in requirements",
            "token from environment",
            "/start handler registered",
        ]
    if kind == ProjectKind.WEB_SITE:
        return [
            "main.py valid Python",
            "fastapi or flask in requirements",
            "GET / home page",
            "GET /health",
            "no telegram imports",
            "HTML template or static index",
            "compileall passes",
        ]
    if kind == ProjectKind.WEB_API:
        return [
            "main.py valid Python",
            "fastapi or flask in requirements",
            "GET /health",
            "no telegram imports",
            "compileall passes",
        ]
    if kind == ProjectKind.CLI_APP:
        return [
            "main.py valid Python",
            "CLI --help works",
            "argparse or click entrypoint",
            "no telegram imports",
            "compileall passes",
        ]
    if kind == ProjectKind.LIBRARY:
        return ["importable package", "at least one test file", "no telegram imports"]
    return ["main.py valid Python", "compileall passes"]


def kind_metadata(kind: ProjectKind) -> dict[str, Any]:
    surface = delivery_surface(kind)
    rc = runtime_contract(kind)
    return {
        "project_kind": kind.value,
        "delivery_surface": surface.value,
        "project_kind_label_ar": label_ar(kind),
        "needs_bot_token": needs_bot_token(kind),
        "start_command": rc["start_command"],
        "health_path": rc["health_path"],
        "port": rc["port"],
        "env_keys": list(rc["env_keys"]),
        "default_deliverables": default_deliverables(kind),
        "acceptance_hints": acceptance_hints(kind),
    }


def planner_intent_kind(kind: ProjectKind) -> str:
    if kind == ProjectKind.WEB_SITE:
        return "web_site"
    if kind == ProjectKind.CLI_APP:
        return "cli_app"
    for k, v in _INTENT_TO_KIND.items():
        if v == kind:
            return k
    return kind.value


def seed_workspace(work_dir: str | Path, kind: ProjectKind) -> list[str]:
    """Write minimal scaffold files if missing. Never overwrites existing files.

    Web scaffolds follow 2026 FastAPI practice: thin main + routers/health + /health.
    Site adds Jinja templates + static/. Telegram does not pre-write main.py.
    """
    root = Path(work_dir)
    root.mkdir(parents=True, exist_ok=True)
    created: list[str] = []

    def _write(rel: str, content: str) -> None:
        path = root / rel
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        created.append(rel)

    if kind == ProjectKind.WEB_API:
        _write("requirements.txt", "fastapi>=0.110\nuvicorn[standard]>=0.27\n")
        _write("routers/__init__.py", '"""HTTP routers."""\n')
        _write(
            "routers/health.py",
            '"""Liveness probe — required for hosting healthchecks."""\n'
            "from __future__ import annotations\n\n"
            "from fastapi import APIRouter\n\n"
            'router = APIRouter(tags=["health"])\n\n\n'
            '@router.get("/health")\n'
            "def health():\n"
            '    return {"status": "ok"}\n',
        )
        _write(
            "main.py",
            '"""API entry — include routers; keep business logic out of this file."""\n'
            "from __future__ import annotations\n\n"
            "from fastapi import FastAPI\n\n"
            "from routers.health import router as health_router\n\n"
            'app = FastAPI(title="Lumen API")\n'
            "app.include_router(health_router)\n",
        )
        _write(".env.example", "PORT=8000\n")
        _write(
            "README.md",
            "# API\n\n"
            "Entrypoint: `uvicorn main:app --host 0.0.0.0 --port 8000`\n\n"
            "Health: `GET /health`\n\n"
            "Add feature routers under `routers/` and `include_router` in `main.py`.\n",
        )
    elif kind == ProjectKind.WEB_SITE:
        _write(
            "requirements.txt",
            "fastapi>=0.110\nuvicorn[standard]>=0.27\njinja2>=3.1\n",
        )
        _write(
            "main.py",
            '"""Website entry — templates + GET / and GET /health."""\n'
            "from __future__ import annotations\n\n"
            "from pathlib import Path\n\n"
            "from fastapi import FastAPI, Request\n"
            "from fastapi.responses import HTMLResponse\n"
            "from fastapi.staticfiles import StaticFiles\n"
            "from fastapi.templating import Jinja2Templates\n\n"
            "ROOT = Path(__file__).resolve().parent\n"
            'app = FastAPI(title="Lumen Site")\n'
            'app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")\n'
            'templates = Jinja2Templates(directory=str(ROOT / "templates"))\n\n\n'
            '@app.get("/", response_class=HTMLResponse)\n'
            "def home(request: Request):\n"
            '    return templates.TemplateResponse(request, "index.html", {"title": "Lumen"})\n\n\n'
            '@app.get("/health")\n'
            "def health():\n"
            '    return {"status": "ok"}\n',
        )
        _write(
            "templates/index.html",
            "<!DOCTYPE html>\n"
            '<html lang="ar" dir="rtl">\n'
            "<head>\n"
            '<meta charset="utf-8">\n'
            "<title>Lumen</title>\n"
            '<link rel="stylesheet" href="/static/style.css">\n'
            "</head>\n"
            "<body>\n"
            "<h1>مرحباً</h1>\n"
            "<p>موقع جاهز للتوسيع.</p>\n"
            "</body>\n"
            "</html>\n",
        )
        _write("static/style.css", "body{font-family:system-ui;margin:2rem}\n")
        _write(".env.example", "PORT=8000\n")
        _write(
            "README.md",
            "# Website\n\n"
            "Entrypoint: `uvicorn main:app --host 0.0.0.0 --port 8000`\n\n"
            "Home: `GET /`\nHealth: `GET /health`\n",
        )
    elif kind == ProjectKind.CLI_APP:
        _write("requirements.txt", "# add deps as needed\n")
        _write(
            "main.py",
            '"""CLI entry — extend argparse subcommands."""\n'
            "from __future__ import annotations\n\n"
            "import argparse\n\n\n"
            "def main(argv: list[str] | None = None) -> int:\n"
            '    p = argparse.ArgumentParser(description="Lumen CLI")\n'
            '    p.add_argument("--version", action="store_true")\n'
            "    args = p.parse_args(argv)\n"
            "    if args.version:\n"
            '        print("0.1.0")\n'
            "        return 0\n"
            "    p.print_help()\n"
            "    return 0\n\n\n"
            'if __name__ == "__main__":\n'
            "    raise SystemExit(main())\n",
        )
        _write("README.md", "# CLI\n\nRun: `python main.py --help`\n")
    elif kind == ProjectKind.LIBRARY:
        _write(
            "pyproject.toml",
            '[project]\nname = "lumen_lib"\nversion = "0.1.0"\nrequires-python = ">=3.10"\n',
        )
        _write("src/__init__.py", '"""Library package."""\n__version__ = "0.1.0"\n')
        _write(
            "tests/test_basic.py",
            "def test_version():\n    from src import __version__\n    assert __version__\n",
        )
        _write("README.md", "# Library\n\nImport from `src`.\n")
    elif kind == ProjectKind.TELEGRAM_BOT:
        _write("requirements.txt", "python-telegram-bot>=21.0\n")
        _write(".env.example", "BOT_TOKEN=\nTELEGRAM_BOT_TOKEN=\n")
        _write("README.md", "# Telegram bot\n\nSet BOT_TOKEN then `python main.py`\n")
    elif kind == ProjectKind.GENERAL_APP:
        _write(
            "README.md",
            "# Project\n\nEntrypoint: `python main.py`\n\n"
            "Document how to run this project after generation.\n",
        )
        _write("requirements.txt", "# add dependencies here\n")

    # Runtime contract sidecar for ZIP / hosting
    try:
        import json
        rc = runtime_contract(kind)
        manifest = {
            "project_kind": kind.value,
            "start_command": rc["start_command"],
            "health_path": rc["health_path"],
            "port": rc["port"],
            "env_keys": list(rc["env_keys"]),
            "delivery_surface": delivery_surface(kind).value,
        }
        man_path = root / ".lumen" / "runtime.json"
        if not man_path.exists():
            man_path.parent.mkdir(parents=True, exist_ok=True)
            man_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            created.append(".lumen/runtime.json")
        root_man = root / "lumen.runtime.json"
        if not root_man.exists():
            root_man.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            created.append("lumen.runtime.json")
    except Exception:
        pass

    return created


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
    "runtime_contract",
    "default_deliverables",
    "acceptance_hints",
    "seed_workspace",
]
